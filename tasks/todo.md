# Task List: red-shark

See `tasks/plan.md` for architecture decisions, risks, and phase checkpoints.

## Phase 1: Foundation — Raw Dictation Loop

## Task 1: Project scaffolding & config

**Description:** Create the `dictate/` package skeleton, `config.py` with constants (hotkey keys, whisper model name/quantization, sample rate, audio device, hold-duration threshold), `requirements.txt`, and `.gitignore` for `models/` and `.venv`.

**Acceptance criteria:**
- [ ] `python -m dictate` runs without ImportError (stub is fine)
- [ ] `requirements.txt` lists faster-whisper, sounddevice, pywin32, llama-cpp-python, pystray, pytest, ruff

**Verification:**
- [ ] `python -m dictate` runs without error
- [ ] `pip install -r requirements.txt` succeeds in a clean venv

**Dependencies:** None

**Files likely touched:**
- `dictate/__init__.py`
- `dictate/__main__.py` (stub)
- `dictate/config.py`
- `requirements.txt`
- `.gitignore`

**Estimated scope:** Small

---

## Task 2: Shift+Z hold-to-talk keyboard hook

**Description:** Implement `hotkey.py` using `WH_KEYBOARD_LL` via `ctypes`. Track Shift and Z down/up state. Only treat a hold past the configured threshold (~250ms) as dictation-start (fires `on_start`, swallows further Z events); releasing either key before the threshold lets the keystroke pass through normally (types a literal capital "Z"). Releasing after dictation has started fires `on_stop` and swallows the release too.

**Acceptance criteria:**
- [ ] Holding Shift+Z past the threshold triggers `on_start` exactly once per hold
- [ ] Releasing either key after `on_start` triggers `on_stop` exactly once
- [ ] A quick Shift+Z tap (under threshold) still types a literal "Z", not swallowed
- [ ] No "Z" character ever reaches the focused app during an armed dictation hold

**Verification:**
- [ ] `pytest` unit test simulating key event callbacks against the press/hold/release/threshold state machine (mocked event dispatch, not real OS input)
- [ ] Manual test: open Notepad, hold Shift+Z past threshold, confirm no "Z" typed and start/stop logged
- [ ] Manual test: open Notepad, quick-tap Shift+Z, confirm a literal "Z" is typed

**Dependencies:** Task 1

**Files likely touched:**
- `dictate/hotkey.py`
- `tests/test_hotkey.py`

**Estimated scope:** Medium — highest-risk task in the plan

---

## Task 3: Audio capture on hold

**Description:** `audio.py` using `sounddevice` to record from the default mic while the hotkey is held; returns a numpy array + sample rate on stop.

**Acceptance criteria:**
- [ ] `start_recording()` begins capture; `stop_recording()` stops and returns the audio buffer
- [ ] Buffer duration matches hold duration within reasonable tolerance

**Verification:**
- [ ] `pytest` test with a mocked `sounddevice` stream
- [ ] Manual test: record ~3s, save to WAV, play back, confirm audible speech

**Dependencies:** Task 1

**Files likely touched:**
- `dictate/audio.py`
- `tests/test_audio.py`

**Estimated scope:** Small

---

## Task 4: Whisper transcription

**Description:** `transcribe.py` wrapping `faster-whisper`. Loads `tiny.en`, `int8`, once at startup as a module-level singleton. `transcribe(audio, sample_rate) -> str`.

**Acceptance criteria:**
- [ ] Given a known short WAV fixture, returns text closely matching the expected transcript (spot-check, not exact-match — STT isn't fully deterministic across environments)

**Verification:**
- [ ] `pytest` test against `tests/fixtures/sample.wav`, asserting key words appear in the output
- [ ] Manual test with live mic input

**Dependencies:** Task 1

**Files likely touched:**
- `dictate/transcribe.py`
- `tests/test_transcribe.py`
- `tests/fixtures/sample.wav`

**Estimated scope:** Small

---

## Task 5: Text injection via SendInput

**Description:** `inject.py` using `SendInput` (`ctypes`) to type a given string into whatever window currently has focus.

**Acceptance criteria:**
- [ ] Given a string, characters appear in the focused window in order, including basic punctuation and capital letters

**Verification:**
- [ ] `pytest` test checks the `ctypes` call structure is well-formed (can't verify actual OS-level typing automatically)
- [ ] Manual test: focus Notepad, call `inject("Hello, world!")`, confirm correct output

**Dependencies:** Task 1

**Files likely touched:**
- `dictate/inject.py`
- `tests/test_inject.py`

**Estimated scope:** Small

---

## Task 6: Wire the raw dictation loop end-to-end

**Description:** `__main__.py` connects hotkey start/stop callbacks → audio capture → transcribe → inject directly (no cleanup yet), plus a bare `pystray` tray icon with a "Quit" option.

**Acceptance criteria:**
- [ ] Holding Shift+Z past threshold, speaking, releasing results in raw (uncleaned) transcription typed into the focused app
- [ ] App runs in the system tray and can be quit from there

**Verification:**
- [ ] Manual end-to-end smoke test in Notepad, a browser text field, and VS Code

**Dependencies:** Tasks 2, 3, 4, 5

**Files likely touched:**
- `dictate/__main__.py`

**Estimated scope:** Medium

---

## Checkpoint: After Tasks 1–6 (Foundation)
- [ ] Raw dictation loop works end-to-end in Notepad, a browser text field, and VS Code
- [ ] No stray "Z" typed on any armed hold; quick taps still type a literal "Z"
- [ ] All Phase 1 tests pass
- [ ] Review with human before proceeding to Phase 2

## Phase 2: Cleanup Layer

## Task 7: Local LLM cleanup wrapper

**Description:** `cleanup.py` using `llama-cpp-python`, loads a quantized Qwen2.5-3B-Instruct (or Llama-3.2-3B-Instruct) GGUF model once at startup. `cleanup(raw_text) -> str` applies a fixed prompt stripping filler words and fixing punctuation/grammar without changing meaning. Benchmark latency on the real T14s hardware as part of this task.

**Acceptance criteria:**
- [ ] Given raw text with filler words ("um, so, I think, uh, we should go"), returns cleaned text preserving meaning and removing fillers
- [ ] Does not hallucinate new content not present in the input
- [ ] Measured latency for a typical one-sentence input is recorded

**Verification:**
- [ ] `pytest` tests with raw→expected-pattern fixtures (substring/keyword checks, not exact match, given LLM non-determinism)
- [ ] Manual comparison of cleanup output against raw dictation quality

**Dependencies:** Task 1 (config for model path). Can be built in parallel with Phase 1, Tasks 2–5.

**Files likely touched:**
- `dictate/cleanup.py`
- `tests/test_cleanup.py`

**Estimated scope:** Medium

---

## Task 8: Model download/setup step

**Description:** A small setup script (or documented manual step) to download the GGUF cleanup model and whisper model files into `models/` (gitignored), referenced by `config.py` paths.

**Acceptance criteria:**
- [ ] Fresh clone + setup command results in `models/` populated with both required model files

**Verification:**
- [ ] Manual run of the setup script on a clean checkout

**Dependencies:** Task 7 (needs the exact model file/quant pinned first — see Open Questions in `plan.md`)

**Files likely touched:**
- `scripts/download_models.py` (or setup docs in README)
- `dictate/config.py` (path constants)

**Estimated scope:** Small

---

## Task 9: Wire cleanup into the pipeline

**Description:** Insert the `cleanup()` call between `transcribe()` and `inject()` in `__main__.py`.

**Acceptance criteria:**
- [ ] Dictated text is cleaned (fillers removed, punctuation fixed) before insertion

**Verification:**
- [ ] Manual end-to-end test in Notepad with intentionally filler-heavy speech
- [ ] End-to-end latency measured and confirmed under ~3s target

**Dependencies:** Tasks 6, 7, 8

**Files likely touched:**
- `dictate/__main__.py`

**Estimated scope:** XS

---

## Checkpoint: After Tasks 7–9 (Cleanup)
- [ ] Full pipeline (hotkey → audio → transcribe → cleanup → inject) works end-to-end
- [ ] End-to-end latency measured and recorded; under ~3s target
- [ ] Cleanup removes filler words without altering meaning, verified across several manual test sentences
- [ ] All PRD Success Criteria checked off
- [ ] Review with human before proceeding to Phase 3

## Phase 3: Packaging & Daily-Use Polish

## Task 10: Tray icon controls

**Description:** Expand the `pystray` tray icon beyond "Quit" to include a pause/resume dictation toggle and a status indicator (icon changes while recording).

**Acceptance criteria:**
- [ ] Tray icon shows idle/recording state
- [ ] Pause/resume works; hotkey is inert while paused
- [ ] Quit cleanly shuts down the hook and releases the mic

**Verification:**
- [ ] Manual test toggling pause/resume and confirming the hotkey is inert while paused

**Dependencies:** Task 9

**Files likely touched:**
- `dictate/__main__.py`

**Estimated scope:** Small

---

## Task 11: PyInstaller build

**Description:** Create `dictate.spec`, verify a single-folder build runs standalone without the dev venv, bundling a reference to `models/` (not embedding large model files in the exe — document that `models/` must sit alongside the built exe).

**Acceptance criteria:**
- [ ] Built exe runs on this machine without an active Python install/venv
- [ ] Full pipeline works from the built exe

**Verification:**
- [ ] Manual test running the built exe fresh, dictating a sentence

**Dependencies:** Task 10

**Files likely touched:**
- `dictate.spec`

**Estimated scope:** Medium

---

## Task 12: Run-on-login (optional)

**Description:** Startup folder shortcut creation, documented or scripted. Only implement if actually wanted — confirm before starting.

**Acceptance criteria:**
- [ ] App starts automatically on Windows login, if enabled

**Verification:**
- [ ] Manual test via logoff/login or restart

**Dependencies:** Task 11

**Files likely touched:**
- `scripts/install_startup.py` or README docs

**Estimated scope:** XS

---

## Checkpoint: Complete
- [ ] All PRD Success Criteria met
- [ ] Standalone build runs without the dev venv active
- [ ] Ready for daily use
