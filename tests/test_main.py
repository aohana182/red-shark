import numpy as np

import dictate.transcribe as transcribe_module
from dictate.__main__ import (
    _CTRL_BREAK_EVENT,
    _CTRL_C_EVENT,
    _CTRL_CLOSE_EVENT,
    _CTRL_LOGOFF_EVENT,
    _CTRL_SHUTDOWN_EVENT,
    App,
)


def make_app_with_fake_stops():
    app = App()
    stopped = {"listener": False, "icon": False}
    app._listener.stop = lambda: stopped.__setitem__("listener", True)
    app._icon.stop = lambda: stopped.__setitem__("icon", True)
    return app, stopped


def test_ctrl_c_triggers_shutdown():
    app, stopped = make_app_with_fake_stops()

    handled = app.handle_console_event(_CTRL_C_EVENT)

    assert handled is True
    assert stopped == {"listener": True, "icon": True}


def test_console_close_triggers_shutdown():
    app, stopped = make_app_with_fake_stops()

    handled = app.handle_console_event(_CTRL_CLOSE_EVENT)

    assert handled is True
    assert stopped == {"listener": True, "icon": True}


def test_all_tracked_ctrl_types_trigger_shutdown():
    for ctrl_type in (_CTRL_C_EVENT, _CTRL_BREAK_EVENT, _CTRL_CLOSE_EVENT, _CTRL_LOGOFF_EVENT, _CTRL_SHUTDOWN_EVENT):
        app, stopped = make_app_with_fake_stops()

        handled = app.handle_console_event(ctrl_type)

        assert handled is True, f"ctrl_type {ctrl_type} should trigger shutdown"
        assert stopped == {"listener": True, "icon": True}


def test_unrecognized_ctrl_type_is_ignored():
    app, stopped = make_app_with_fake_stops()

    handled = app.handle_console_event(999)

    assert handled is False
    assert stopped == {"listener": False, "icon": False}


# _on_start/_on_stop/_on_cancel run synchronously inside the global keyboard
# hook's callback. An exception escaping there doesn't propagate normally --
# ctypes swallows it with a bare stderr warning, bypassing logging, and can
# leave the hook's return value to Windows undefined. Every entry point must
# catch and log instead of letting anything through.


def test_on_start_does_not_raise_when_recording_fails():
    app = App()
    app._recorder.start_recording = _raise

    app._on_start()  # must not raise


def test_on_stop_does_not_raise_when_recording_fails():
    app = App()
    app._recorder.stop_recording = _raise

    app._on_stop()  # must not raise


def test_on_stop_does_not_raise_when_transcription_fails():
    app = App()
    app._recorder.stop_recording = lambda: (np.ones((100,), dtype=np.float32), 16000)

    original = transcribe_module.transcribe
    transcribe_module.transcribe = _raise
    try:
        app._on_stop()  # must not raise
    finally:
        transcribe_module.transcribe = original


def test_on_cancel_does_not_raise_when_recording_fails():
    app = App()
    app._recorder.stop_recording = _raise

    app._on_cancel()  # must not raise


def _raise(*_args, **_kwargs):
    raise RuntimeError("simulated failure")
