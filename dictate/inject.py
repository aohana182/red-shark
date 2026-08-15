import ctypes
import time
from ctypes import wintypes

from dictate import config

_user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002

ULONG_PTR = wintypes.WPARAM  # unsigned, pointer-sized on both 32- and 64-bit


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    # Must include MOUSEINPUT and HARDWAREINPUT even though this module only
    # ever populates `ki` -- SendInput validates cbSize against the real
    # Win32 INPUT struct size (40 bytes on x64), which is sized by the
    # largest union member (MOUSEINPUT), not by KEYBDINPUT alone. Omitting
    # them makes our struct 32 bytes and SendInput rejects it outright.
    _fields_ = [  # noqa: RUF012 -- ctypes Union, not a real mutable default
        ("ki", _KEYBDINPUT),
        ("mi", _MOUSEINPUT),
        ("hi", _HARDWAREINPUT),
    ]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUT_UNION)]


_user32.SendInput.restype = wintypes.UINT
_user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]


def _char_event(char: str, flags: int) -> _INPUT:
    ki = _KEYBDINPUT(wVk=0, wScan=ord(char), dwFlags=flags, time=0, dwExtraInfo=0)
    return _INPUT(type=INPUT_KEYBOARD, union=_INPUT_UNION(ki=ki))


def inject(text: str, send_input_fn=None, sleep_fn=time.sleep) -> None:
    """Types `text` into whatever window currently has focus.

    Uses KEYEVENTF_UNICODE so every character -- including punctuation and
    capitals -- is injected by Unicode code point, without needing to
    compute virtual-key codes or simulate Shift state.

    Sends one character at a time with a small delay between them, rather
    than the whole string as one SendInput burst -- confirmed by real-world
    testing that some apps silently drop or garble characters when a long
    string arrives as a single zero-delay burst.
    """
    if not text:
        return

    send_input_fn = send_input_fn or _user32.SendInput
    delay_s = config.INJECT_CHAR_DELAY_MS / 1000

    for i, char in enumerate(text):
        events = (
            _char_event(char, KEYEVENTF_UNICODE),
            _char_event(char, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP),
        )
        array = (_INPUT * 2)(*events)
        sent = send_input_fn(2, array, ctypes.sizeof(_INPUT))
        if sent != 2:
            raise ctypes.WinError(ctypes.get_last_error())

        if i < len(text) - 1:
            sleep_fn(delay_s)
