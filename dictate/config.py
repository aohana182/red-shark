from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"

SAMPLE_RATE = 16000

WHISPER_MODEL_SIZE = "tiny.en"
WHISPER_COMPUTE_TYPE = "int8"

HOLD_THRESHOLD_MS = 250

# Delay between injected characters. Sending a whole sentence as one large
# burst of keystrokes with no delay can overwhelm some apps' input handling,
# silently dropping or garbling characters -- confirmed by real-world testing.
INJECT_CHAR_DELAY_MS = 8

CLEANUP_MODEL_PATH = MODELS_DIR / "cleanup-model.gguf"
