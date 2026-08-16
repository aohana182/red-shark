import sys
from pathlib import Path


def _resolve_project_root() -> Path:
    # A PyInstaller-frozen build's __file__ points inside the bundle, not
    # next to the built exe -- models/ and bin/ are meant to sit alongside
    # the exe (see README), so the root must be derived from sys.executable
    # instead when frozen.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _resolve_project_root()
MODELS_DIR = PROJECT_ROOT / "models"

SAMPLE_RATE = 16000

WHISPER_MODEL_SIZE = "tiny.en"
WHISPER_COMPUTE_TYPE = "int8"

HOLD_THRESHOLD_MS = 250

# Delay between injected characters. Sending a whole sentence as one large
# burst of keystrokes with no delay can overwhelm some apps' input handling,
# silently dropping or garbling characters -- confirmed by real-world testing.
INJECT_CHAR_DELAY_MS = 8

# Official Qwen release, not a third-party quantization -- better provenance.
# 1.5B (not 3B): ~1.66GB resident RAM vs ~4.7-6GB for the 3B model, with no
# quality regression observed for this task -- see tasks/plan.md.
CLEANUP_MODEL_REPO = "Qwen/Qwen2.5-1.5B-Instruct-GGUF"
CLEANUP_MODEL_FILENAME = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
CLEANUP_MODEL_PATH = MODELS_DIR / "cleanup" / CLEANUP_MODEL_FILENAME

CLEANUP_CONTEXT_SIZE = 2048
CLEANUP_MAX_TOKENS = 256

# llama-cpp-python has no prebuilt wheel for this machine's Python 3.14, and
# the one community wheel that does (llama-cpp-python-win) crashes at model
# load (STATUS_ILLEGAL_INSTRUCTION) -- confirmed via real testing to be a
# CPU-targeting issue in that specific wheel, not a hardware limitation: the
# official llama.cpp CPU binary loads the same GGUF file on this same CPU
# without error. So cleanup.py runs the official llama-server.exe binary as
# a subprocess and talks to it over local HTTP instead of using a Python
# binding at all.
LLAMACPP_BIN_DIR = PROJECT_ROOT / "bin" / "llamacpp"
LLAMACPP_SERVER_EXE = LLAMACPP_BIN_DIR / "llama-server.exe"
LLAMACPP_RELEASE_REPO = "ggml-org/llama.cpp"
LLAMACPP_ASSET_PATTERN = "-bin-win-cpu-x64.zip"
CLEANUP_SERVER_PORT = 8811
