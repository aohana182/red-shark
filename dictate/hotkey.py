from __future__ import annotations

import ctypes
import threading
import time
from collections.abc import Callable
from ctypes import wintypes

from dictate import config

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

    def key_down(self, vk: int, now: float) -> None:
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
                return

            if self._state == _WAITING:
                self._state = _SUPPRESSED
            elif self._state == _ARMED:
                self._state = _SUPPRESSED
                self._on_cancel()

    def key_up(self, vk: int, now: float) -> None:
        with self._lock:
            if vk not in VK_CONTROL_CODES and vk not in VK_SHIFT_CODES:
                return

            was_armed = self._state == _ARMED
            was_waiting = self._state == _WAITING
            if vk in VK_CONTROL_CODES:
                self._ctrl_down = False
            else:
                self._shift_down = False

            if was_armed:
                self._state = _IDLE
                self._armed_at = None
                self._on_stop()
                return

            if was_waiting:
                # One of the two required keys let go before the threshold
                # elapsed -- the "held together" window is broken, even if
                # the other modifier is still down. Cancel the pending arm.
                self._state = _IDLE
                self._armed_at = None
                return

            if not self._ctrl_down and not self._shift_down:
                self._state = _IDLE

    def on_tick(self, now: float) -> None:
        with self._lock:
            if self._state == _WAITING and self._armed_at is not None and now >= self._armed_at:
                self._state = _ARMED
                self._on_start()


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
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
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
                self._sm.key_down(kb.vkCode, now)
                threading.Timer(
                    self._sm.threshold_s,
                    lambda: self._sm.on_tick(time.monotonic()),
                ).start()
            elif w_param in (WM_KEYUP, WM_SYSKEYUP):
                self._sm.key_up(kb.vkCode, now)
        return _user32.CallNextHookEx(None, n_code, w_param, l_param)

    def start(self) -> None:
        module_handle = _kernel32.GetModuleHandleW(None)
        self._hook_id = _user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._proc, module_handle, 0
        )
        if not self._hook_id:
            raise ctypes.WinError(ctypes.get_last_error())

    def stop(self) -> None:
        if self._hook_id:
            _user32.UnhookWindowsHookEx(self._hook_id)
            self._hook_id = None

    def pump_messages(self) -> None:
        """Blocks, pumping the Windows message queue this hook needs to fire.

        Run this on the thread that called start(), typically a dedicated
        background thread.
        """
        msg = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))
