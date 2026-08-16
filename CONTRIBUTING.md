# Contributing

## Setup

```sh
git clone https://github.com/aohana182/red-shark.git
cd red-shark
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts\download_models.py
.venv\Scripts\python.exe -m pytest -q
```

## Workflow

1. Branch from `master`: `git checkout -b feat/your-feature`
2. Make changes and run tests
3. Commit with [Conventional Commits](https://www.conventionalcommits.org): `feat(scope): description`
4. Open a PR against `master`

## Commit format

```
type(scope): subject (max 72 chars)

- What changed
- Why it matters
- How verified
```

Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`

## Code style

- `.venv\Scripts\python.exe -m ruff check .` — lint
- `.venv\Scripts\python.exe -m ruff format --check .` — format check
- Flat, minimal modules — one responsibility per file, no class hierarchies where a function does the job
- Type hints on all function signatures
- No abstraction layers for hypothetical future backends — call `faster-whisper` and the cleanup server directly

## Testing

- `tests/test_cleanup_quality.py` needs the downloaded cleanup model/binary (`scripts\download_models.py`) — it skips automatically if they're not present
- No automated test for actual audio/model output quality beyond the regression cases already covered; anything touching the cleanup prompt or transcription accuracy should be spot-checked manually and documented in `memory.md`
