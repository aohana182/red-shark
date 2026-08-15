import numpy as np

from dictate.audio import AudioRecorder


class FakeStream:
    def __init__(self, samplerate, channels, dtype, callback):
        self.callback = callback
        self.started = False
        self.stopped = False
        self.closed = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True


def make_factory():
    created = {}

    def factory(**kwargs):
        stream = FakeStream(**kwargs)
        created["stream"] = stream
        return stream

    return factory, created


def test_start_recording_starts_the_stream():
    factory, created = make_factory()
    rec = AudioRecorder(sample_rate=16000, stream_factory=factory)

    rec.start_recording()

    assert created["stream"].started


def test_stop_recording_concatenates_captured_frames_in_order():
    factory, created = make_factory()
    rec = AudioRecorder(sample_rate=16000, stream_factory=factory)

    rec.start_recording()
    stream = created["stream"]
    stream.callback(np.array([[0.1], [0.2]], dtype=np.float32), 2, None, None)
    stream.callback(np.array([[0.3]], dtype=np.float32), 1, None, None)
    audio, sample_rate = rec.stop_recording()

    assert sample_rate == 16000
    np.testing.assert_allclose(audio, [0.1, 0.2, 0.3])


def test_stop_recording_stops_and_closes_the_stream():
    factory, created = make_factory()
    rec = AudioRecorder(sample_rate=16000, stream_factory=factory)

    rec.start_recording()
    rec.stop_recording()

    assert created["stream"].stopped
    assert created["stream"].closed


def test_stop_recording_with_no_audio_returns_empty_buffer():
    factory, _created = make_factory()
    rec = AudioRecorder(sample_rate=16000, stream_factory=factory)

    rec.start_recording()
    audio, sample_rate = rec.stop_recording()

    assert audio.shape == (0,)
    assert sample_rate == 16000


def test_recorder_resets_frames_between_recordings():
    factory, created = make_factory()
    rec = AudioRecorder(sample_rate=16000, stream_factory=factory)

    rec.start_recording()
    created["stream"].callback(np.array([[0.5]], dtype=np.float32), 1, None, None)
    rec.stop_recording()

    rec.start_recording()
    audio, _ = rec.stop_recording()

    assert audio.shape == (0,)
