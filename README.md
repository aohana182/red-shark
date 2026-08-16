# red-shark

A local, fully offline Windows dictation utility. Hold **Ctrl+Shift**, speak, release — your speech is transcribed on-device, cleaned up (filler words removed, punctuation fixed) by a local LLM, and typed directly into whatever app has focus.

No cloud, no accounts, no telemetry, no network calls at runtime.

## Requirements

- Windows 10/11
- Python 3.11+ (developed and tested on 3.14)
- A working microphone
- ~4GB free disk space for local models (whisper + cleanup LLM)

## Setup

```
git clone <this repo> red-shark
cd red-shark
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts\download_models.py
```

(Calling `.venv\Scripts\python.exe` directly, rather than activating the venv first, is what this project's own setup/testing has actually used throughout — it sidesteps any per-shell activation differences between cmd and PowerShell.)

`download_models.py` fetches two things that are *not* installed via pip:
- The cleanup LLM's GGUF weights (Qwen2.5-1.5B-Instruct, ~1.1GB) into `models/cleanup/`
- The official `llama.cpp` CPU binaries (~46MB) into `bin/llamacpp/`

The whisper model downloads automatically on first use — nothing to do there.

Both `models/` and `bin/` are gitignored; every fresh clone needs this step.

## Running

**Quick launch:** a `red-shark` shortcut is created on the Desktop (`scripts/launch.bat`), opening minimized. This is the normal way to use it day to day — the app is *not* meant to run all the time; launch it when you want to dictate, quit it when you're done.

**From source (for debugging, shows logs directly):**
```
.venv\Scripts\python.exe -m dictate
```

On startup it preloads both models (~2-2.5s total) before the hotkey becomes active, then sits in the system tray.

**Quit:** the tray icon's Quit item, or Ctrl+C in the console if it's not minimized out of view. (Right-click on the tray icon has not been confirmed reliable in testing — Ctrl+C is the dependable fallback. See `memory.md`.)

**Logs:** `dictate.log` in the project root (gitignored). DEBUG level for this app's own code, WARNING+ for third-party libraries.

## Usage

1. Launch the app (shortcut or `python -m dictate`)
2. Click into any text field
3. Hold **Ctrl+Shift**, speak a sentence, release
4. Cleaned-up text appears at the cursor, a couple seconds later

Common three-key shortcuts that start with Ctrl+Shift (`Ctrl+Shift+Esc`, `+Z`, `+T`, `+S`, `+N`, etc.) continue to work normally — dictation only arms if no third key follows.

## Testing

```
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
```

## Project Structure

```
dictate/
  __main__.py       → entry point, tray icon, App lifecycle
  hotkey.py          → Ctrl+Shift hold-to-talk keyboard hook
  audio.py           → mic capture
  transcribe.py      → faster-whisper wrapper
  cleanup.py         → manages the local llama-server subprocess, cleanup(text)
  inject.py          → SendInput text injection into focused window
  config.py          → model paths, hotkey binding, all tunable constants
models/               → downloaded model weights (gitignored)
bin/llamacpp/         → downloaded llama.cpp CPU binaries (gitignored)
scripts/
  download_models.py → fetches everything models/ and bin/ need
  launch.bat          → quick-launch entry point (used by the Desktop shortcut)
tests/                → pytest suite (54 tests as of the last session)
tasks/                → plan.md and todo.md, the working implementation plan
```

## Status

Phase 1 (raw dictation) and Phase 2 (LLM cleanup) are implemented and covered by automated tests, verified end-to-end via synthetic-input testing. **A live voice test by an actual human has not yet happened since the cleanup layer was added** — see `PRD.md` for the full spec and `memory.md` for session history, key decisions (especially why the cleanup LLM backend went through several pivots), and a detailed outstanding-items list.

**REVIEW THIS FILE NEXT SESSION** — written by an agent without a live human test of the instructions above; confirm the setup steps and commands actually work as described before trusting them at face value.
