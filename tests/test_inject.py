from dictate.inject import KEYEVENTF_KEYUP, KEYEVENTF_UNICODE, inject


def test_sends_one_down_and_one_up_event_per_character():
    captured = {}

    def fake_send_input(count, array, struct_size):
        captured["count"] = count
        captured["events"] = [
            (array[i].union.ki.wScan, array[i].union.ki.dwFlags) for i in range(count)
        ]
        return count

    inject("Hi", send_input_fn=fake_send_input)

    assert captured["count"] == 4
    assert captured["events"] == [
        (ord("H"), KEYEVENTF_UNICODE),
        (ord("H"), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP),
        (ord("i"), KEYEVENTF_UNICODE),
        (ord("i"), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP),
    ]


def test_handles_punctuation_and_capitals_via_unicode_codes_not_shift_state():
    captured = {}

    def fake_send_input(count, array, struct_size):
        captured["scans"] = [array[i].union.ki.wScan for i in range(count)]
        return count

    inject("A!", send_input_fn=fake_send_input)

    assert captured["scans"] == [ord("A"), ord("A"), ord("!"), ord("!")]


def test_empty_string_sends_nothing():
    captured = {"called": False}

    def fake_send_input(count, array, struct_size):
        captured["called"] = True
        return count

    inject("", send_input_fn=fake_send_input)

    assert captured["called"] is False


def test_raises_when_fewer_events_are_sent_than_requested():
    def fake_send_input(count, array, struct_size):
        return count - 1

    try:
        inject("Hi", send_input_fn=fake_send_input)
    except OSError:
        pass
    else:
        raise AssertionError("expected OSError (ctypes.WinError) to be raised")
