# TODO — Artifacts MMO QA Sandbox

Задачи организованы по фазам беклога (`docs/implementation_backlog.md`).
Версии коммитов отражают фазу: `v0.1.x` → фаза 1, `v0.2.x` → фаза 2 и т.д.

---

## DX — Удобство разработки

Не привязаны к фазам, улучшают процесс работы.

- [x] **Запуск тестов** — базовые команды pytest задокументированы в README
  ```bash
  pytest                              # все быстрые тесты (long исключены)
  pytest -v -s tests/test_movement.py # один файл + живые логи
  pytest -m long                      # только long-тесты (ночной прогон)
  pytest -m ""                        # всё включая long
  pytest -v -s -x tests/test_combat.py  # стоп на первом падении
  ```

- [x] **Логи тестов** (`chore(infra): configure pytest logging to terminal and file`)
  - живые логи в терминале во время прогона (`log_cli = true`)
  - сохранение в `logs/pytest.log` после каждого прогона
  - в терминал — INFO+, в файл — DEBUG+ (все запросы/ответы)
  - `logs/` в `.gitignore`, папка зафиксирована через `.gitkeep`

- [x] **Cooldown-aware тесты** (`feat(infra): add wait_for_cooldown and harden stateful tests`)
  - `wait_for_cooldown(client, character_name)` в `services/cooldown.py`
  - читает `cooldown_expiration` из GET /characters/{name}, спит до истечения
  - все stateful-тесты используют явный wait, не пропускают при 499
  - `max_wait=120s` — покрывает бой и штраф за смерть

- [x] **Long-тесты** (`chore(infra): add long test marker`)
  - маркер `@pytest.mark.long` для многошаговых сценариев
  - исключены из дефолтного `pytest` через `addopts = -m "not long"`
  - пример: `test_inventory_full_returns_497` — заполняет инвентарь гербом

- [x] **Smoke-тесты** — отдельный слой в `tests/test_smoke.py`
  - быстрые, без ожиданий, без assert на 200
  - проверяют только доступность эндпоинта и структуру ответа
  - новый домен = новый smoke-тест в том же файле

---

## Фаза 1 — Фундамент (`v0.1.x`) ✅

Цель: стабильная основа до любой игровой логики.

- [x] **1. Авторизация**
  - Bearer token из env, централизован в `ArtifactsClient`
  - conftest валидирует наличие токена и имени персонажа при старте сессии

- [x] **2. Логирование**
  - `logging.getLogger` в клиенте, DEBUG-логи каждого запроса/ответа
  - pytest выводит логи в терминал и сохраняет в `logs/pytest.log`

- [x] **3. Структура проекта**
  - `clients/` — HTTP-слой, `services/` — доменная логика, `tests/` — тесты
  - `clients/__init__.py`, `services/__init__.py` — оформлены как пакеты

- [x] **4. Обработка ошибок**
  - `services/errors.py`: константы всех кодов, `describe_status()`, `parse_api_error()`
  - тесты импортируют коды из `services.errors`, не используют magic numbers

- [x] **5. Cooldown-менеджмент**
  - `services/cooldown.py`: `is_on_cooldown()`, `parse_cooldown()`, `remaining_seconds()`, `wait_for_cooldown()`

- [x] **6. Rate-limit awareness**
  - группы и лимиты задокументированы комментарием в `clients/artifacts_client.py`

---

## Фаза 2 — Базовый геймплей (`v0.2.x`) ✅

Цель: надёжная core-механика для одного персонажа.

- [x] **7. Движение** (`feat(movement): add move action and position helpers`)
  - `services/movement.py`: `get_position`, `move_character`, `is_already_at_destination`
  - 490 и 499 тестируются как отдельные сценарии
  - состояние до/после видно через GET /characters

- [x] **8. Сбор ресурсов** (`feat(gathering): add gathering action with inventory delta`)
  - `services/gathering.py`: `gather`, `parse_gathered_items`
  - ресурсный тайл: Copper Rocks `(2, 0)`
  - delta инвентаря видна, cooldown в ответе проверяется

- [x] **9. Инвентарь** (`feat(inventory): add inventory inspection and delta helpers`)
  - `services/inventory.py`: `get_inventory`, `free_slots`, `find_item`, `inventory_delta`, `is_inventory_full`
  - `test_inventory_full_returns_497` — `@pytest.mark.long`, заполняет инвентарь

- [x] **10. Банк / хранилище** (`feat(bank): add deposit/withdraw flows and delta checks`)
  - `services/bank.py`: `get_bank_items`, `deposit_item`, `withdraw_item`, `deposit_gold`, `bank_delta`
  - эндпоинты: `/action/bank/deposit/item`, `/action/bank/withdraw/item` (list payload)
  - `INSUFFICIENT_GOLD = 492` добавлен в `services/errors.py`

- [x] **11. Отдых / восстановление** (`feat(rest): add rest action and HP recovery check`)
  - `services/rest.py`: `rest`, `get_hp`, `is_full_hp`
  - HP восстановление проверено post-combat (курица `(0, 1)`)

- [x] **12. Бой** (`feat(combat): add fight action with result and state validation`)
  - `services/combat.py`: `fight`, `parse_fight_result`, `is_win`, `is_loss`
  - API возвращает `"loss"` (не `"lose"`) — зафиксировано
  - проверены: результат win/loss, XP при победе, delta HP

---

## Фаза 3 — Production chains (`v0.3.x`)

Цель: многошаговые значимые сценарии, персонаж как полноценный агент.

- [x] **13. Профиль персонажа** (`feat(character): add skills, stats, and equipment inspection`)
  - уровни навыков: mining, woodcutting, fishing, cooking, weaponcrafting, gearcrafting, jewelrycrafting, alchemy
  - базовые статы: attack, defense, speed, hp_max
  - слоты экипировки и надетые предметы
  - хелпер `get_character_profile` — единая точка для решений по персонажу
  - основа для skill-aware крафта, подбора ресурсов, мульти-перса

- [x] **14. Крафт** (`feat(crafting): add crafting flow with material delta check`)
  - проверка нужных материалов и уровня навыка
  - выполнение крафта (нужен тайл мастерской)
  - delta материалов видима
  - результат крафта проверяем

- [x] **15. Задания (Tasks)** (`feat(tasks): add task accept and complete flow`)
  - просмотр текущего задания
  - принять / отслеживать / завершить задание
  - один поток задания проверен end-to-end
  - task-хелперы переиспользуемы в сценариях

- [x] **16. Мультиперсонаж** (`feat(multi-char): add multi-character state tracking`)
  - получить список всех персонажей аккаунта
  - читать состояние каждого: HP, позиция, cooldown, инвентарь, навыки
  - выбирать, кто готов к действию (cooldown expired + нужный скилл)
  - логи чётко показывают кто что делает
  - основа для параллельных сценариев

- [x] **17. Менеджер сценариев** (`feat(infra): add lightweight scenario orchestration helper`)
  - `ROLES` dict: имя персонажа → роль (combat / mining / woodcutting / alchemy)
  - cycle-функции по роли: `run_combat_cycle`, `run_mining_cycle`, `run_woodcutting_cycle`, `run_alchemy_cycle`
  - каждый cycle: wait → move → action → post-action check (HP, inventory, task)
  - `run_dispatch_loop`: читает всех персонажей, запускает cycle для готовых, спит до следующего
  - ошибка одного персонажа не останавливает loop — логируется, остальные продолжают
  - `scripts/dispatch.py` — запускаемый вручную скрипт для проверки loop
  - тайлы ресурсов для woodcutting/alchemy — заглушки до пункта 18.1

- [x] **18.1. Карта ресурсов** (`feat(infra): add map tile cache with JSON storage`)
  - `services/map_cache.py`: кэш 1428 тайлов, TTL 24ч, `find_content(cache, code)` поиск по коду
  - `scripts/discover_map.py`: поиск тайлов по коду (`ash_tree chicken bank`), `--refresh`, `--all`
  - `data/maps.json`: gitignored, генерируется скриптом
  - координаты заполнены через `ROLE_RESOURCE` в `scenario.py` — нет хардкода:
    - mining: `copper_rocks` → (2, 0)
    - woodcutting: `ash_tree` → (-1, 0)
    - fishing: `gudgeon_spot` → (4, 2)
    - alchemy: `sunflower_field` → (2, 2)
  - CLAUDE.md обновлён: полная карта ресурсов по ролям
  - `gathering.py`: 598 → `invalidate_cache()` — кэш сбрасывается при несоответствии тайла

---

## Фаза 4 — Расширение (`v0.4.x`)

Цель: рыночные механики, события, мета-прогресс.

- [ ] **18. Grand Exchange** (`feat(exchange): add market state read and order inspection`)
  - просмотр публичных и аккаунт-ордеров
  - проверка карты и предусловий аккаунта
  - основа для будущих торговых сценариев

- [ ] **19. События (Events)** (`feat(events): add event detection and state observation`)
  - читать данные событий
  - детектировать активные события
  - event-специфичная автоматизация возможна без переработки архитектуры

- [ ] **20. Достижения / прогресс аккаунта** (`feat(infra): add achievement and account progress observation`)
  - читать достижения и badge-данные
  - использовать как meta-прогресс при необходимости

---

## Фаза 5 — Goal system (`v0.5.x`)

Цель: верхний слой пользовательских целей поверх исполнительного слоя.
Персонажи выбираются по пригодности, а не по фиксированным ролям.
Planner пишет задачи в БД — dispatcher читает и выполняет, не зная о planner.
Детали архитектуры и acceptance criteria: `docs/goal_system.md`.

- [x] **21. SQLite storage** (`feat(goals): add SQLite storage for goals, tasks, reservations`)
  - таблицы: `goals`, `tasks`, `reservations`
  - `data/goals.db` — gitignored, создаётся при первом запуске
  - атомарные UPDATE для статусов и claim — без них reservation сломается
  - схема версионируется через `schema_version` таблицу

- [x] **22. Модели** (`feat(goals): add Goal and PlannedTask dataclasses`)
  - `Goal`: id, type, status, priority, target_item/skill/level/character,
    allowed/preferred/assigned_character, hard_assignment, parent_goal_id
  - `PlannedTask`: id, goal_id, type, status, character_name, item_code, quantity,
    allowed/preferred_characters, hard_assignment, claimed_at, reserved_until
  - статусы goal: `active`, `completed`, `blocked`, `failed`
  - статусы task: `open`, `claimed`, `running`, `done`, `blocked`, `failed`
  - blocked хранит причину строкой — для логов и будущего UI

- [x] **23. World state snapshot** (`feat(goals): add world state collector`)
  - один снимок за planning cycle: персонажи, инвентари, навыки, экипировка, банк,
    active goals, active tasks, reservations, cooldowns
  - единственный источник истины для planner в рамках одного цикла
  - не дёргает API повторно внутри одного planning pass

- [x] **24. Planner cycle** (`feat(goals): add idempotent planner loop`)
  - читает active goals → world state → создаёт недостающие tasks
  - idempotent: не создаёт дубли, если task уже существует в open/claimed
  - при создании dependency tasks хранит `parent_goal_id`
  - защита от циклов: visited set при рекурсивном планировании, лимит глубины
  - если зависимость неразрешима → goal → `blocked` с причиной

- [x] **25. Assignment / targeting** (`feat(goals): add character suitability scoring`)
  - `score_character(char, task)` → число; выше = лучше подходит
  - факторы: нужный инструмент надет, skill level достаточен, уже рядом с тайлом,
    cooldown мал, персонаж в allowed_characters
  - `allowed_characters` — только они могут взять задачу
  - `preferred_characters` — получают бонус к score
  - `hard_assignment` — только один конкретный персонаж, score остальных = 0
  - `scripts/goals.py` — новый runner, не трогает `scenario.py`

- [x] **26. Reservation + claim** (`feat(goals): add reservation and claim/lock system`)
  - reservation: сколько единиц ресурса уже зарезервировано под active tasks/goals
  - перед созданием gather-task: `needed = target − in_bank − reserved − in_active_tasks`
  - claim: `task.claimed_by`, `task.claimed_at`; таймаут ~300s (бой + смерть + восстановление)
  - dispatcher при взятии задачи делает атомарный UPDATE status=claimed WHERE status=open
  - expired claims возвращаются в open в начале каждого planning cycle

- [x] **27. Collect goal** (`feat(goals): add collect goal with bank-based progress`)
  - MVP первого типа цели
  - прогресс = количество предмета в банке (не в инвентаре, не в пути)
  - `remaining = target_qty − bank_qty − reserved`
  - разбивка на чанки ≤ inventory_max_items * DEPOSIT_FILL_RATIO
  - done когда `bank_qty >= target_qty`

- [x] **28. Craft goal** (`feat(goals): add craft goal with recipe cache and gather dependencies`)
  - рецепты из `GET /items/{code}` → `craft.items[]`
  - кэш рецептов в `data/items.json` (аналог `maps.json`, TTL или on-demand)
  - если материалов не хватает — автоматически создаёт collect sub-goals
  - craft task выдаётся только когда все материалы доступны (bank − reserved ≥ needed)
  - done когда готовый предмет появился в нужном количестве

- [x] **29. Equip goal** (`feat(goals): add equip goal with fallback to craft/collect`)
  - equip не требует тайла — просто `POST /action/equip`
  - порядок поиска предмета: equipped → inventory → bank → craft/collect
  - если предмет уже надет → goal сразу `completed`
  - если предмет в инвентаре → equip
  - если предмет в банке → withdraw → equip
  - если нет нигде → spawn craft/collect sub-goal → ждать → equip
  - `target_character` обязателен, `hard_assignment = True` по умолчанию

- [x] **30. Level goal** (`feat(goals): add level goal with action registry`)
  - критерий завершения: `skill_level >= target_level` у target_character
  - action registry: какие действия качают какой навык (mining → mine copper/iron/...,
    woodcutting → cut ash/birch/..., combat → fight monsters)
  - planner выбирает подходящий ресурс/монстра по текущему skill level персонажа
  - combat level goal — базовая заглушка: бить ближайшего посильного монстра
  - level goal можно совмещать с collect: одни и те же действия, разный критерий

- [x] **31. Observability** (`feat(goals): add planner decision logging and blocked reporting`)
  - лог каждого planning decision: почему выбран персонаж, какой score, какая задача создана
  - лог blocked: причина + goal/task id
  - лог reservation state при создании задач
  - статус всех целей и подзадач виден в логах без дебаггера

---

## MVP ✅

Пункты 1–12 (Фазы 1 и 2) стабильны.
Проект уже полезен для автоматизации реального геймплея одного персонажа.

## Текущее состояние

**Фазы 1, 2, 3 и Goal system (пункты 21–31) завершены.**

**Сервисы:**
- `clients/artifacts_client.py` — HTTP-клиент с logging и rate-limit комментарием
- `services/errors.py` — все коды ошибок включая `NO_RESOURCE_ON_TILE = 598`
- `services/cooldown.py` — `wait_for_cooldown`, `parse_cooldown`, `remaining_seconds`
- `services/movement.py` — `get_position`, `move_character`
- `services/gathering.py` — `gather`, `parse_gathered_items`; 598 → `invalidate_cache()`
- `services/inventory.py` — `get_inventory`, `free_slots`, `find_item`, `inventory_delta`, `get_inventory_state`
- `services/bank.py` — `deposit_item`, `withdraw_item`, `deposit_gold`, `bank_delta`
- `services/rest.py` — `rest`, `get_hp`, `is_full_hp`
- `services/combat.py` — `fight`, `parse_fight_result`, `is_win`, `is_loss`
- `services/character.py` — `get_character_profile`, `get_skill_level`, `get_equipment`, `has_skill_level`
- `services/crafting.py` — `craft`, `parse_craft_result`, `get_item_info`, `has_materials`
- `services/tasks.py` — `get_task_state`, `accept_task`, `complete_task`, `is_task_complete`
- `services/multi_char.py` — `get_all_characters`, `find_ready_characters`, `sleep_until_next_ready`
- `services/map_cache.py` — кэш 1428 тайлов, `find_content`, TTL 24ч, инвалидация по 598
- `services/scenario.py` — `ROLES`, `ROLE_RESOURCE`, `run_dispatch_loop`, цикл-функции по роли
- `services/goals.py` — `Goal`, `PlannedTask` dataclasses; `GoalType`, `TaskType`, статусы; make_*_task хелперы
- `services/goal_store.py` — SQLite (WAL): goals/tasks/reservations; atomic claim; expire_stale_claims
- `services/world_state.py` — `build_world_state`: снимок персонажей, банка, кэша, задач за 3 API вызова
- `services/planner.py` — `run_planning_cycle`: collect/craft/equip/level planners, idempotent, sub-goals
- `services/assignment.py` — `score_character_for_task`; `find_best_character_for_task`; `find_best_task_for_character`
- `services/item_data.py` — `ITEM_SOURCE`, `RESOURCE_SKILL`, `RESOURCE_DROP`, `SKILL_TRAIN_RESOURCE`, `WORKSHOP_CONTENT_CODE`
- `services/item_cache.py` — lazy cache `data/items.json`; `get_cached_recipe`, `get_craft_skill`, `get_item_type`
- `services/equipment.py` — `get_slot_for_item`, `is_item_equipped`, `equip_item`, `unequip_item`

**Скрипты:**
- `scripts/dispatch.py` — запуск dispatch loop (`--cycles N`)
- `scripts/discover_map.py` — поиск тайлов по коду (`--refresh`, `--all`)
- `scripts/goals.py` — goal runner: plan → assign → execute; `GOALS` список правится вручную

**Тесты:**
- `tests/test_smoke.py` — 13 smoke-тестов (все домены включая crafting/tasks/maps)
- `tests/test_movement.py` — 4 теста
- `tests/test_gathering.py` — 4 теста
- `tests/test_inventory.py` — 5 fast + 1 long
- `tests/test_bank.py` — 4 теста
- `tests/test_rest.py` — 4 теста
- `tests/test_combat.py` — 5 тестов
- `tests/test_character.py` — 4 теста (профиль, навыки, экипировка)
- `tests/test_crafting.py` — статeful крафт-тесты
- `tests/test_tasks.py` — task accept/complete flow
- `tests/test_multi_char.py` — 4 теста (dispatch поля, cooldown логика)
- `tests/test_map_cache.py` — 10 unit-тестов + 3 smoke (GET /maps)
