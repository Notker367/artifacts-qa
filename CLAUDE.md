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
```
clients/artifacts_client.py   — thin wrapper around requests.Session
services/                     — domain helpers (one file per domain)
  cooldown.py                 — wait_for_cooldown, parse_cooldown, remaining_seconds
  errors.py                   — all API error codes as constants
  movement.py                 — get_position, move_character
  gathering.py                — gather, parse_gathered_items
  inventory.py                — get_inventory, free_slots, find_item, inventory_delta
  bank.py                     — deposit_item, withdraw_item, deposit_gold, bank_delta
  rest.py                     — rest, get_hp, is_full_hp
  combat.py                   — fight, parse_fight_result, is_win, is_loss
tests/
  conftest.py                 — session-scoped fixtures: client, character_name
  test_smoke.py               — fast endpoint reachability checks, one per domain
  test_*.py                   — stateful tests per domain
docs/
  artifacts_context.md        — game mechanics reference
  implementation_backlog.md   — full phase roadmap
  roles_and_optimization.md   — multi-character role model and dispatch strategy
```

## Testing focus
Prioritize these scenario types:
1. smoke checks for basic GET/POST behavior (`test_smoke.py`)
2. stateful flows (move → fight → bank → continue)
3. negative cases using documented game/API errors
4. cooldown-aware execution
5. inventory/bank consistency
6. trading/task/event flows only after core actions are stable

## Test layers

### Smoke tests (`test_smoke.py`)
- Fast, no `wait_for_cooldown`, no state assertions
- Accept full range of valid game codes (200, 490, 499, etc.)
- One test per domain endpoint
- Add a smoke test when adding a new domain

### Stateful tests (`test_*.py`)
- Call `wait_for_cooldown` before every action
- Assert concrete state transitions (delta, position, HP)
- Never skip on 499 — always wait and retry

### Long tests (`@pytest.mark.long`)
- Multi-step scenarios that take minutes (inventory fill, farm loops)
- Excluded from default `pytest` run via `addopts = -m "not long"`
- Run with `pytest -m long` for overnight / manual sessions

## Important game assumptions
- Artifacts is an API-first sandbox MMORPG: every meaningful in-game action is done through HTTP endpoints.
- One account can control up to 5 characters.
- Character actions are POST requests under `/my/{name}/action/...`.
- Most action responses include both action result and cooldown data.
- Sending a new action during cooldown returns 499 — expected game rule, not a failure.
- Each character is a single-threaded worker: one action at a time, one cooldown.
- Bank is account-level — shared across all characters.

## Key API facts
- Base URL: https://api.artifactsmmo.com
- Auth: `Authorization: Bearer <token>`
- Responses: `{"data": {...}}`
- Fight result field: `"win"` or `"loss"` (not `"lose"`)
- Bank deposit/withdraw: `/action/bank/deposit/item` and `/action/bank/withdraw/item`, list payload
- All characters: `GET /my/characters`

## Common status codes

| Code | Meaning |
|------|---------|
| 200  | OK |
| 404  | Not found |
| 422  | Unprocessable (bad input) |
| 486  | Character locked |
| 490  | Already at destination |
| 492  | Not enough gold |
| 497  | Inventory full |
| 498  | Character not found |
| 499  | On cooldown |
| 598  | No resource on this tile |

## Known map tiles

Tile data is cached in `data/maps.json` via `services/map_cache.py`.
Run `python scripts/discover_map.py` to refresh. Key tiles below for quick reference.

### Infrastructure
| Location | Coordinates | Notes |
|----------|-------------|-------|
| Bank | (4, 1) | nearest bank from start |
| Bank | (7, 13) | forest area |
| Bank | (-2, 19) | desert island |
| Taskmaster (monsters) | (1, 2) | accept/complete monster tasks |
| Taskmaster (items) | (4, 13) | accept/complete item tasks |

### Combat (monsters)
| Monster | Coordinates | Notes |
|---------|-------------|-------|
| Chicken | (0, 1) | level 1, 60 HP |
| Cow | (0, 2) | level 1 |
| Green Slime | (0, -1) (3, -2) | level 1–2 |
| Wolf | (-3, 0) (-2, 1) | higher level |

### Mining
| Resource | Coordinates |
|----------|-------------|
| copper_rocks | (2, 0) |
| iron_rocks | (1, 7) |
| coal_rocks | (1, 6) |
| gold_rocks | (3, -5) (5, -4) — underground |
| mithril_rocks | (-3, 4) (-2, 5) — underground |

### Woodcutting
| Resource | Coordinates |
|----------|-------------|
| ash_tree | (-1, 0) (6, 1) |
| birch_tree | (3, 5) (-1, 6) |
| spruce_tree | (2, 6) (1, 9) |
| maple_tree | (1, 12) (4, 14) |

### Fishing
| Resource | Coordinates |
|----------|-------------|
| gudgeon_spot | (4, 2) |
| shrimp_spot | (5, 2) |
| salmon_spot | (-3, -4) (-2, -4) |
| trout_spot | (7, 12) |
| bass_spot | (6, 12) |

### Alchemy (plants)
| Resource | Coordinates |
|----------|-------------|
| sunflower_field | (2, 2) |
| glowstem | (1, 10) |
| nettle | (7, 14) |
| torch_cactus | (-3, 18) (0, 19) |

## Cooldown facts
- Gathering cooldown: ~30s
- Fight cooldown: ~57s (varies with haste)
- Death penalty cooldown: ~100s
- Rest cooldown: ~3s
- `wait_for_cooldown` default max_wait: 120s

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
Read `docs/roles_and_optimization.md` before working on multi-character features.

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
- `v0.3.x` — Phase 3: Production chains (character profile, crafting, tasks, multi-char, scenario manager)
- `v0.4.x` — Phase 4: Expansion (grand exchange, events, achievements)
