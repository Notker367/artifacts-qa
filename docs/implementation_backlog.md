# Artifacts MMO — implementation backlog

## Purpose

This file describes the implementation roadmap for the Artifacts MMO QA / automation sandbox.

It is not a generic framework plan.
It is a practical backlog for building a readable Python project around:
- API access
- game actions
- stateful scenarios
- automation helpers
- future multi-character orchestration

Main priorities:
1. keep the implementation simple
2. make debugging easy
3. support stateful game logic
4. avoid overengineering
5. build a project that can grow step by step

---

## Project intent

This project is meant to become a practical sandbox for:
- learning the Artifacts MMO API
- automating meaningful gameplay flows
- testing state transitions
- building reusable action/services logic
- experimenting with multi-character control later

This is NOT:
- a huge framework
- a pure bot farm from day one
- a contract-only API test suite

This IS:
- a readable implementation sandbox
- a place for incremental automation
- a foundation for future gameplay orchestration

---

## Core implementation principles

- Keep code simple and readable.
- Avoid unnecessary abstractions.
- Prefer small services over clever architecture.
- Separate HTTP layer from domain logic.
- Separate domain logic from tests.
- Prefer explicit flows over hidden magic.
- Log every important action and state transition.
- Treat cooldowns, inventory, and location as first-class concerns.
- Build for one character first, then expand to multiple characters.

---

## Recommended implementation layers

### 1. Core layer
Responsible for:
- configuration
- auth
- HTTP client
- error handling
- rate-limit awareness
- cooldown-aware helpers
- logging

### 2. Domain layer
Responsible for:
- movement
- gathering
- inventory
- bank
- combat
- crafting
- tasks
- rest / recovery

### 3. Orchestration layer
Responsible for:
- multi-step scenarios
- character scheduling
- multi-character coordination
- future automation loops

### 4. QA / validation layer
Responsible for:
- smoke checks
- state transition checks
- negative scenarios
- regression safety

---

## Delivery phases

# Phase 1 — foundation
Goal: build stable basics before gameplay logic

## 1. Authorization
### Goal
Implement authenticated access to protected endpoints.

### Scope
- load token from env
- construct Authorization header
- validate that auth is configured
- handle auth-related API failures clearly

### Done when
- client can call protected endpoints successfully
- missing/invalid token errors are easy to identify
- token handling is centralized

### Why it matters
All meaningful character actions depend on auth.

---

## 2. Logging principles
### Goal
Create logs that explain what happened and why.

### Scope
- log request method + endpoint
- log payload for actions
- log response status / error code
- log duration
- log character name
- log cooldown decisions
- log state transitions

### Done when
- any failed scenario can be reconstructed from logs
- action chains are readable
- logs help debug location / inventory / cooldown issues

### Why it matters
State-driven game logic becomes painful very quickly without logs.

---

## 3. Project structure
### Goal
Create a clean and expandable structure.

### Minimum expected structure
- clients/
- services/
- tests/
- docs/
- config files in root

### Done when
- HTTP logic is separated from domain actions
- tests are not mixed with client code
- project is easy to navigate

### Why it matters
This project should grow gradually without collapsing into chaos.

---

## 4. Error handling
### Goal
Handle API failures consistently.

### Scope
- parse API errors
- distinguish auth / validation / cooldown / inventory / not-found / rate-limit failures
- expose errors in a simple usable form

### Done when
- tests and services do not manually parse every error
- error reporting is predictable
- debugging bad responses is easy

### Why it matters
Artifacts has meaningful domain-specific failures and they should not feel random.

---

## 5. Cooldown management
### Goal
Treat cooldown as a normal game mechanic, not as an edge case.

### Scope
- parse cooldown data from action responses
- represent cooldown in a reusable way
- provide helpers for "can act now?" logic
- optionally provide wait helpers later

### Done when
- action services can detect cooldown cleanly
- repeated action failures are understandable
- cooldown handling is not duplicated everywhere

### Why it matters
Cooldown is central to almost every action flow.

---

## 6. Rate-limit awareness
### Goal
Avoid breaking flows because of request throttling.

### Scope
- know endpoint categories
- know which requests are expensive
- optionally provide lightweight throttling later
- surface rate-limit failures clearly

### Done when
- request bursts are intentional
- tests do not confuse throttling with game bugs
- multi-character growth remains feasible

### Why it matters
The API has different rate-limit groups and they matter for automation.

---

# Phase 2 — basic gameplay actions
Goal: build reliable core game behavior around one character first

## 7. Movement
### Goal
Move a character predictably and safely.

### Scope
- get current position
- move to coordinates
- detect "already there"
- validate preconditions where possible
- later: support map-aware movement rules

### Done when
- movement works in simple scenarios
- state before/after move is visible
- movement failures are understandable

### Why it matters
Almost every meaningful action depends on location.

---

## 8. Gathering action
### Goal
Implement resource gathering as the first real stateful action.

### Scope
- call gathering action
- verify that resource collection changes state
- check cooldown behavior
- check inventory impact

### Done when
- one gathering flow can be executed and validated end-to-end
- inventory delta is visible
- gathering failures are understandable

### Why it matters
It is a simpler stateful action than combat and a good first domain milestone.

---

## 9. Inventory
### Goal
Make inventory readable and testable.

### Scope
- inspect current inventory
- count free slots
- search item by code
- compare inventory before/after actions
- detect full inventory situations

### Done when
- inventory delta checks are easy
- actions can guard against missing space
- inventory logic is not duplicated inside tests

### Why it matters
Inventory is involved in gathering, combat, crafting, and bank flows.

---

## 10. Bank / storage
### Goal
Implement basic storage behavior.

### Scope
- read bank state
- deposit item
- withdraw item
- deposit gold
- withdraw gold
- compare state before/after

### Done when
- inventory-to-bank transitions are visible
- deposit/withdraw flows are testable
- bank actions can be reused by other services

### Why it matters
Bank enables longer scenarios and removes inventory bottlenecks.

---

## 11. Rest / recovery
### Goal
Recover characters cleanly after damage.

### Scope
- rest action
- detect HP changes
- surface cooldown after rest
- later: item-based recovery if useful

### Done when
- damaged character can recover through a reusable service
- recovery is visible in logs
- post-combat recovery becomes scriptable

### Why it matters
Combat automation becomes painful without recovery.

---

## 12. Combat action
### Goal
Implement basic combat flows.

### Scope
- fight action
- inspect result
- inspect cooldown
- check loot / XP / HP changes
- detect failure cases
- later: advanced combat scenarios

### Done when
- one character can fight and result can be validated
- combat state changes are understandable
- failures are debuggable

### Why it matters
Combat is one of the most important and interesting stateful systems.

---

# Phase 3 — production chains
Goal: build longer meaningful workflows

## 13. Crafting
### Goal
Create items from materials in a structured way.

### Scope
- inspect needed materials
- perform crafting
- validate resource consumption
- validate crafted result
- later: recycling

### Done when
- a simple crafting flow works end-to-end
- material delta is visible
- crafted item output is testable

### Why it matters
Crafting is one of the best domains for multi-step scenarios.

---

## 14. Task management
### Goal
Support game tasks as higher-level objectives.

### Scope
- inspect current task
- accept task
- track objective progress
- complete task
- later: helper logic for choosing/advancing tasks

### Done when
- one task flow can be completed and validated
- task state is readable
- task handling can be reused in scenarios

### Why it matters
Tasks connect multiple gameplay systems into one useful flow.

---

## 15. Scenario manager
### Goal
Create a lightweight orchestration helper for multi-step flows.

### Scope
- define ordered steps
- define preconditions
- handle action interruptions
- abort on unrecoverable failure
- optionally resume later

### Done when
- simple multi-step scenarios are easier to express
- repeated flow logic is not copy-pasted everywhere
- orchestration remains readable

### Why it matters
It is the bridge between low-level actions and useful automation.

---

# Phase 4 — multi-character and expansion
Goal: move from one-character flows to account-level orchestration

## 16. Multi-character management
### Goal
Control multiple characters without losing clarity.

### Scope
- fetch and represent multiple characters
- track their state independently
- choose which character should act next
- respect cooldown and location constraints
- avoid conflicting flows

### Done when
- at least two characters can be coordinated safely
- logs clearly show which character did what
- scheduling logic is understandable

### Why it matters
This is where the project begins to feel like a real agent system.

---

## 17. Grand Exchange
### Goal
Support marketplace-related flows later.

### Scope
- inspect public and account orders
- place/update/cancel workflows later if needed
- validate map and account preconditions

### Done when
- market-related state can be read and reasoned about
- future exchange actions have a place in the architecture

### Why it matters
This is useful, but not essential for the first stable version.

---

## 18. Events
### Goal
Support limited-time event-aware logic later.

### Scope
- read event data
- detect active events
- optionally route characters to event content later

### Done when
- event state is observable
- event-specific automation can be added without redesigning the project

### Why it matters
Events are useful expansion content, but not core MVP.

---

## 19. Achievements / account-level progress
### Goal
Optionally observe long-term account progress later.

### Scope
- read achievement/badge-related state
- use it as meta progress data if needed

### Done when
- achievement-related info is available for future reporting or planning

### Why it matters
This is a low-priority extension, not an initial build target.

---

## MVP recommendation

The first practical MVP should include:

1. Authorization
2. Logging principles
3. Project structure
4. Error handling
5. Cooldown management
6. Movement
7. Inventory
8. Bank
9. Gathering
10. Rest
11. Combat

If these are stable, the project already becomes useful.

---

## Next after MVP

After MVP, prioritize:

1. Crafting
2. Task management
3. Scenario manager
4. Multi-character management

---

## Later / optional

After that, expand into:
- Grand Exchange
- Events
- Achievements
- smarter scheduling
- richer automation loops

---

## Definition of success

This project is successful when:
- one character can perform several actions reliably
- state transitions are visible and testable
- failures are easy to understand
- code remains simple and readable
- new gameplay systems can be added without large rewrites
- multi-character support can be added on top of stable foundations

---

## Notes for Claude

When helping with this project:
- prioritize practicality over architecture
- avoid creating generic frameworks
- do not introduce async unless explicitly requested
- do not add extra dependencies unless clearly useful
- think in terms of game state and transitions
- prefer minimal services and readable tests
- build one stable layer at a time