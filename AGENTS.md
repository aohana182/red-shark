# red-shark — Agent Context

## What this is

A local, fully offline Windows dictation utility, built for a single user (the repo owner) running on a Lenovo ThinkPad T14s (Intel Core Ultra 7 255U, 32GB RAM, no discrete GPU). Hold Ctrl+Shift, speak, release — speech is transcribed on-device, cleaned up by a local LLM (filler words removed, punctuation fixed), and typed directly into whatever window has focus. No cloud, no accounts, no telemetry, no network calls at runtime.

## Stack

- Python 3.11+ (developed and tested on 3.14)
- `faster-whisper` (`tiny.en`, `int8`, CPU-only) for transcription
- `llama-server.exe` (official llama.cpp CPU binary, run as a subprocess, talked to over local HTTP) running Qwen2.5-1.5B-Instruct GGUF for cleanup — not a Python LLM binding
- `pywin32` / `ctypes` for the low-level keyboard hook and `SendInput` text injection
- `pystray` for the tray icon
- `pytest` + `ruff` for tests/lint/format

## Structure

```
dictate/
  __main__.py    → entry point, tray icon, App lifecycle, console-ctrl shutdown handling
  hotkey.py      → Ctrl+Shift hold-to-talk keyboard hook (WH_KEYBOARD_LL)
  audio.py       → mic capture via sounddevice
  transcribe.py  → faster-whisper wrapper
  cleanup.py     → manages the local llama-server subprocess, cleanup(text), Job Object kill-on-close
  inject.py      → SendInput text injection into focused window
  config.py      → model paths, hotkey binding, all tunable constants
models/, bin/    → gitignored, downloaded by scripts/download_models.py
tests/           → pytest suite; tests/test_cleanup_quality.py needs the real model downloaded, skips otherwise
tasks/           → plan.md (architecture decisions, risks) and todo.md (task-level plan and status)
PRD.md           → the spec, including Success Criteria checklist (kept up to date, don't let it go stale)
memory.md        → session-by-session history: decisions, pivots, and why. Read this first when resuming work.
```

## How to run

```sh
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts\download_models.py
.venv\Scripts\python.exe -m dictate
.venv\Scripts\python.exe -m pytest -q
```

## Key decisions

- **Hotkey is bare Ctrl+Shift, hold-to-talk, with a ~250ms arm threshold and cancel-on-third-key.** This is deliberate: Ctrl+Shift is the lead-in to common three-key shortcuts (`Ctrl+Shift+Esc`, `+Z`, `+T`, `+S`, `+N`). The hook must never arm dictation on a bare press — only after the threshold, and only if no third key follows. Changing this is a PRD boundary item ("ask first").
- **Cleanup runs as a subprocess (`llama-server.exe`), not a Python binding.** `llama-cpp-python` has no prebuilt wheel for this machine's Python 3.14, and the one community wheel that does crashes at model load (`STATUS_ILLEGAL_INSTRUCTION`) — confirmed to be a wheel-specific CPU-targeting bug, not a real hardware limit, since the official binary loads the same GGUF fine. Don't reintroduce a Python LLM binding without re-verifying this.
- **Cleanup model is Qwen2.5-1.5B-Instruct, not 3B.** Dropped from 3B after RAM footprint concerns (4.7-6GB vs 1.66GB), no quality regression observed for this task. See `memory.md` for the ONNX/RTN quantization detour that was tried and rejected first (hallucination).
- **The cleanup system prompt has a hard "never delete a clause carrying real information" rule**, added after a live voice test showed the model silently dropping real content (not just filler). See `memory.md` Session 2 and `tests/test_cleanup_quality.py` for the reproduction case and regression tests. If you touch `dictate/cleanup.py`'s `_SYSTEM_PROMPT`, run those tests and re-read that history first — the failure mode is subtle (it doesn't hallucinate, it deletes) and took 4 prompt iterations to substantially fix. Note: the local model isn't fully deterministic at temperature 0 (likely CPU multi-threaded float variance), so these tests carry a small amount of inherent flakiness.
- **Launch on demand, not a background service.** No run-on-login by explicit user decision — neither model should be resident in RAM when the user isn't dictating.
- **Windows Job Object (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`) on the cleanup subprocess**, so force-killing the app (Task Manager) doesn't orphan `llama-server.exe` still holding ~1.66GB RAM.

## Out of scope

Personal dictionary, per-app formatting/style profiles, live preview overlay, voice commands/automation — explicitly deferred for v1 per `PRD.md`. Don't add these without the user asking first. Also out of scope: any cloud fallback, telemetry, accounts, or licensing scheme — this must stay fully offline at runtime.

## Gotchas

- `_on_start`/`_on_stop`/`_on_cancel` in `__main__.py` run synchronously inside the global keyboard hook's `ctypes` callback — an exception escaping there gets silently swallowed by `ctypes` instead of raised normally, so every entry point there is defensively wrapped. Don't remove that without understanding why.
- The hook's `start()` and `pump_messages()` must run on the *same* thread — callbacks are only delivered to the thread that installed the hook.
- Non-BMP Unicode (emoji) requires UTF-16 surrogate pairs in `inject.py`'s `SendInput` calls — `wScan` is 16-bit.
- `AudioRecorder.stop_recording()` can be called before `start_recording()` has actually finished starting (observed with very short holds) — must not crash; returns an empty buffer instead.
