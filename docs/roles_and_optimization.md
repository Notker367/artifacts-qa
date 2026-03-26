# Roles & Optimization Strategy (Artifacts MMO)

## Purpose

This document defines how characters should be used to maximize efficiency.

This is NOT a static role system.
This is a dynamic optimization model based on:

- cooldown utilization
- action throughput
- bottleneck avoidance
- minimal tool switching
- parallel resource generation

---

## Core principle

Each character is a single-threaded worker:

1 character = 1 action queue = 1 cooldown

A character cannot:
- fight and gather
- gather and craft
- perform parallel actions

---

## Main optimization goal

Maximize total account efficiency:

maximize(progress per unit time)

NOT:
- maximize each character individually
- maximize specialization purity

---

## Critical constraints

### 1. Cooldowns differ significantly

- combat → medium (depends on turns)
- gathering → high (long cooldown)
- crafting → low (short cooldown)

Conclusion:

gathering is the main bottleneck
crafting is NOT a bottleneck

---

### 2. Tool slot limitation

Each character has one tool slot:

- axe → woodcutting
- pickaxe → mining
- net → fishing
- gloves → alchemy (gathering plants)

Switching tools:
- costs time
- complicates logic
- reduces efficiency

Conclusion:

DO NOT rely on tool switching
Prefer fixed tool per character

---

### 3. Shared bank

All characters share a bank.

This enables:
- central resource storage
- indirect cooperation
- decoupled roles

Conclusion:

roles can specialize because resources are shared

---

## Bottleneck theory

Main bottleneck:

gathering time

If gathering is not parallelized:
- crafting waits
- combat progression slows
- upgrades are delayed

Conclusion:

gathering must be distributed across multiple characters

---

## Role model (initial strategy)

This is a STARTING POINT, not a final design.

### Character 1 — Main Carry

Role:
- pure combat

Responsibilities:
- maximize EXP gain
- always fight best available enemies
- never idle

Rules:
- no gathering
- no crafting
- no tool switching

---

### Character 2 — Secondary Fighter / Drop Farmer

Role:
- combat + targeted farming

Responsibilities:
- farm specific mobs for drops
- support progression resources
- assist main indirectly

Rules:
- combat-first
- no heavy crafting
- minimal gathering only if needed

---

### Character 3 — Woodcutting Specialist

Tool:
- axe

Role:
- wood gathering

Responsibilities:
- constant wood supply
- optional light crafting if idle

Rules:
- no tool switching
- avoid combat unless necessary

---

### Character 4 — Mining Specialist

Tool:
- pickaxe

Role:
- ore gathering

Responsibilities:
- constant ore supply
- support crafting pipeline

Rules:
- no tool switching
- optional crafting support

---

### Character 5 — Fishing + Cooking

Tool:
- fishing net

Role:
- sustain provider

Responsibilities:
- produce food
- maintain healing resources

Rules:
- fishing primary
- cooking secondary
- no unnecessary switching

---

## Why this works

- 3 parallel gathering streams (wood / ore / fish)
- no tool-switch overhead
- combat characters stay fully utilized
- crafting can consume resources continuously
- no single gathering bottleneck

---

## What is intentionally NOT included

- no dedicated "full crafter" at start
- no single gatherer model
- no heavy specialization per character

Reason:

over-specialization creates idle time and bottlenecks

---

## Dynamic adjustment principle

Roles are NOT fixed.

System must adapt based on bottlenecks.

---

### If gathering is insufficient:

- convert Character 2 or 3 into hybrid gatherer
- increase gathering parallelism

---

### If crafting becomes a bottleneck:

- assign crafting temporarily to:
  - mining character
  - woodcutting character

---

### If combat progression slows:

- redirect one gatherer to combat
- increase combat capacity

---

## Key optimization rules

1. Avoid idle time
2. Avoid single-point bottlenecks
3. Prefer parallelism over specialization
4. Minimize tool switching
5. Keep combat characters active
6. Use bank to decouple roles

---

## Future evolution

Later, system may evolve into:

- hybrid roles
- multi-character coordination
- boss-fight preparation (3 fighters)

But initial goal:

stable, parallel, predictable resource flow

---

## Instructions for Claude

When proposing implementations:

- do NOT introduce complex frameworks
- do NOT enforce strict role separation
- do NOT rely on tool switching logic
- prefer simple services
- think in terms of:
  - time
  - cooldown
  - resource flow
  - bottlenecks

Always ask:

"Which part of the system is waiting?"

---

## Task distribution — implementation groundwork

### Core idea

The dispatcher is not a scheduler. It is a loop that:

1. reads all characters
2. finds who is ready (cooldown expired)
3. runs their assigned task
4. repeats

No threads. No queues. One loop, sequential decisions.

```
while True:
    for each character:
        if ready → run assigned task
    sleep until next character is ready
```

---

### Key helpers needed

**`seconds_until_ready(character_data) → float`**

Reads `cooldown_expiration` from character data.
Returns 0 if ready, positive seconds if waiting.
Does not make an API call — works on already-fetched data.

**`get_all_characters(client) → list[dict]`**

GET /my/characters — returns all account characters with full state.
One call, all data. Avoids N separate GET /characters/{name} calls.

**`find_next_ready(characters) → dict | None`**

Returns the character with the lowest `seconds_until_ready`.
If none are ready, returns the one ready soonest (to sleep toward).

**`run_task(client, character, role) → None`**

Dispatches one action cycle based on role:
- "combat" → move to monster tile → fight → rest if HP low
- "mining" → move to ore tile → gather → deposit if inventory near full
- "woodcutting" → move to wood tile → gather → deposit if inventory near full
- "fishing" → move to fish tile → gather → cook if ingredients available

---

### Role assignment

Simple dict, not a framework:

```python
ROLES = {
    "Furiba":    "combat",
    "Char2":     "mining",
    "Char3":     "woodcutting",
    "Char4":     "fishing",
    "Char5":     "combat",
}
```

Roles live in config, not in code logic.
Changing a role = changing one line.

---

### Idle time minimization

Key rule: never sleep longer than needed.

After each dispatch cycle:
- collect `seconds_until_ready` for all characters
- sleep `min(all_ready_times) + 0.3` (buffer for clock drift)
- do not sleep a fixed interval

This ensures the loop wakes up exactly when the next character becomes available.

---

### Deposit trigger

Characters should deposit before their inventory fills up (not after 497).

Simple rule:

```python
if free_slots(inventory) < DEPOSIT_THRESHOLD:
    move to bank → deposit all → return to task tile
```

`DEPOSIT_THRESHOLD` = 3–5 slots depending on drop rate.

---

### Health check rule (combat characters)

After every fight:

```python
hp, max_hp = get_hp(client, character_name)
if hp / max_hp < HP_THRESHOLD:
    rest until full
```

`HP_THRESHOLD` = 0.3 (rest when below 30% HP).

This prevents death penalty cooldowns which are the most expensive idle time.

---

### What this is NOT

- not a task queue
- not a priority scheduler
- not async
- not multi-threaded

It is a sequential loop that makes greedy decisions:
act on whoever is ready, sleep until the next one is.

This is sufficient for 5 characters.
Complexity can grow later if needed.
