import numpy as np
from faster_whisper import WhisperModel

from dictate import config

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(
            config.WHISPER_MODEL_SIZE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
            download_root=str(config.MODELS_DIR / "whisper"),
        )
    return _model


def preload() -> None:
    """Loads the model eagerly so the first real hold isn't slower than the rest."""
    _get_model()


def transcribe(audio: np.ndarray, sample_rate: int) -> str:
    assert sample_rate == config.SAMPLE_RATE, (
        f"expected {config.SAMPLE_RATE}Hz audio, got {sample_rate}Hz"
    )
    model = _get_model()
    segments, _ = model.transcribe(audio, language="en")
    return " ".join(segment.text.strip() for segment in segments)
