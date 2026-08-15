from __future__ import annotations

import ctypes
import logging
import threading
import time
from collections.abc import Callable
from ctypes import wintypes

from dictate import config

logger = logging.getLogger(__name__)

VK_CONTROL_CODES = {0x11, 0xA2, 0xA3}  # VK_CONTROL, VK_LCONTROL, VK_RCONTROL
VK_SHIFT_CODES = {0x10, 0xA0, 0xA1}  # VK_SHIFT, VK_LSHIFT, VK_RSHIFT

_IDLE = "idle"
_WAITING = "waiting"
_ARMED = "armed"
_SUPPRESSED = "suppressed"


class HotkeyStateMachine:
    """Ctrl+Shift hold-to-talk state machine.

    Arms only if Ctrl+Shift are held alone past `threshold_s` with no third
    key pressed in between. A third key at any point (before or after
    arming) suppresses/cancels instead, so shortcuts like Ctrl+Shift+Esc
    are never interfered with.
    """

    def __init__(
        self,
        threshold_s: float,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        self.threshold_s = threshold_s
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_cancel = on_cancel or (lambda: None)
        self._lock = threading.Lock()
        self._state = _IDLE
        self._ctrl_down = False
        self._shift_down = False
        self._armed_at: float | None = None

    def key_down(self, vk: int, now: float) -> float | None:
        # Callbacks must never run while holding _lock: on_stop() calls
        # inject(), which calls SendInput(), which -- because our hook is
        # global -- re-enters this same thread's hook callback for the
        # synthetic keystrokes it just injected, before SendInput even
        # returns. That reentrant call tries to acquire the same
        # (non-reentrant) lock and deadlocks. Decide what to call while
        # locked, then call it after releasing.
        #
        # Returns the deadline (monotonic time) to check on_tick, but only
        # when a new wait period was just entered -- not on every keydown.
        # Windows fires repeated keydowns for a held key (confirmed in real
        # use: ~30 events/sec while a modifier is held), and the caller
        # schedules a real OS timer per deadline returned here; scheduling
        # one per repeat event would spawn a new thread every ~30ms for as
        # long as a key is held, for no benefit.
        callback = None
        deadline = None
        with self._lock:
            is_modifier = vk in VK_CONTROL_CODES or vk in VK_SHIFT_CODES
            if vk in VK_CONTROL_CODES:
                self._ctrl_down = True
            elif vk in VK_SHIFT_CODES:
                self._shift_down = True

            if is_modifier:
                if self._ctrl_down and self._shift_down and self._state == _IDLE:
                    self._state = _WAITING
                    self._armed_at = now + self.threshold_s
                    deadline = self._armed_at
            elif self._state == _WAITING:
                self._state = _SUPPRESSED
            elif self._state == _ARMED:
                self._state = _SUPPRESSED
                callback = self._on_cancel

        if callback is not None:
            callback()
        return deadline

    def key_up(self, vk: int, now: float) -> None:
        if vk not in VK_CONTROL_CODES and vk not in VK_SHIFT_CODES:
            return

        callback = None
        with self._lock:
            was_armed = self._state == _ARMED
            was_waiting = self._state == _WAITING
            if vk in VK_CONTROL_CODES:
                self._ctrl_down = False
            else:
                self._shift_down = False

            if was_armed:
                self._state = _IDLE
                self._armed_at = None
                callback = self._on_stop
            elif was_waiting:
                # One of the two required keys let go before the threshold
                # elapsed -- the "held together" window is broken, even if
                # the other modifier is still down. Cancel the pending arm.
                self._state = _IDLE
                self._armed_at = None
            elif not self._ctrl_down and not self._shift_down:
                self._state = _IDLE

        if callback is not None:
            callback()

    def on_tick(self, now: float) -> None:
        callback = None
        with self._lock:
            if self._state == _WAITING and self._armed_at is not None and now >= self._armed_at:
                self._state = _ARMED
                callback = self._on_start

        if callback is not None:
            callback()


WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# ctypes defaults to a 32-bit c_int for undeclared return types, which
# truncates 64-bit handles on Win64 and produces garbage values. Every
# WinAPI call used here must have explicit argtypes/restype.
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE
_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

_user32.SetWindowsHookExW.restype = wintypes.HANDLE
_user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int,
    ctypes.c_void_p,
    wintypes.HINSTANCE,
    wintypes.DWORD,
]

_user32.CallNextHookEx.restype = ctypes.c_long
_user32.CallNextHookEx.argtypes = [
    wintypes.HANDLE,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
]

_user32.UnhookWindowsHookEx.restype = wintypes.BOOL
_user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]

_user32.GetMessageW.restype = ctypes.c_int
_user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    ctypes.c_uint,
    ctypes.c_uint,
]


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        # ULONG_PTR per MSDN (a pointer-sized integer), not an actual
        # pointer -- happens to have the same size/alignment either way, so
        # this was a dormant mistype with no observable bug since the field
        # is never read here, but the correct type is an integer.
        ("dwExtraInfo", wintypes.WPARAM),
    ]


_LowLevelKeyboardProc = ctypes.WINFUNCTYPE(
    ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)


class HotkeyListener:
    """Installs a passive (non-blocking) WH_KEYBOARD_LL hook.

    Never swallows a keystroke -- Ctrl and Shift held alone type nothing
    visible and trigger no default Windows action on their own, so there is
    nothing to suppress at the OS level. All arming/cancelling is internal
    bookkeeping in the state machine; every real keystroke always reaches
    the focused app normally.
    """

    def __init__(
        self,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        on_cancel: Callable[[], None] | None = None,
        threshold_ms: int = config.HOLD_THRESHOLD_MS,
    ) -> None:
        self._sm = HotkeyStateMachine(threshold_ms / 1000, on_start, on_stop, on_cancel)
        self._hook_id = None
        self._proc = _LowLevelKeyboardProc(self._hook_proc)

    def _hook_proc(self, n_code: int, w_param: int, l_param: int) -> int:
        if n_code >= 0:
            kb = ctypes.cast(l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            now = time.monotonic()
            if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                logger.debug("key down: vk=0x%02X", kb.vkCode)
                deadline = self._sm.key_down(kb.vkCode, now)
                if deadline is not None:
                    delay = max(0.0, deadline - now)
                    threading.Timer(delay, lambda: self._sm.on_tick(time.monotonic())).start()
            elif w_param in (WM_KEYUP, WM_SYSKEYUP):
                logger.debug("key up: vk=0x%02X", kb.vkCode)
                self._sm.key_up(kb.vkCode, now)
        return _user32.CallNextHookEx(None, n_code, w_param, l_param)

    def start(self) -> None:
        module_handle = _kernel32.GetModuleHandleW(None)
        self._hook_id = _user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._proc, module_handle, 0
        )
        if not self._hook_id:
            raise ctypes.WinError(ctypes.get_last_error())
        logger.debug("hook installed, id=%s, thread=%s", self._hook_id, threading.get_ident())

    def stop(self) -> None:
        if self._hook_id:
            _user32.UnhookWindowsHookEx(self._hook_id)
            self._hook_id = None
            logger.debug("hook removed")

    def pump_messages(self) -> None:
        """Blocks, pumping the Windows message queue this hook needs to fire.

        Run this on the thread that called start(), typically a dedicated
        background thread.
        """
        msg = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))
