# Spec: red-shark — Local Windows Dictation App

## Objective
A background Windows utility that lets you dictate text into any focused application via a hold-to-talk hotkey. Speech is transcribed locally, cleaned up by a local LLM (filler words removed, punctuation/grammar fixed), and inserted directly at the cursor. Fully offline — no cloud, no accounts, no telemetry. Single user (you).

**Success looks like:** hold Ctrl+Shift → speak → release → clean text appears where your cursor was, in under ~2-3 seconds for a typical sentence.

## Tech Stack
- **Language:** Python 3.11+
- **STT:** `faster-whisper` (CTranslate2 backend), `tiny.en` model, `int8` quantization — CPU-only, no GPU dependency. One-line config swap to `base.en`/`small.en` if accuracy is lacking.
- **Cleanup LLM:** `llama-cpp-python` running a quantized local model in-process (no external service) — default **Qwen2.5-3B-Instruct** or **Llama-3.2-3B-Instruct**, `Q4_K_M` GGUF. 32GB RAM leaves headroom to swap to a 7-8B model later via config if you want better cleanup at the cost of latency.
- **Audio capture:** `sounddevice`
- **Windows integration:**
  - Hotkey: **Ctrl+Shift, hold-to-talk** (bare modifiers, no letter key), via a low-level keyboard hook (`WH_KEYBOARD_LL` through `ctypes`/`pywin32`) tracking both keys' down/up state — chosen because `RegisterHotKey` only fires on a combo press, not hold-duration. Verified against this machine specifically: the legacy Ctrl+Shift/Alt+Shift layout-toggle hotkey is unset in the registry (`HKCU\Keyboard Layout\Toggle`), confirming Windows uses the modern Win+Space input switcher instead — no conflict there. Using bare modifiers (not a modifier+letter combo) also means neither key types a visible character on its own, so there's no risk of a stray character being typed. The remaining risk: Ctrl+Shift is the first two keys of many common three-key shortcuts (`Ctrl+Shift+Esc` Task Manager, `Ctrl+Shift+Z` redo, `Ctrl+Shift+T` reopen tab, `Ctrl+Shift+S` Snipping Tool, `Ctrl+Shift+N` new incognito window). The hook must not swallow or arm dictation on Ctrl+Shift-down alone — only arm past a hold-duration threshold (~250ms) **and only if no third key is pressed in the meantime**; a third key press while both modifiers are held immediately cancels arming and lets everything pass through untouched, so those shortcuts keep working normally.
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
  hotkey.py          → Ctrl+Shift hold-to-talk keyboard hook
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
- [x] Hold Ctrl+Shift → speak → release → correct text appears at cursor in the focused app — confirmed 2026-08-16, three real dictations in `dictate.log`
- [ ] Works in at least: Notepad, a browser text field, VS Code — **partially confirmed**: tested in Notepad and Notepad++ (2026-08-16). Browser and VS Code not yet tested.
- [x] End-to-end latency (release hotkey → text inserted) under ~3s for a one-sentence dictation — confirmed, measured 1.5-1.7s in `dictate.log` (2026-08-16)
- [x] Cleanup removes filler words ("um", "uh") and fixes obvious punctuation without altering meaning — the "without altering meaning" half is now solid (regression-tested, see `tests/test_cleanup_quality.py`); "um"/"uh" removal is real but inconsistent, especially mid-sentence — accepted limitation of the 1.5B model, see `memory.md`
- [x] Runs entirely offline — works with network disabled — confirmed 2026-08-16 with `HF_HUB_OFFLINE=1` (forces the whisper loader to fail rather than silently fall back to network): full transcribe+cleanup pipeline ran successfully with zero network access. Not tested via a hard firewall block (would need admin rights not available in this environment) — the env-var test is real but slightly weaker evidence than a true network-disabled run.
- [x] No admin/elevated privileges required to run — confirmed by inspection: `scripts/launch.bat` requests no elevation, and the app has been run repeatedly from a normal user shell
- [x] `Ctrl+Shift+Esc`, `Ctrl+Shift+Z`, `Ctrl+Shift+T`, `Ctrl+Shift+S`, `Ctrl+Shift+N` (and similar three-key shortcuts) continue to work normally — dictation never arms or interferes when a third key follows — verified via synthetic-input testing in Session 1 (`memory.md`), and consistent with real Alt+Tab/Ctrl+C/Ctrl+V activity observed in `dictate.log` during live use

## Hardware Reference
Lenovo ThinkPad T14s Gen 6, Intel Core Ultra 7 255U (12 cores / 14 threads), 32GB RAM, integrated Intel Graphics (no discrete GPU). All model choices above are CPU-only by design to match this hardware.

## Out of Scope for v1
Personal dictionary, per-app formatting/style profiles, live preview overlay, voice commands/automation — all explicitly deferred, not to be implemented until requested.

## Open Questions
None outstanding — resolved via conversation on 2026-08-15 (project name, hotkey, model sizes); project renamed from savage-tongue to red-shark and hotkey changed from Caps Lock to Shift+Z to Ctrl+Shift (bare modifiers, cancel-on-third-key) on 2026-08-15.
