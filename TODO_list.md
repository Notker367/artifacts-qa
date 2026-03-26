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

## MVP ✅

Пункты 1–12 (Фазы 1 и 2) стабильны.
Проект уже полезен для автоматизации реального геймплея одного персонажа.

## Текущее состояние

**Фазы 1, 2 и 3 завершены.**

**Сервисы:**
- `clients/artifacts_client.py` — HTTP-клиент с logging и rate-limit комментарием
- `services/errors.py` — все коды ошибок включая `NO_RESOURCE_ON_TILE = 598`
- `services/cooldown.py` — `wait_for_cooldown`, `parse_cooldown`, `remaining_seconds`
- `services/movement.py` — `get_position`, `move_character`
- `services/gathering.py` — `gather`, `parse_gathered_items`; 598 → `invalidate_cache()`
- `services/inventory.py` — `get_inventory`, `free_slots`, `find_item`, `inventory_delta`
- `services/bank.py` — `deposit_item`, `withdraw_item`, `deposit_gold`, `bank_delta`
- `services/rest.py` — `rest`, `get_hp`, `is_full_hp`
- `services/combat.py` — `fight`, `parse_fight_result`, `is_win`, `is_loss`
- `services/character.py` — `get_character_profile`, `get_skill_level`, `get_equipment`, `has_skill_level`
- `services/crafting.py` — `craft`, `parse_craft_result`, `get_item_info`, `has_materials`
- `services/tasks.py` — `get_task_state`, `accept_task`, `complete_task`, `is_task_complete`
- `services/multi_char.py` — `get_all_characters`, `find_ready_characters`, `sleep_until_next_ready`
- `services/map_cache.py` — кэш 1428 тайлов, `find_content`, TTL 24ч, инвалидация по 598
- `services/scenario.py` — `ROLES`, `ROLE_RESOURCE`, `run_dispatch_loop`, цикл-функции по роли

**Скрипты:**
- `scripts/dispatch.py` — запуск dispatch loop (`--cycles N`)
- `scripts/discover_map.py` — поиск тайлов по коду (`--refresh`, `--all`)

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
