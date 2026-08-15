import threading

from dictate.hotkey import VK_CONTROL_CODES, VK_SHIFT_CODES, HotkeyStateMachine

VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_ESCAPE = 0x1B
VK_Z = 0x5A
VK_PACKET = 0xE7  # what Windows reports for a SendInput(KEYEVENTF_UNICODE) keystroke

THRESHOLD_S = 0.25


class Recorder:
    def __init__(self):
        self.starts = 0
        self.stops = 0
        self.cancels = 0

    def on_start(self):
        self.starts += 1

    def on_stop(self):
        self.stops += 1

    def on_cancel(self):
        self.cancels += 1


def make_sm(rec: Recorder) -> HotkeyStateMachine:
    return HotkeyStateMachine(THRESHOLD_S, rec.on_start, rec.on_stop, rec.on_cancel)


def test_arms_after_threshold_when_ctrl_shift_held_alone():
    rec = Recorder()
    sm = make_sm(rec)

    sm.key_down(VK_LCONTROL, now=0.0)
    sm.key_down(VK_LSHIFT, now=0.0)
    sm.on_tick(now=THRESHOLD_S)

    assert rec.starts == 1


def test_does_not_arm_before_threshold_elapses():
    rec = Recorder()
    sm = make_sm(rec)

    sm.key_down(VK_LCONTROL, now=0.0)
    sm.key_down(VK_LSHIFT, now=0.0)
    sm.on_tick(now=THRESHOLD_S - 0.05)

    assert rec.starts == 0


def test_stop_fires_once_on_release_after_armed():
    rec = Recorder()
    sm = make_sm(rec)

    sm.key_down(VK_LCONTROL, now=0.0)
    sm.key_down(VK_LSHIFT, now=0.0)
    sm.on_tick(now=THRESHOLD_S)
    sm.key_up(VK_LSHIFT, now=THRESHOLD_S + 1.0)

    assert rec.starts == 1
    assert rec.stops == 1


def test_release_before_threshold_never_arms():
    rec = Recorder()
    sm = make_sm(rec)

    sm.key_down(VK_LCONTROL, now=0.0)
    sm.key_down(VK_LSHIFT, now=0.0)
    sm.key_up(VK_LSHIFT, now=0.1)
    sm.on_tick(now=THRESHOLD_S + 1.0)

    assert rec.starts == 0
    assert rec.stops == 0


def test_third_key_before_threshold_prevents_arming_without_cancel():
    rec = Recorder()
    sm = make_sm(rec)

    sm.key_down(VK_LCONTROL, now=0.0)
    sm.key_down(VK_LSHIFT, now=0.0)
    sm.key_down(VK_ESCAPE, now=0.05)
    sm.on_tick(now=THRESHOLD_S + 1.0)

    assert rec.starts == 0
    assert rec.cancels == 0


def test_third_key_after_armed_fires_cancel_not_stop():
    rec = Recorder()
    sm = make_sm(rec)

    sm.key_down(VK_LCONTROL, now=0.0)
    sm.key_down(VK_LSHIFT, now=0.0)
    sm.on_tick(now=THRESHOLD_S)
    sm.key_down(VK_ESCAPE, now=THRESHOLD_S + 0.05)

    assert rec.starts == 1
    assert rec.cancels == 1
    assert rec.stops == 0


def test_ctrl_alone_never_arms():
    rec = Recorder()
    sm = make_sm(rec)

    sm.key_down(VK_LCONTROL, now=0.0)
    sm.on_tick(now=THRESHOLD_S + 1.0)

    assert rec.starts == 0


def test_shift_alone_never_arms():
    rec = Recorder()
    sm = make_sm(rec)

    sm.key_down(VK_LSHIFT, now=0.0)
    sm.on_tick(now=THRESHOLD_S + 1.0)

    assert rec.starts == 0


def test_left_and_right_modifier_variants_are_equivalent():
    rec = Recorder()
    sm = make_sm(rec)

    sm.key_down(VK_RCONTROL, now=0.0)
    sm.key_down(VK_RSHIFT, now=0.0)
    sm.on_tick(now=THRESHOLD_S)

    assert rec.starts == 1


def test_can_rearm_after_full_release_following_suppression():
    rec = Recorder()
    sm = make_sm(rec)

    # First hold: suppressed by a third key, never arms.
    sm.key_down(VK_LCONTROL, now=0.0)
    sm.key_down(VK_LSHIFT, now=0.0)
    sm.key_down(VK_ESCAPE, now=0.05)
    sm.key_up(VK_ESCAPE, now=0.1)
    sm.key_up(VK_LCONTROL, now=0.2)
    sm.key_up(VK_LSHIFT, now=0.2)

    # Second hold: clean, should arm normally.
    sm.key_down(VK_LCONTROL, now=1.0)
    sm.key_down(VK_LSHIFT, now=1.0)
    sm.on_tick(now=1.0 + THRESHOLD_S)

    assert rec.starts == 1


def test_vk_code_sets_cover_generic_and_left_right_variants():
    assert VK_CONTROL_CODES == {0x11, 0xA2, 0xA3}
    assert VK_SHIFT_CODES == {0x10, 0xA0, 0xA1}


def test_on_stop_reentering_key_events_does_not_deadlock():
    # Regression test for a real bug: on_stop() (called while the state
    # machine's internal lock is held) runs inject(), which calls
    # SendInput(), which -- because the keyboard hook is global -- delivers
    # the synthetic keystrokes it just injected back into this same
    # thread's hook callback before SendInput even returns. That reentrant
    # call used to try to reacquire the same non-reentrant lock and hang
    # forever. Simulate that reentrancy directly here.
    rec = Recorder()
    sm = HotkeyStateMachine(THRESHOLD_S, rec.on_start, rec.on_stop, rec.on_cancel)

    def on_stop_that_reenters():
        rec.stops += 1
        # Simulates SendInput's synthetic keystrokes re-entering the hook.
        sm.key_down(VK_PACKET, now=100.0)
        sm.key_up(VK_PACKET, now=100.0)

    sm._on_stop = on_stop_that_reenters

    sm.key_down(VK_LCONTROL, now=0.0)
    sm.key_down(VK_LSHIFT, now=0.0)
    sm.on_tick(now=THRESHOLD_S)

    done = threading.Event()

    def release():
        sm.key_up(VK_LSHIFT, now=THRESHOLD_S + 1.0)
        done.set()

    thread = threading.Thread(target=release, daemon=True)
    thread.start()
    finished = done.wait(timeout=2.0)

    assert finished, "key_up deadlocked instead of returning"
    assert rec.stops == 1
