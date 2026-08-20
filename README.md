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

## What it is

red-shark is a personal, offline dictation utility for Windows. It's not a product — it's one tool, built for one user, to type by voice into whatever window happens to have focus: Notepad, a browser field, VS Code, anything. There's no cloud step anywhere in the pipeline — nothing you say ever leaves the machine.

It exists because cloud dictation tools mean your voice (and whatever you're dictating) goes to someone else's server. red-shark trades a bit of transcription polish for that guarantee: everything — speech-to-text and the cleanup pass — runs as local models on your own CPU.

<table>
<tr><td><b>Hold-to-talk hotkey</b></td><td>Ctrl+Shift, bare modifiers — never fires on <code>Ctrl+Shift+Esc</code>, <code>+Z</code>, <code>+T</code>, <code>+S</code>, <code>+N</code>, or any other three-key shortcut that starts the same way.</td></tr>
<tr><td><b>On-device transcription</b></td><td>Speech is transcribed locally with <code>faster-whisper</code>, CPU-only, no GPU required.</td></tr>
<tr><td><b>LLM cleanup that won't destroy your sentence</b></td><td>A local model strips filler words and fixes punctuation, with regression tests guarding against silently dropped content.</td></tr>
<tr><td><b>Types into anything</b></td><td>Direct <code>SendInput</code> injection at the cursor — works in Notepad, browsers, editors, any focused window.</td></tr>
<tr><td><b>Zero network calls at runtime</b></td><td>Nothing leaves your machine. No cloud, no accounts, no telemetry.</td></tr>
<tr><td><b>Launch on demand</b></td><td>Sits in the tray only while you're using it — not a background service that's always resident in RAM.</td></tr>
</table>

---

## How it works

Five stages, each its own module, wired together in `dictate/__main__.py`:

```
Ctrl+Shift held  →  hotkey.py    →  low-level keyboard hook (WH_KEYBOARD_LL) arms
     (~250ms)                        after a hold threshold; a third key cancels
                                      it instantly so Ctrl+Shift+Esc etc. still work
                                            │
  speak, release  →  audio.py    →  sounddevice records the hold, returns a
                                      numpy float32 buffer on release
                                            │
                     transcribe.py → faster-whisper (tiny.en, int8, CPU) turns
                                      the buffer into raw text
                                            │
                     cleanup.py   → a local llama-server.exe subprocess
                                      (Qwen2.5-1.5B-Instruct, Q4_K_M) strips
                                      filler words and fixes punctuation —
                                      talked to over local HTTP, not a Python
                                      binding, and never over the network
                                            │
                     inject.py    → SendInput types the cleaned text at the
                                      cursor, in the window that has focus
```

Both models load once at startup and stay resident for the life of the process — see [Resource usage](#resource-usage) for why. The cleanup subprocess is bound to a Windows Job Object, so it's killed automatically the moment the app exits, by any means (clean quit, crash, or a Task Manager force-kill) — it can't leak RAM in the background.

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

### Day-to-day launch

No need to activate the venv or remember the module invocation every time — a `red-shark.lnk` shortcut in the project root runs `pythonw.exe -m dictate` directly (the windowless Python interpreter), so it starts straight into the tray with **no console window at all**. Quit via the tray icon's right-click **Quit** item — that's the only shutdown path in this mode, since there's no console to Ctrl+C.

Running `python -m dictate` from a real terminal (e.g. for debugging) still prints logs to the console as normal, in addition to `dictate.log`.

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

## Known limitations

- **Filler-word removal is inconsistent, especially mid-sentence "um"/"uh".** The cleanup model is deliberately conservative — it's tuned to never delete real content over aggressively stripping every filler, after an earlier version silently dropped whole clauses (see `memory.md`). The tradeoff: some fillers get through. Accepted as a real limit of a 1.5B model, not a bug.
- **The local cleanup model isn't fully deterministic, even at temperature 0.0** — the same input can occasionally produce slightly different output across calls, most likely CPU multi-threaded floating-point non-associativity in llama.cpp.
- **First-ever dictation on a cold machine will show more of both of the above** — no cache, no model "warm-up" in the practical sense, and you're still learning the hold-timing yourself. It settles with use.

## Troubleshooting

**"An Application Control policy has blocked this file" / the app won't start at all.** This is Windows 11's **Smart App Control**, not a red-shark bug: it blocks unsigned native DLLs from pip-installed packages, and `faster-whisper`'s `av` dependency ships one (even though red-shark never actually uses the code path that needs it — it only gets imported). Fixed as of this repo by stubbing `av` out in `dictate/_av_stub.py` before `faster_whisper` is imported, so the real (blocked) extension is never loaded. If you hit a *different* blocked file, check `Event Viewer → Applications and Services Logs → Microsoft → Windows → CodeIntegrity → Operational` (event ID 3077) for the exact path.

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
| `.venv\Scripts\python.exe -m PyInstaller dictate.spec` | Build a standalone `dist\dictate\` folder (no Python/venv needed to run it) |
| `scripts\launch.bat` | Alternative quick-launch entry point via `pythonw.exe` (the `red-shark.lnk` shortcut now calls `pythonw.exe` directly instead) |

**Standalone build:** `pyinstaller dictate.spec` produces a single-folder build at `dist\dictate\dictate.exe`. Model weights aren't bundled into it — copy (or symlink) your `models\` and `bin\` folders to sit alongside `dictate.exe` in `dist\dictate\` before running it; the exe resolves paths relative to its own location, not the source tree. Verified working end to end (preload, tray icon, hotkey, and the force-kill mic/RAM cleanup all behave the same as running from source).

Calling `.venv\Scripts\python.exe` directly, rather than activating the venv first, is what this project's own setup and testing has used throughout — it sidesteps per-shell activation differences between cmd and PowerShell.

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
  _av_stub.py         → stubs faster_whisper's unused `av` import (see Troubleshooting)
models/               → downloaded model weights (gitignored)
bin/llamacpp/         → downloaded llama.cpp CPU binaries (gitignored)
scripts/
  download_models.py → fetches everything models/ and bin/ need
  launch.bat          → alternative quick-launch entry point (red-shark.lnk calls pythonw.exe directly)
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
