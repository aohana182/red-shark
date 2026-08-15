# Implementation Plan: red-shark (Local Windows Dictation App)

## Overview
Build a background Windows utility, Ctrl+Shift hold-to-talk, that captures speech, transcribes it locally with faster-whisper, cleans it up with a local LLM, and types it into whatever app has focus. Fully offline, single user, no bells and whistles for v1. Built in three vertical slices: a working raw-dictation loop first (de-risks the hardest technical pieces — the keyboard hook and text injection), then the cleanup layer, then packaging for daily use.

## Architecture Decisions
- **Vertical slicing over horizontal**: Phase 1 delivers a complete, testable, useful path (raw dictation, no cleanup) before touching the LLM layer. This surfaces the two highest-risk unknowns — the low-level keyboard hook and `SendInput` reliability across real apps — as early as possible, per PRD boundaries ("ask first" on anything hotkey-related).
- **Hold-duration threshold + cancel-on-third-key on the hotkey hook (new, not in original PRD)**: Ctrl+Shift (bare modifiers) is the first two keys of common three-key shortcuts (`Ctrl+Shift+Esc`, `+Z`, `+T`, `+S`, `+N`). Arming dictation the instant both modifiers are down would break all of those. Task 2 implements a hold-duration threshold (~250ms) before arming, and cancels arming immediately if a third key is pressed while both modifiers are held — letting those shortcuts pass through untouched. This is an implementation detail within the already-agreed hotkey choice, not a hotkey change, but it materially changes what Task 2 has to do, so it's called out here. (Verified this machine specifically has no conflict with the legacy Ctrl+Shift layout-toggle hotkey — that registry key is unset, Windows uses Win+Space instead.)
- **Cleanup LLM built in parallel with Phase 1**: `cleanup.py` (Task 7) has no dependency on the hotkey/audio/inject chain, only on `config.py`. It can be developed and tested independently while Phase 1 lands, then wired in at Task 9.
- **No abstraction layers**: per PRD Code Style — faster-whisper and llama-cpp-python are called directly, no pluggable backend interface, since only one backend of each is ever planned.

## Task List

### Phase 1: Foundation — Raw Dictation Loop
- [x] Task 1: Project scaffolding & config
- [x] Task 2: Ctrl+Shift hold-to-talk keyboard hook (with hold-duration threshold + cancel-on-third-key)
- [x] Task 3: Audio capture on hold
- [x] Task 4: Whisper transcription
- [x] Task 5: Text injection via SendInput
- [x] Task 6: Wire the raw dictation loop end-to-end

### Checkpoint: Foundation
- [ ] Raw dictation loop works end-to-end in Notepad, a browser text field, and VS Code -- **needs live human test**, see below
- [ ] `Ctrl+Shift+Esc`/`+Z`/`+T`/`+S`/`+N` and similar shortcuts still work normally; dictation never arms when a third key follows -- **needs live human test**
- [x] All Phase 1 tests pass (21 unit tests, all green; full wiring verified with real transcribe against the synthesized fixture)
- [ ] Review with human before proceeding to the cleanup layer

### Phase 2: Cleanup Layer
- [ ] Task 7: Local LLM cleanup wrapper *(can be built in parallel with Phase 1, Tasks 2–5)*
- [ ] Task 8: Model download/setup step
- [ ] Task 9: Wire cleanup into the pipeline

### Checkpoint: Cleanup
- [ ] Full pipeline (hotkey → audio → transcribe → cleanup → inject) works end-to-end
- [ ] End-to-end latency measured and recorded; under ~3s target for a typical sentence
- [ ] Cleanup removes filler words without altering meaning, verified across several manual test sentences
- [ ] All PRD Success Criteria checked off
- [ ] Review with human before proceeding to packaging

### Phase 3: Packaging & Daily-Use Polish
- [ ] Task 10: Tray icon controls (pause/resume, recording-state indicator)
- [ ] Task 11: PyInstaller build
- [ ] Task 12: Run-on-login (optional, only if wanted)

### Checkpoint: Complete
- [ ] All PRD Success Criteria met
- [ ] Standalone build runs without the dev venv active
- [ ] Ready for daily use

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Low-level keyboard hook (ctypes `WH_KEYBOARD_LL`) is fiddly and easy to get subtly wrong | High | Build and validate Task 2 first, in isolation, before any other module; fall back to the `keyboard` library if raw ctypes proves too fragile |
| Ctrl+Shift arming logic blocks common three-key shortcuts (`Ctrl+Shift+Esc`/`Z`/`T`/`S`/`N`) | High | Hold-duration threshold + cancel-on-third-key — see Architecture Decisions. Verify explicitly at the Foundation checkpoint by exercising each of those shortcuts while the app is running |
| Local LLM cleanup latency exceeds the ~3s end-to-end target on CPU-only T14s hardware | Medium | Benchmark with real hardware as part of Task 7, before committing to the 3B model; drop to a smaller/more aggressive quantization if too slow |
| `faster-whisper tiny.en` accuracy too low for usable dictation | Medium | Model size is a one-line config swap (already designed into the PRD); escalate to `base.en`/`small.en` if the Foundation checkpoint reveals poor accuracy |
| `SendInput` injection fails or behaves oddly in certain apps (custom input handling, elevated windows) | Medium | Test across all three PRD-specified apps at the Foundation checkpoint; document any app-specific failures as known limitations rather than blocking progress |

## Open Questions
- Exact GGUF model source/repo for the cleanup LLM (Hugging Face link + quant filename) — needs to be pinned before Task 8 (model download step)
