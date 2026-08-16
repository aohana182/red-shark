<p align="center">
  <img src="assets/banner.png" alt="red-shark" width="100%">
</p>

# red-shark

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/aohana182/red-shark/issues"><img src="https://img.shields.io/badge/Issues-welcome-yellow?style=for-the-badge" alt="Issues"></a>
  <img src="https://img.shields.io/badge/Windows-10%2F11-0078D6?style=for-the-badge&logo=windows" alt="Windows 10/11">
</p>

**Hold Ctrl+Shift, speak, release — your words land at the cursor, transcribed and cleaned up entirely on your own machine.**

<table>
<tr><td><b>Hold-to-talk hotkey</b></td><td>Ctrl+Shift, bare modifiers — never fires on <code>Ctrl+Shift+Esc</code>, <code>+Z</code>, <code>+T</code>, <code>+S</code>, <code>+N</code>, or any other three-key shortcut that starts the same way.</td></tr>
<tr><td><b>On-device transcription</b></td><td>Speech is transcribed locally with <code>faster-whisper</code>, CPU-only, no GPU required.</td></tr>
<tr><td><b>LLM cleanup that won't destroy your sentence</b></td><td>A local model strips filler words and fixes punctuation, with regression tests guarding against silently dropped content.</td></tr>
<tr><td><b>Types into anything</b></td><td>Direct <code>SendInput</code> injection at the cursor — works in Notepad, browsers, editors, any focused window.</td></tr>
<tr><td><b>Zero network calls at runtime</b></td><td>Nothing leaves your machine. No cloud, no accounts, no telemetry.</td></tr>
<tr><td><b>Launch on demand</b></td><td>Sits in the tray only while you're using it — not a background service that's always resident in RAM.</td></tr>
</table>

---

## Quick start

```sh
git clone https://github.com/aohana182/red-shark.git
cd red-shark
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts\download_models.py
.venv\Scripts\python.exe -m dictate
```

`download_models.py` fetches the cleanup LLM weights (~1.1GB) and the llama.cpp CPU binaries (~46MB) — the whisper model downloads itself on first use. Both `models/` and `bin/` are gitignored, so every fresh clone needs this step. See [Requirements](#requirements) below before you start.

Once running: click into any text field, hold **Ctrl+Shift**, speak a sentence, release. Cleaned-up text appears at the cursor a couple of seconds later.

## Requirements

- Windows 10/11
- Python 3.11+ (developed and tested on 3.14)
- A working microphone
- ~4GB free disk space for local models (whisper + cleanup LLM)

## Resource usage

Both models load once at startup and stay resident for as long as the app is running — traded off deliberately against reloading fresh on every dictation, which would add ~1.2-1.5s of latency per hold. In exchange:

- **Cleanup LLM** (Qwen2.5-1.5B-Instruct, Q4_K_M): ~1.7GB RAM
- **Whisper** (`tiny.en`, int8): a smaller additional footprint on top of that
- **Startup preload**: ~2-2.5s before the hotkey becomes active

This is exactly why red-shark is launch-on-demand rather than something that starts with Windows — it's meant to sit in the tray only while you're actively dictating, not hold onto that RAM in the background all day.

**On exit, all of it is freed** — not just on a clean Quit. The cleanup model runs as a separate `llama-server.exe` subprocess assigned to a Windows Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, so Windows kills it automatically the moment the parent process exits *by any means*, including a Task Manager force-kill or a crash — not just the graceful shutdown path. This was a real bug caught during testing (force-killing used to orphan the subprocess, silently leaking ~1.7GB) and is covered by a real (non-mocked) integration test in `tests/test_cleanup.py` that spawns a process, closes the job handle, and confirms the child actually dies.

---

## Tech stack

- **Python 3.11+** — the whole app
- **faster-whisper** (`tiny.en`, `int8`, CPU) — on-device speech-to-text
- **llama.cpp** (`llama-server.exe` binary) + **Qwen2.5-1.5B-Instruct GGUF** — local cleanup LLM, run as a subprocess and talked to over local HTTP, not a Python binding
- **pywin32 / ctypes** — the low-level keyboard hook (`WH_KEYBOARD_LL`) and `SendInput` text injection
- **pystray** — the system tray icon

---

## Scripts

| Command | Description |
|---|---|
| `.venv\Scripts\python.exe -m dictate` | Run from source, with logs printed directly (see also `dictate.log`) |
| `.venv\Scripts\python.exe -m pytest -q` | Run the test suite |
| `.venv\Scripts\python.exe -m ruff check .` | Lint |
| `.venv\Scripts\python.exe -m ruff format --check .` | Check formatting |
| `scripts\launch.bat` | Quick-launch entry point (used by the Desktop shortcut) |

Calling `.venv\Scripts\python.exe` directly, rather than activating the venv first, is what this project's own setup and testing has used throughout — it sidesteps per-shell activation differences between cmd and PowerShell.

**Day to day:** a `red-shark` shortcut on the Desktop runs `scripts\launch.bat`, opening minimized. Quit via the tray icon's right-click Quit item (Ctrl+C in the console is the fallback if it isn't minimized out of view).

**Logs:** `dictate.log` in the project root (gitignored) — DEBUG level for this app's own code, WARNING+ for third-party libraries. This includes the raw and cleaned text of everything you dictate, in plaintext, for debugging — it never leaves your machine, but keep that in mind before sharing the file itself.

---

## Project structure

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
tests/                → pytest suite
tasks/                → plan.md and todo.md, the working implementation plan
```

---

## Status

Phase 1 (raw dictation) and Phase 2 (LLM cleanup) are implemented, tested, and verified via live voice testing. Most `PRD.md` Success Criteria are confirmed — see that file for the full checklist and what's still open (browser/VS Code testing, a hard network-disabled run). Phase 3 (packaging polish: tray pause/resume, a standalone build) is in progress — see `tasks/todo.md`.

For session history, key architectural pivots, and an outstanding-items list, see `memory.md`.

---

## Contributing

This is currently a solo personal project, but it's structured for good practice regardless:

```sh
git clone https://github.com/aohana182/red-shark.git
cd red-shark
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pytest -q
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for branching, commit format, and PR process.

---

## License

MIT — see [LICENSE](LICENSE).
