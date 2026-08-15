import numpy as np
import sounddevice as sd

from dictate import config


class AudioRecorder:
    def __init__(self, sample_rate: int = config.SAMPLE_RATE, stream_factory=sd.InputStream):
        self._sample_rate = sample_rate
        self._stream_factory = stream_factory
        self._frames: list[np.ndarray] = []
        self._stream = None

    def _callback(self, indata, frames, time_info, status) -> None:
        self._frames.append(indata.copy())

    def start_recording(self) -> None:
        self._frames = []
        self._stream = self._stream_factory(
            samplerate=self._sample_rate,
            channels=1,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def stop_recording(self) -> tuple[np.ndarray, int]:
        self._stream.stop()
        self._stream.close()
        self._stream = None

        if not self._frames:
            return np.zeros((0,), dtype=np.float32), self._sample_rate

        audio = np.concatenate(self._frames, axis=0).reshape(-1)
        return audio, self._sample_rate
