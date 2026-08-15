import wave
from pathlib import Path

import numpy as np

from dictate.transcribe import transcribe

FIXTURE = Path(__file__).parent / "fixtures" / "sample.wav"


def load_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return audio, sample_rate


def test_transcribes_known_fixture_sentence():
    audio, sample_rate = load_wav(FIXTURE)

    text = transcribe(audio, sample_rate)

    lowered = text.lower()
    assert "quick" in lowered
    assert "brown" in lowered
    assert "fox" in lowered
