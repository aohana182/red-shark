# Project Memory: red-shark

Session reasoning, decisions, and open questions not fully captured in commit messages. See `PRD.md` for the spec and `tasks/plan.md` / `tasks/todo.md` for the task-level plan and status.

---

### 2026-08-15 — Session 1: Spec → Phase 1 (Foundation) → Phase 2 (Cleanup) complete

**What this session built**: a working local Windows dictation app. Hold Ctrl+Shift, speak, release — transcribed via `faster-whisper`, cleaned up (fillers removed, punctuation fixed) via a local LLM, typed into whatever app has focus.

**Current status**: Phase 1 (raw dictation) and Phase 2 (LLM cleanup) are both implemented, tested (51 automated tests, all passing), and verified working end-to-end via real synthetic-input tests. **Not yet confirmed by the user's own live voice test since the cleanup layer was wired in** — see Outstanding below.

## Key Decisions and Why

- **Hotkey**: Ctrl+Shift, hold-to-talk. Bare modifiers (no letter key) to avoid any printable-character injection risk. Requires a hold-duration threshold (~250ms) + cancel-on-third-key logic in `hotkey.py`, because Ctrl+Shift alone is the lead-in to common shortcuts (`Ctrl+Shift+Esc`, `+Z`, `+T`, `+S`, `+N`) — verified via real synthetic-input testing that those shortcuts still work normally while the app is running.
- **STT**: `faster-whisper`, `tiny.en`, int8, CPU-only. Works well; PRD documents the config knob to escalate to `base.en`/`small.en` if accuracy ever seems lacking.
- **Cleanup LLM — this took several pivots, worth understanding for future work**:
  1. Originally planned: Qwen2.5-3B-Instruct GGUF via `llama-cpp-python`. No prebuilt wheel exists for this machine's Python 3.14.
  2. Tried a community fork (`llama-cpp-python-win`) with a prebuilt wheel — installed fine but **crashed at model load** (`STATUS_ILLEGAL_INSTRUCTION`). Root-caused via direct testing: not a real hardware limitation — the *official* llama.cpp CPU binary loads the same GGUF file on the same CPU without error (it ships proper per-microarchitecture runtime dispatch; the community wheel apparently doesn't).
  3. Briefly pivoted to ONNX Runtime GenAI (Llama-3.2-3B, int4 RTN quantization) to sidestep the crash. This introduced a *quality* regression instead — RTN is a cruder quantization method than GGUF's K-quants, and it reliably hallucinated (e.g., "uh, so" → "I think so").
  4. **Final approach**: run the *official* `llama-server.exe` binary (from llama.cpp's GitHub releases, fetched dynamically by `scripts/download_models.py`) as a subprocess, talk to it over local HTTP. No Python LLM binding at all. Model: **Qwen2.5-1.5B-Instruct GGUF Q4_K_M** (dropped from 3B after user feedback that the RAM footprint — 4.7-6GB — was too much for a background utility; 1.5B uses ~1.66GB with no quality regression for this task).
  5. Evaluated and rejected a pure regex-based filler-word stripper as a full replacement for the LLM: safe and free for unambiguous fillers (um/uh), but has a real, disqualifying failure mode on words with legitimate non-filler meanings — `"you know the answer, right"` → `"The answer, right."` (silently destroys correct sentences). Strictly worse than the LLM's conservative under-cleaning. A narrow regex pre-pass for um/uh only remains a possible future optimization, not implemented.
- **Cleanup quality, current state**: no hallucination in any tested prompt (a real fix vs. the ONNX attempt). Reliably strips "um"/"uh" and fixes end punctuation. Inconsistently catches "so"/"like" (ambiguous words — the model is being appropriately cautious rather than wrong) and inconsistent on start-of-sentence capitalization. User said this quality bar is acceptable.
- **Resident, not load-on-demand**: both models preload at app startup and stay in memory for the life of the process (~1.66GB for cleanup + whisper's smaller footprint). Chosen over load-per-dictation because the RAM cost dropped to a reasonable level once the model size was cut to 1.5B, and residency keeps latency low (~1.1s per cleanup call vs ~2.3-2.6s if loaded fresh each time).
- **Not an always-running background service**: user clarified they don't always dictate and doesn't want either model resident in RAM when not in use. So the app is **launched on demand**, not auto-started with Windows. A desktop shortcut (`red-shark.lnk`, wired to `scripts/launch.bat`) exists for quick launch — minimized window (not fully console-less), specifically so the Ctrl+C shutdown fallback stays available even though right-click on the tray icon has never been confirmed reliable (see Outstanding).
- **Windows Job Object for the cleanup subprocess**: found during quick-launch testing that force-killing the app (as a user closing it via Task Manager would) orphaned `llama-server.exe`, silently holding ~1.66GB RAM. Fixed with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` — Windows now kills the subprocess automatically whenever the parent exits or is force-killed, by any means. Verified with a real (non-mocked) test that actually closes a job handle and confirms the child dies.

## Real Bugs Found and Fixed This Session (all covered by regression tests)

- ctypes 64-bit handle truncation in the keyboard hook (`GetModuleHandleW` returning garbage without explicit `restype`)
- Undersized `INPUT` struct in `SendInput` (union needs `MOUSEINPUT` included for correct sizeof, even though only `KEYBDINPUT` is used)
- Deadlock: `inject()`'s `SendInput` call re-enters the global keyboard hook on the same thread for its own synthetic keystrokes, which used to try to reacquire a non-reentrant lock
- Timer-per-keydown-repeat: Windows fires ~30 keydown events/sec for a held key; the hook used to schedule a new `threading.Timer` (and thus a new OS thread) on every single one
- Truncation on injected text: sending a whole sentence as one `SendInput` burst could drop/garble characters in some apps; fixed with a small per-character delay
- Non-BMP Unicode (emoji) silently broke in `inject()` since `wScan` is 16-bit; fixed via UTF-16 surrogate pairs
- `AudioRecorder.stop_recording()` crashed with `AttributeError` if called before `start_recording()` finished (or hung) — found via automated testing where real mic access hangs in this sandboxed environment; fixed defensively regardless of root cause

## Outstanding / What's Left

- **The cleanup-layer live voice test has not been done by the user.** Everything is verified via real synthetic-input testing (real transcribe, real cleanup server, mocked-or-verified injection) from this session, but the actual "hold Ctrl+Shift, speak with filler words, see the cleaned result land correctly" experience needs the user at the keyboard and mic — this environment cannot drive real microphone input (confirmed: attempts hang, not just fail).
- **Tray icon right-click has never been confirmed working.** Diagnosed as a likely pystray-on-Windows `SetForegroundWindow` flakiness (same class of issue hit with `SendInput` focus-stealing in this environment), but no code fix was applied — it's third-party library internals. The Ctrl+C/Ctrl+Break shutdown path was added specifically as a reliable fallback in case this stays broken. **User should confirm whether right-click actually works** on a real launch; if not, decide whether it's worth investigating further or living with Ctrl+C as the primary quit method.
- **Phase 3 (Packaging & Daily-Use Polish) has not been started**: tray icon pause/resume controls, a proper PyInstaller build (currently only runs from the dev venv), optional run-on-login. Given the "launch on demand, not always-running" clarification, run-on-login is probably *not* wanted — worth confirming before doing that task.
- **PRD Success Criteria checklist** (`PRD.md`) has not been formally walked through and checked off end-to-end by the user.
- Model download step (`scripts/download_models.py`) has only been tested by this session's own runs (which happened to already have most things cached/present) — a genuinely clean-machine run (nothing downloaded yet) has not been tested start to finish.
- `bin/llamacpp/` and `models/` are gitignored (large binaries/weights) — a fresh clone needs `pip install -r requirements.txt` **and** `python scripts/download_models.py` before first run. This isn't currently written down anywhere user-facing (no README yet).

## How to Run

```
cd C:\Users\avioh\red-shark
.\.venv\Scripts\python.exe -m dictate          # foreground, for debugging (see dictate.log)
```
or double-click the `red-shark` shortcut on the Desktop for normal quick-launch use (minimized window).

Quit via the tray icon's Quit item, or Ctrl+C / closing the console window if it's not minimized-and-forgotten.

## How to Test

```
.\.venv\Scripts\python.exe -m pytest -q        # 51 tests as of this session
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```
