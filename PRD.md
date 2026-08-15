# Spec: red-shark — Local Windows Dictation App

## Objective
A background Windows utility that lets you dictate text into any focused application via a hold-to-talk hotkey. Speech is transcribed locally, cleaned up by a local LLM (filler words removed, punctuation/grammar fixed), and inserted directly at the cursor. Fully offline — no cloud, no accounts, no telemetry. Single user (you).

**Success looks like:** hold Shift+Z → speak → release → clean text appears where your cursor was, in under ~2-3 seconds for a typical sentence.

## Tech Stack
- **Language:** Python 3.11+
- **STT:** `faster-whisper` (CTranslate2 backend), `tiny.en` model, `int8` quantization — CPU-only, no GPU dependency. One-line config swap to `base.en`/`small.en` if accuracy is lacking.
- **Cleanup LLM:** `llama-cpp-python` running a quantized local model in-process (no external service) — default **Qwen2.5-3B-Instruct** or **Llama-3.2-3B-Instruct**, `Q4_K_M` GGUF. 32GB RAM leaves headroom to swap to a 7-8B model later via config if you want better cleanup at the cost of latency.
- **Audio capture:** `sounddevice`
- **Windows integration:**
  - Hotkey: **Shift+Z, hold-to-talk**, via a low-level keyboard hook (`WH_KEYBOARD_LL` through `ctypes`/`pywin32`) tracking both keys' down/up state — chosen because `RegisterHotKey` only fires on a combo press, not hold-duration. Shift+Z has no OS or common-app global-shortcut collision (verified: all `Win+*` combos are OS-reserved and cannot be overridden; `Ctrl+Alt+*` fires accidentally via AltGr on non-US layouts — both avoided; Shift+Z is also a validated real-world preset used by FluidVox). The hook must **swallow** the Z keystroke (block it from reaching the focused app) — otherwise a stray "Z" gets typed at the start of every dictation, since Z is a printable character unlike a pure modifier key.
  - Text injection: `SendInput` via `ctypes`/`pywin32`
  - Tray icon: `pystray` (start/stop, quit)
- **Packaging:** PyInstaller, single-folder build, run-on-login optional via Startup shortcut

## Commands
```
Setup:  python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt
Run:    python -m dictate
Build:  pyinstaller dictate.spec
Test:   pytest
Lint:   ruff check . --fix
```

## Project Structure
```
dictate/
  __main__.py       → entry point, tray icon, event loop
  hotkey.py          → Shift+Z hold-to-talk keyboard hook
  audio.py           → mic capture, start/stop on hold
  transcribe.py      → faster-whisper wrapper
  cleanup.py         → llama-cpp-python wrapper, cleanup prompt
  inject.py          → SendInput text injection into focused window
  config.py          → model paths, hotkey binding, constants
models/               → downloaded GGUF + whisper model files (gitignored)
tests/                → unit tests
```

## Code Style
- Flat, minimal modules — one responsibility per file, no class hierarchies where a function does the job
- Type hints on all function signatures
- No abstraction layers for "future" STT/LLM backends — hardcode faster-whisper and llama-cpp-python calls directly; swap later if actually needed
```python
def transcribe(audio: np.ndarray, sample_rate: int) -> str:
    segments, _ = model.transcribe(audio, language="en")
    return " ".join(s.text.strip() for s in segments)
```

## Testing Strategy
- `pytest` unit tests for: hotkey state machine (press/hold/release), cleanup prompt output shape, text injection targeting
- No automated test for actual audio/model output (non-deterministic) — manual verification instead
- Manual smoke test before any commit: dictate a real sentence into Notepad and confirm correct insertion

## Boundaries
- **Always:** keep the whole pipeline local — no network calls at runtime, ever
- **Ask first:** adding any new runtime dependency beyond what's listed above; changing the hotkey default; anything that requires admin/elevated privileges
- **Never:** add cloud fallback, telemetry, accounts, or licensing of any kind; add personal dictionary, per-app profiles, live overlay, or voice commands (explicitly out of scope for v1)

## Success Criteria
- [ ] Hold Shift+Z → speak → release → correct text appears at cursor in the focused app
- [ ] Works in at least: Notepad, a browser text field, VS Code
- [ ] End-to-end latency (release hotkey → text inserted) under ~3s for a one-sentence dictation
- [ ] Cleanup removes filler words ("um", "uh") and fixes obvious punctuation without altering meaning
- [ ] Runs entirely offline — works with network disabled
- [ ] No admin/elevated privileges required to run
- [ ] No stray "Z" (or accidental capitalization) is ever typed into the focused app when the hotkey is used

## Hardware Reference
Lenovo ThinkPad T14s Gen 6, Intel Core Ultra 7 255U (12 cores / 14 threads), 32GB RAM, integrated Intel Graphics (no discrete GPU). All model choices above are CPU-only by design to match this hardware.

## Out of Scope for v1
Personal dictionary, per-app formatting/style profiles, live preview overlay, voice commands/automation — all explicitly deferred, not to be implemented until requested.

## Open Questions
None outstanding — resolved via conversation on 2026-08-15 (project name, hotkey, model sizes); project renamed from savage-tongue to red-shark and hotkey changed from Caps Lock to Shift+Z on 2026-08-15.
