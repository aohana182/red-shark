import numpy as np

import dictate.transcribe as transcribe_module
from dictate.__main__ import (
    _CTRL_BREAK_EVENT,
    _CTRL_C_EVENT,
    _CTRL_CLOSE_EVENT,
    _CTRL_LOGOFF_EVENT,
    _CTRL_SHUTDOWN_EVENT,
    App,
    _make_icon_image,
)


class FakeIcon:
    """Stands in for pystray.Icon so tests never touch the real Win32 tray
    backend -- constructing a real one registers an OS-level window class
    keyed on id(self), which pytest can collide on across many App()
    instances in one process (id() gets reused once an earlier Icon is
    garbage collected)."""

    def __init__(self, name, image, title, menu=None):
        self.name = name
        self.icon = image
        self.title = title
        self.menu = menu
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True

    def update_menu(self) -> None:
        pass


def make_app_with_fake_stops():
    app = App(icon_factory=FakeIcon)
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
    for ctrl_type in (
        _CTRL_C_EVENT,
        _CTRL_BREAK_EVENT,
        _CTRL_CLOSE_EVENT,
        _CTRL_LOGOFF_EVENT,
        _CTRL_SHUTDOWN_EVENT,
    ):
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
    app = App(icon_factory=FakeIcon)
    app._recorder.start_recording = _raise

    app._on_start()  # must not raise


def test_on_stop_does_not_raise_when_recording_fails():
    app = App(icon_factory=FakeIcon)
    app._recorder.stop_recording = _raise

    app._on_stop()  # must not raise


def test_on_stop_does_not_raise_when_transcription_fails():
    app = App(icon_factory=FakeIcon)
    app._recorder.stop_recording = lambda: (np.ones((100,), dtype=np.float32), 16000)

    original = transcribe_module.transcribe
    transcribe_module.transcribe = _raise
    try:
        app._on_stop()  # must not raise
    finally:
        transcribe_module.transcribe = original


def test_on_cancel_does_not_raise_when_recording_fails():
    app = App(icon_factory=FakeIcon)
    app._recorder.stop_recording = _raise

    app._on_cancel()  # must not raise


def _raise(*_args, **_kwargs):
    raise RuntimeError("simulated failure")


def _icon_pixels(image):
    return image.tobytes()


def test_starts_unpaused():
    app = App(icon_factory=FakeIcon)

    assert app._paused is False


def test_toggle_pause_flips_state():
    app = App(icon_factory=FakeIcon)

    app._toggle_pause(app._icon, None)
    assert app._paused is True

    app._toggle_pause(app._icon, None)
    assert app._paused is False


def test_on_start_does_not_record_while_paused():
    app = App(icon_factory=FakeIcon)
    app._paused = True
    started = {"called": False}
    app._recorder.start_recording = lambda: started.__setitem__("called", True)

    app._on_start()

    assert started["called"] is False


def test_on_start_records_when_not_paused():
    app = App(icon_factory=FakeIcon)
    started = {"called": False}
    app._recorder.start_recording = lambda: started.__setitem__("called", True)

    app._on_start()

    assert started["called"] is True


def test_icon_shows_paused_state_after_toggle():
    app = App(icon_factory=FakeIcon)

    app._toggle_pause(app._icon, None)

    assert _icon_pixels(app._icon.icon) == _icon_pixels(_make_icon_image("paused"))


def test_icon_reverts_to_idle_after_toggling_pause_off():
    app = App(icon_factory=FakeIcon)

    app._toggle_pause(app._icon, None)
    app._toggle_pause(app._icon, None)

    assert _icon_pixels(app._icon.icon) == _icon_pixels(_make_icon_image("idle"))


def test_icon_shows_recording_state_while_recording():
    app = App(icon_factory=FakeIcon)
    app._recorder.start_recording = lambda: None

    app._on_start()

    assert _icon_pixels(app._icon.icon) == _icon_pixels(_make_icon_image("recording"))


def test_icon_reverts_to_idle_after_stop():
    app = App(icon_factory=FakeIcon)
    app._recorder.start_recording = lambda: None
    app._recorder.stop_recording = lambda: (np.zeros((0,), dtype=np.float32), 16000)

    app._on_start()
    app._on_stop()

    assert _icon_pixels(app._icon.icon) == _icon_pixels(_make_icon_image("idle"))


def test_icon_reverts_to_paused_after_stop_if_paused_meanwhile():
    # A pause toggled mid-hold must still stop the in-progress recording
    # (which already started while unpaused) rather than leaving the mic
    # stream open -- pause only prevents a *new* hold from starting.
    app = App(icon_factory=FakeIcon)
    app._recorder.start_recording = lambda: None
    stopped = {"called": False}

    def fake_stop():
        stopped["called"] = True
        return np.zeros((0,), dtype=np.float32), 16000

    app._recorder.stop_recording = fake_stop

    app._on_start()
    app._paused = True
    app._on_stop()

    assert stopped["called"] is True
    assert _icon_pixels(app._icon.icon) == _icon_pixels(_make_icon_image("paused"))


def test_quit_releases_the_microphone():
    app, _stopped = make_app_with_fake_stops()
    app._icon.stop = lambda: None
    released = {"called": False}
    app._recorder.stop_recording = lambda: released.__setitem__("called", True)

    app._quit(app._icon, None)

    assert released["called"] is True


def test_quit_does_not_raise_if_releasing_the_microphone_fails():
    app, _stopped = make_app_with_fake_stops()
    app._icon.stop = lambda: None
    app._recorder.stop_recording = _raise

    app._quit(app._icon, None)  # must not raise
