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
pytest                              # all fast tests (long tests excluded by default)
pytest -v                           # verbose output
pytest -v -s tests/test_movement.py # single file with live logs
pytest -m long                      # only long-running tests (overnight runs)
pytest -m ""                        # everything, including long tests
pytest -v -s -x tests/test_combat.py  # stop on first failure
```

Long tests (`@pytest.mark.long`) cover multi-step scenarios like inventory fill detection
or gather-many + bank deposit flows. They are excluded from the default `pytest` run.

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
