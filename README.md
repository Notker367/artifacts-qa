# artifacts-qa

Python QA sandbox for [Artifacts MMO](https://artifactsmmo.com) API.
Built with `pytest` + `requests`. Every in-game action is an HTTP call — this project automates and validates them.

## Goal

- Learn the Artifacts MMO API through practical automation
- Build readable stateful test scenarios (move → fight → bank → continue)
- Create a foundation for multi-character orchestration later

## Stack

- Python 3.x
- pytest
- requests
- python-dotenv

## Project structure

```
clients/        # HTTP layer — thin wrapper around requests.Session
services/       # Domain logic — movement, combat, inventory, bank, etc.
tests/          # pytest test files, one file per domain
docs/           # Context, backlog, and API notes
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# fill in your token and character name
```

`.env` expects:
```
ARTIFACTS_BASE_URL=https://api.artifactsmmo.com
ARTIFACTS_TOKEN=your_token_here
ARTIFACTS_CHARACTER=your_character_name
```

## Run tests

```bash
pytest
pytest -v                    # verbose output
pytest tests/test_character.py  # single file
```

## Implementation phases

| Version | Phase | Status |
|---------|-------|--------|
| v0.1.x  | Foundation: auth, logging, error handling, cooldown | in progress |
| v0.2.x  | Basic gameplay: movement, gathering, inventory, bank, combat | planned |
| v0.3.x  | Production chains: crafting, tasks, scenario manager | planned |
| v0.4.x  | Multi-character and expansion | planned |

See `docs/implementation_backlog.md` for full details.

## API reference

- Docs: https://api.artifactsmmo.com/docs
- Auth: `Authorization: Bearer <token>`
- All responses: `{"data": {...}}`
