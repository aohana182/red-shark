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
