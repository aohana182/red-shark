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

### 2026-08-16 — Session 2 continued: Phase 3 (tray controls + PyInstaller build)

**Task 10 (tray controls)**: added Pause/Resume to the tray menu and a 3-state icon (idle=red, recording=red+white ring, paused=gray). Hotkey holds are ignored while paused; a hold that already started before a pause toggle still stops correctly (icon/mic never leak — see the `test_icon_reverts_to_paused_after_stop_if_paused_meanwhile` test, which specifically guards the mid-hold-toggle race). Quit and the Ctrl+C/console-close paths now both explicitly release the mic. Found and fixed a real test-infrastructure bug along the way: `pystray.Icon`'s Win32 backend names its window class using `id(self)`, which CPython can reuse after garbage collection — constructing many real `pystray.Icon` instances across a pytest run (10+ `App()` calls already existed) was a latent "Class already exists" WinError waiting to happen, and this task's added tests tipped it over into an actual failure. Fixed by giving `App` an injectable `icon_factory` (mirrors `AudioRecorder`'s existing `stream_factory` pattern) and a `FakeIcon` test double, same rationale as faking `sounddevice` in `tests/test_audio.py`.

**Task 11 (PyInstaller build)**: added `dictate.spec` (single-folder/onedir build). Had to fix `config.py`'s `PROJECT_ROOT` first -- it was derived from `__file__`, which points inside the frozen bundle once packaged, not next to the actual exe. Now branches on `sys.frozen`: uses `Path(sys.executable).parent` when frozen, the old `__file__`-based logic otherwise. Actually built and ran the exe this session (not just written the spec): copied `models/` and `bin/` alongside `dist/dictate/dictate.exe` (per the "not bundled, sits alongside" design), launched it standalone (no venv in the invocation), and confirmed via `dictate.log` that whisper preload, the cleanup LLM subprocess, the tray icon, and the keyboard hook all start correctly. Also force-killed the running exe with `taskkill /F` and confirmed the orphaned `llama-server.exe` still gets cleaned up by the Job Object in the packaged build, not just from source. Build artifacts (`dist/`, `build/`) were deleted after verification -- gitignored, reproducible via `pyinstaller dictate.spec`.

**Task 12 (run-on-login)**: explicitly declined by the user when asked directly. Consistent with the Session 1 "launch on demand" decision.

## Outstanding / What's Left

- **PRD Success Criteria checklist** (`PRD.md`) has not been formally walked through and checked off end-to-end by the user.
- Model download step (`scripts/download_models.py`) has only been tested by this session's own runs (which happened to already have most things cached/present) — a genuinely clean-machine run (nothing downloaded yet) has not been tested start to finish.
- `bin/llamacpp/` and `models/` are gitignored (large binaries/weights) — a fresh clone needs `pip install -r requirements.txt` **and** `python scripts/download_models.py` before first run. Now documented in `README.md`.
- **The local cleanup model isn't fully deterministic even at temperature 0.0.** Confirmed while writing `tests/test_cleanup_quality.py` (2026-08-16): the same input to `cleanup()` occasionally produces different output across separate calls. Most likely CPU multi-threaded floating-point non-associativity in llama.cpp, not a code bug. Means the cleanup tests carry a small amount of inherent flakiness — acceptable for now, not investigated further.

### 2026-08-16 — Session 2: live voice test, cleanup-prompt bug fix, regression tests

**What happened**: user ran the first real live voice tests since the cleanup layer was built. Found two things:

1. **Tray icon right-click quit — confirmed working.** No longer an open question; Ctrl+C remains a fallback, not the primary method. `README.md` updated.
2. **A real bug in the cleanup LLM**: comparing raw whisper transcripts to cleaned/injected output (via `dictate.log`) showed the cleanup model was silently deleting whole clauses of real content, not just trimming filler — e.g. a genuine rhetorical question ("You know the answer already, right?") and a real statement ("I always mix those up") vanished entirely. Root cause: the system prompt in `dictate/cleanup.py` listed "like"/"you know" as unconditional filler words (no distinction between disfluency-usage and real-content-usage), and had no rule forbidding clause/sentence deletion.

**Fix** (commit `6e3c8fa`): rewrote the system prompt — explicit rule that "um"/"uh" are always safe to strip, "like"/"you know"/"right" only count as filler when they carry no content, and a hard "never delete a clause carrying real information" rule, anchored with two few-shot examples. Took 4 prompt iterations to find the balance; the model tends to overcorrect toward "touch nothing" if the anti-deletion framing is too strong, so filler-stripping is still inconsistent (especially mid-sentence "um"/"uh") — accepted as a real limitation of the 1.5B model, not something more prompt tuning fixed (tested explicitly).

**Regression tests added** (commit `7ae26b6`): `tests/test_cleanup_quality.py`, 3 real-model integration tests (skipped if the model/binary aren't downloaded). Followed the Prove-It pattern properly — reproduced the bug first using the *actual* whisper transcript captured in `dictate.log`, confirmed 2 of 3 tests failed against the pre-fix prompt (temporarily restored via `git checkout`, then reverted), then confirmed all 3 pass against the fix. Suite is now 54 tests total.

**Still true**: setup steps (venv, `download_models.py` on a genuinely clean machine) still haven't been tested from a truly clean checkout.

### 2026-08-20 — Session 3: first real launch, Smart App Control block, av-stub fix, README rewrite

**What happened**: user's actual first attempt to launch the app. Two problems surfaced:

1. **Desktop shortcut lived on a OneDrive-redirected path** (`C:\Users\avioh\OneDrive\Desktop`, via Windows Known Folder Backup — not something red-shark did) and the user doesn't use the Desktop at all. Moved `red-shark.lnk` into the project root instead (same target: `scripts\launch.bat`, minimized), removed the OneDrive copy, added `*.lnk` to `.gitignore`.
2. **App wouldn't launch at all**: Windows 11 **Smart App Control** (confirmed enabled/enforced via `HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy!VerifiedAndReputablePolicyState = 1`) was blocking `av`'s compiled `frame.pyd` (`av` is a `faster-whisper` dependency, pulled in via `from faster_whisper.audio import decode_audio`). Confirmed via the exact CodeIntegrity event log entry (event ID 3077): "did not meet the Enterprise signing level requirements." SAC has no per-app allowlist for regular users — the block is real and not something a config tweak fixes.

**Root-caused before touching anything**: read `faster_whisper`'s actual installed source and confirmed `decode_audio()` (the only function that touches `av`) is never called by this app — `transcribe()` always passes an already-decoded numpy array, and `faster_whisper/transcribe.py` explicitly skips `decode_audio()` when the input is already an `np.ndarray`. The crash was purely from the unconditional `import av` at the top of `faster_whisper/audio.py`, not from any actual use of it.

**Fix** (commit `78b3e46`): `dictate/_av_stub.py` registers a stub `av` module (and its `av.audio`/`av.audio.resampler`/`av.audio.fifo`/`av.error` submodules) in `sys.modules` before `faster_whisper` is imported in `transcribe.py`. Real `av` never loads; stubbed functions raise if ever actually called, as a tripwire in case a future code path genuinely needs real audio decoding. Lives entirely in red-shark's own source — no site-packages edits, no admin rights, no changes to Windows security settings.

**User explicitly declined** turning off Smart App Control (irreversible without a clean Windows reinstall) and declined swapping the STT library/model — wanted a fix that touched neither. This was the only option that satisfied both constraints.

**Verified**: full pytest suite (67/67, including the real whisper-transcription fixture test which exercises the actual import path), `ruff check` + `ruff format --check` clean, and a live `python -m dictate` run — whisper preload, cleanup LLM subprocess, tray icon, and keyboard hook all started successfully, no orphaned `llama-server.exe` after shutdown (confirmed via `tasklist`).

**Live voice test, cold machine, first ever use**: worked end to end — dictated text landed at the cursor correctly (confirmed via `dictate.log`, since this session's own instructions to Claude were dictated through red-shark itself). Some filler-word/distortion artifacts noted by the user as expected and tolerable, consistent with the known "inconsistent on ambiguous fillers" limitation from Session 2 — not a new bug.

**README.md rewritten** (same commit as below): added a "How it works" pipeline diagram (hotkey → audio → transcribe → cleanup → inject, naming the actual module per stage), a "Known limitations" section (filler inconsistency, cleanup non-determinism, cold-start expectations), and a "Troubleshooting" section documenting the Smart App Control issue for future reference (in case it recurs after a `faster_whisper` version bump, or hits a different machine with SAC enabled). Quick start updated to reference the project-root shortcut instead of the old Desktop one.

**Follow-up, same session**: user reported the shortcut still showed a visible terminal/log window, which they found unnecessary. Root cause: `.bat` files always run through `cmd.exe` (a console-subsystem process); the shortcut's WindowStyle=minimized hint on a `.bat` target isn't reliably honored, especially with Windows Terminal as the default host on Windows 11 -- this superseded the Session 1 decision to route through a `.bat`/console specifically to keep a Ctrl+C fallback, which was written before tray-icon Quit was confirmed reliable (it since was, in Session 2).

**Fix**: repointed `red-shark.lnk` directly at `.venv\Scripts\pythonw.exe -m dictate` (windowless Python interpreter), bypassing `cmd.exe`/`launch.bat` entirely -- Windows never allocates a console for a GUI-subsystem exe, so there's no window to (fail to) minimize. `scripts\launch.bat` updated to call `pythonw.exe` too, kept as an alternative entry point. Also fixed `_setup_logging()` in `__main__.py`: under `pythonw.exe`, `sys.stderr` is `None` (not just closed), so the console `StreamHandler` would have crashed on the first log call -- it's now only added when a real stream exists (i.e. when launched from an actual terminal for debugging); `dictate.log` file logging is unaffected either way. Tray-icon Quit is now the only shutdown path when launched via the shortcut (no console to Ctrl+C) -- acceptable since it's been confirmed reliable, and the Job Object still guarantees `llama-server.exe` cleanup even on a hard kill.

**Verified**: full pytest suite (67/67), ruff clean, and a live run via `pythonw.exe -m dictate` -- preload, hotkey hook, tray icon, and cleanup subprocess all started correctly; force-kill still cleaned up the orphaned `llama-server.exe` via the Job Object.

**Next**: browser/VS Code injection testing, a genuinely clean-machine `download_models.py` run, and final `PRD.md` checkpoint sign-off are all still open — same as end of Session 2.

**Update, same session**: PRD Success Criteria checklist walked and updated in `PRD.md` — 5 of 7 confirmed, 2 partial (browser/VS Code untested; offline verified via `HF_HUB_OFFLINE=1` rather than a hard firewall block, since this environment has no admin rights to add one). **User is making this repo public.** Ran `/package-repo`: added LICENSE (MIT), CONTRIBUTING.md, GitHub PR/issue templates, AGENTS.md, restructured README with a Resource usage section. Full git history scanned for secrets before going public (clean). Caught and removed one thing before it shipped: an AGENTS.md draft line describing the real embedded-GitHub-token exposure on this dev machine — real operational security info, not project context, doesn't belong in a public repo.

## How to Run

```
cd C:\Users\avioh\red-shark
.\.venv\Scripts\python.exe -m dictate          # foreground, for debugging (see dictate.log)
```
or double-click the `red-shark` shortcut on the Desktop for normal quick-launch use (minimized window).

Quit via the tray icon's Quit item, or Ctrl+C / closing the console window if it's not minimized-and-forgotten.

## How to Test

```
.\.venv\Scripts\python.exe -m pytest -q        # 67 tests as of this session
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

### 2026-09-05 — Session 4: dead hotkey root-caused from the log, whisper bumped, cleanup prompt hardened

**Trigger**: user reported "the quality went to shit" and, mid-session, that dictation had stopped reaching the text box entirely.

**The hotkey was dead, and the log was the only evidence.** `dictate.log` had grown to 24MB / 368k lines, of which 367k were raw keystroke DEBUG lines. Filtering those left 731 real lines, which showed the pipeline logger (`__main__`) going **completely silent after 13:22:22** while `dictate.hotkey` kept logging keystrokes normally. Two textbook-valid holds (Ctrl+Shift for 5.2s and 7.2s, no third key) produced nothing at all.

**How it was diagnosed** (worth repeating — guessing would have failed here):
1. Extracted the exact key-event stream from the log and **replayed it through the real `HotkeyStateMachine`**. The replay said both holds *should* have armed — so the logged input was valid and the state machine's own logic wasn't obviously at fault.
2. Ran the arming path (state machine + real `threading.Timer`) 300x in isolation looking for an early-fire race on `now >= self._armed_at`. 0/300 failures — not the cause.
3. `py-spy dump` on the live process: hook thread idle in `GetMessageW`, no deadlock, no leaked Timer threads, 5 Python threads total. The process was **healthy and idle, just not arming**.

**Two real bugs found, both reproduced before fixing** (`scratchpad/proveit.py` pattern: set `_modifier_state = None` to restore exact pre-fix semantics, assert failure, then assert pass):

1. **`_SUPPRESSED` was a terminal state.** Its only exit was `elif not self._ctrl_down and not self._shift_down`, both flags being accumulated purely from hook events. Windows drops modifier key-ups whenever focus moves mid-hold — and the log shows the user hitting **Win+Space (keyboard layout switch)** and Alt+Tab repeatedly, plus several `key up: vk=0xA2` events with no matching key-down. One swallowed key-up pins a flag `True` forever, and the hotkey never arms again for the life of the process. **This is what killed dictation.**
2. **Stale flags caused phantom arms.** At 13:22:22 a bare *Ctrl tap* armed the mic and captured 0 samples ("empty audio buffer") because a Shift key-up from two seconds earlier had never been delivered.

**Fix**: an injectable `modifier_state` probe (`GetAsyncKeyState`, real physical key state) consulted at the two points where the tracked flags were being trusted — `on_tick` won't arm unless both modifiers are genuinely held, and `key_up` resyncs the flags from reality, which makes `_SUPPRESSED` escapable again. Injected rather than called directly so `HotkeyStateMachine` stays a pure testable unit; `None` preserves the old flag-only behaviour, which is what all the pre-existing tests use.

**Why it was invisible**: `_hook_proc` had no try/except. `__main__.py` already documented this exact hazard for the `_on_start`/`_on_stop`/`_on_cancel` callbacks, but the guard sat one level too low — an exception in the hook proc's own body (or in the `Timer` thread) is swallowed by ctypes into a `sys.stderr` that is `None` under `pythonw.exe`, so it vanishes with zero trace while the hook keeps running. Both boundaries now log properly. **Any future "hotkey just stopped working" will leave a traceback in `dictate.log`.**

**Whisper `tiny.en` → `base.en`.** Real mis-hearings from today's log: "WhatsApp"→"what's up", "bot"→"boat"/"board", "Telegram IDs"→"Telegram ideas", "I can provision"→"icon provision", "a list of numbers"→"lots of numbers". **Important caveat, don't lose this**: I benchmarked tiny/base/small on synthesized audio of those exact phrases and **all three scored 9/9** — clean TTS audio does not reproduce the failure at all, so that test could not discriminate accuracy. The change is justified on robustness to real microphone speech, not on measured accuracy. What the benchmark *did* settle is latency on this CPU: tiny 6.9x realtime, base 3.8x, **small only 1.3x** — small.en is too slow to sit between a key release and text appearing. **Still unverified against Avi's actual voice.** Retaining a debug copy of the audio would make the next quality complaint diagnosable; deliberately not added (privacy surface, not asked for).

**Cleanup prompt: a new failure mode, not the Session 2 one.** At 13:17 the model turned a genuine question into a negated statement of fact and invented an ending for a clause the mic had cut off mid-word: `"...What about WhatsApp? Do I need to have a user-facing page with the QR codes for"` → `"...but I don't have a user-facing page with the QR codes for WhatsApp."` A whole sentence and a question both vanished. Note the Session 2 anti-deletion rules were already in place and did not prevent this — the missing rules were about **sentence type** and **truncated input**, not deletion.

Added two rules (a question stays a question, never negate, never merge/drop sentences; if the text stops mid-sentence LEAVE IT STOPPED, no invented ending, no reordering) plus a few-shot example built from the real failure. Reproduced the bug deterministically against the live server first, then confirmed the fix **5/5 runs** (this model is known non-deterministic even at temperature 0, so single-run confirmation isn't enough here).

**Statistical note**: the cleanup layer has *not* measurably regressed — rate of change is flat across every session (~50% of lines altered, ~20% shrunk >10%, on 08-20, 08-25, 08-26 and 09-05 alike). Today's failures were qualitatively worse, not more frequent. The bigger driver of "quality went to shit" was STT, not cleanup.

**Keystroke logging is now opt-in** (`REDSHARK_LOG_KEYSTROKES=1`). It had been unconditionally on at DEBUG since the beginning, making `dictate.log` a plaintext keylogger of everything typed in every app — passwords included — sitting in the project root. Gitignored and never committed (history was re-checked), so nothing leaked publicly, but the local file is a real liability.

**Verified**: 74 tests passing (67 → +4 hotkey regression, +3 cleanup quality), `ruff check` and `ruff format --check` clean.

**Live verification (same session, after the user quit and relaunched)**: confirmed working end to end. A real 3.4s hold armed and released normally -- the exact thing that was dead -- and the full pipeline ran: `transcribed: 'So, check, check, one, two, checking longer.'` -> `cleaned: 'So, check, one, two, checking longer.'` -> `injected 37 characters`. Keystroke logging confirmed off: **zero** key lines, 1074 bytes after a full session against 24MB before. The old 24MB keylog was truncated in place (it could not be deleted while held open).

Timings on base.en's first call: 1.5s transcribe for 3.4s audio (~2.3x realtime, cold), 3.4s cleanup. The cleanup number is well above the ~1.1s baseline because it was that server's first request -- worth watching, not yet a known regression.

**Still genuinely unproven**: whether base.en actually mishears less than tiny.en *on Avi's voice*. The synthesized-audio benchmark could not discriminate (9/9 on all three sizes). If "WhatsApp" still comes out as "what's up", small.en is the next lever, at a real latency cost (1.3x realtime).

**Open**: PR #1 (`fix/dead-hotkey-and-dictation-quality` -> master) is pushed and passing but **not merged** -- master still has the dead-hotkey code.
