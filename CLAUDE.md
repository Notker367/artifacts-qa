# Artifacts QA Sandbox

## Goal
This repository is a Python QA sandbox for Artifacts MMO API.
It is used to learn the API, automate stateful scenarios, and build readable pytest-based checks.

## Stack
- Python
- pytest
- requests
- python-dotenv

## Project rules
- Keep everything simple and readable.
- Do not overengineer.
- Do not introduce async, pydantic, or extra frameworks unless explicitly requested.
- Use the legacy repository only as reference, not as code to copy blindly.
- Put HTTP logic in `clients/`.
- Keep tests focused on behavior and state transitions, not implementation details.
- Prefer small helpers over generic abstractions.

## Structure
- `clients/artifacts_client.py` — thin wrapper around requests.Session
- `tests/conftest.py` — session-scoped fixtures: client, character_name
- `tests/` — test files per domain

## Testing focus
Prioritize these scenario types:
1. smoke checks for basic GET/POST behavior
2. stateful flows (move -> fight -> bank -> continue)
3. negative cases using documented game/API errors
4. cooldown-aware execution
5. inventory/bank consistency
6. trading/task/event flows only after core actions are stable

## Important game assumptions
- Artifacts is an API-first sandbox MMORPG: every meaningful in-game action is done through HTTP endpoints.
- One account can control up to 5 characters.
- Character actions are POST requests under `/my/{name}/action/...`.
- Most action responses include both action result and cooldown data.
- Sending a new action during cooldown should be treated as an expected game rule, not as random failure.

## Key API facts
- Base URL: https://api.artifactsmmo.com
- Auth: `Authorization: Bearer <token>`
- Responses: `{"data": {...}}`

## Common status codes

| Code | Meaning |
|------|---------|
| 200  | OK |
| 404  | Not found |
| 422  | Unprocessable (bad input) |
| 486  | Character locked |
| 490  | Already at destination |
| 497  | Inventory full |
| 498  | Character not found |
| 499  | On cooldown |

## Environment
Expected env vars:
- ARTIFACTS_BASE_URL
- ARTIFACTS_TOKEN
- ARTIFACTS_CHARACTER

## Before writing tests
Always check:
- whether the action requires auth
- whether the character is on the correct map
- whether inventory space is needed
- whether the character is in cooldown
- whether the scenario changes persistent state

## Conventions
- Tests accept multiple valid status codes where game state matters (cooldown, position)
- No mocking — tests hit the real API
- Keep tests simple and readable

## Reference
Read `docs/artifacts_context.md` before expanding coverage.
