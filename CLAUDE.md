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
Read `docs/implementation_backlog.md` before proposing architecture or implementation steps.

## Comments and naming
- Code comments are mandatory for helpers, fixtures, and any non-obvious logic.
- Use game-context terminology from `docs/artifacts_context.md` — not generic names.
- Good examples: `wait_for_cooldown`, `assert_fight_result`, `deposit_gold_to_bank`, `is_inventory_full`.
- Avoid: `handle_action`, `do_request`, `check_response`, `process_data`.
- Comment on *why* something works the way it does, not just *what* it does.

## Change approval workflow
- Before adding new code blocks or making mass edits — present the plan, explain the intent, wait for confirmation.
- Exception: small single-line fixes requested directly by the user.

## Commit structure
Format: `<type>(<scope>): <description>`

Types: `feat`, `test`, `fix`, `chore`, `docs`
Scopes: `infra`, `character`, `movement`, `gathering`, `inventory`, `bank`, `combat`, `rest`, `crafting`, `tasks`, `exchange`, `events`, `multi-char`

Version is tied to backlog phase:
- `v0.1.x` — Phase 1: Foundation (auth, logging, structure, error handling, cooldown, rate-limit)
- `v0.2.x` — Phase 2: Basic gameplay (movement, gathering, inventory, bank, rest, combat)
- `v0.3.x` — Phase 3: Production chains (crafting, tasks, scenario manager)
- `v0.4.x` — Phase 4: Multi-character and expansion (grand exchange, events, achievements)