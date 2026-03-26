# Artifacts MMO context for QA

## What the game is
Artifacts is a sandbox MMORPG for developers where every action is an API call.
You control characters through HTTP, not through a traditional game client.
The game runs in seasons; each season lasts about 4 months and resets progress.

## Core mental model
- Account -> up to 5 characters
- Character -> stats, inventory, location, cooldown, gold, equipment
- World -> maps, monsters, resources, NPCs, events
- Economy -> bank, grand exchange, task rewards
- Progression -> combat, gathering, crafting, tasks, achievements

## API categories
- public data endpoints: characters, items, monsters, resources, maps, events, exchange data
- auth/account endpoints
- my/account data endpoints
- character action endpoints: `/my/{name}/action/...`

## Authentication
Authenticated endpoints require JWT Bearer token in the `Authorization` header.
Missing or invalid token produces auth-related 45x errors.
A common mistake is forgetting the `Bearer ` prefix.

## Cooldowns and action behavior
Every character action returns a result plus cooldown information.
If a character is still in cooldown, a new action should return error 499.
Cooldown is a core mechanic, not just rate limiting.

## Movement and maps
Not all maps are freely walkable.
Map access types include:
- standard
- blocked
- teleportation
- conditional

Movement tests must account for map conditions and current position.
Trying to move to the current map can return code 490.

## Combat
Fight is an action and is cooldown-based.
Combat depends on character stats, monster stats, equipment, and effects.
Haste reduces fight cooldown.
For multi-character fights, threat affects targeting behavior.

## Inventory and bank
Inventory size can be increased with bags equipped in the bag slot.
Inventory-full cases are important and documented as code 497.
Bank supports item deposit/withdraw, gold deposit/withdraw, and slot expansion.

## Grand Exchange
Trading requires being on a map with a Grand Exchange.
There is a hard limit of 100 active orders per account.

## Tasks
Tasks are random objectives that reward gold and task coins.
Current objective types:
- kill monsters
- deliver items

## Events
Events spawn exclusive monsters, resources, and NPCs for limited time.
Each event has spawn rate and duration.
Event-aware tests should not assume permanent availability.

## Useful documented error codes
- 422 invalid payload
- 429 too many requests
- 452 invalid token
- 453 token expired
- 454 token missing
- 490 character already on this map
- 497 character inventory full
- 498 character not found
- 499 character in cooldown

## Rate-limit groups
Artifacts documents 3 endpoint groups:
- account: 10/s, 500/h
- data: 20/s, 500/min, 10,000/h
- action: 20/2s, 500/min, 10,000/h

## QA priorities
Best first automated scenarios:
1. GET character by name
2. authenticated GET my characters
3. move success / move already-there
4. fight success / fight during cooldown
5. inventory-full handling
6. bank deposit/withdraw delta checks
7. task accept/complete flows
8. exchange and event scenarios only after basic stability