from dictate.inject import KEYEVENTF_KEYUP, KEYEVENTF_UNICODE, inject


def make_recording_send_input(counts_to_return=None):
    calls = []

    def fake_send_input(count, array, struct_size):
        events = [(array[i].union.ki.wScan, array[i].union.ki.dwFlags) for i in range(count)]
        calls.append(events)
        if counts_to_return is not None:
            return counts_to_return.pop(0)
        return count

    return fake_send_input, calls


def test_sends_a_separate_send_input_call_per_character():
    fake_send_input, calls = make_recording_send_input()

    inject("Hi", send_input_fn=fake_send_input, sleep_fn=lambda _s: None)

    assert calls == [
        [(ord("H"), KEYEVENTF_UNICODE), (ord("H"), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)],
        [(ord("i"), KEYEVENTF_UNICODE), (ord("i"), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)],
    ]


def test_handles_punctuation_and_capitals_via_unicode_codes_not_shift_state():
    fake_send_input, calls = make_recording_send_input()

    inject("A!", send_input_fn=fake_send_input, sleep_fn=lambda _s: None)

    scans = [wscan for call in calls for wscan, _flags in call]
    assert scans == [ord("A"), ord("A"), ord("!"), ord("!")]


def test_empty_string_sends_nothing():
    fake_send_input, calls = make_recording_send_input()

    inject("", send_input_fn=fake_send_input, sleep_fn=lambda _s: None)

    assert calls == []


def test_raises_when_fewer_events_are_sent_than_requested():
    fake_send_input, _calls = make_recording_send_input(counts_to_return=[1])

    try:
        inject("Hi", send_input_fn=fake_send_input, sleep_fn=lambda _s: None)
    except OSError:
        pass
    else:
        raise AssertionError("expected OSError (ctypes.WinError) to be raised")


def test_sleeps_between_characters_but_not_after_the_last():
    fake_send_input, _calls = make_recording_send_input()
    sleeps = []

    inject("abc", send_input_fn=fake_send_input, sleep_fn=sleeps.append)

    assert len(sleeps) == 2
    assert all(s > 0 for s in sleeps)


def test_does_not_sleep_for_a_single_character():
    fake_send_input, _calls = make_recording_send_input()
    sleeps = []

    inject("a", send_input_fn=fake_send_input, sleep_fn=sleeps.append)

    assert sleeps == []
