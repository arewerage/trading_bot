# AGENTS.md

Telegram trading-statistics bot (aiogram 3.x). All UI text, DB `op_type` values, and code comments are in Russian (`"Сделка"`, `"Пополнение"`, `"Вывод"`); trade `result` is English (`"Win"`/`"Loss"`). Keep these strings consistent when editing.

## Run

- Local: `python bot.py` — requires `.env` with `API_TOKEN`; bot raises `ValueError` if missing. `ADMIN_ID` is optional (defaults to 0 = no admin).
- Docker: `docker compose up -d --build` (only thing in README). SQLite DB lives at `data/trading_bot.db`, volume-mounted, so it survives rebuilds.
- No tests, linter, CI, or lockfile exist. Nothing to run before committing beyond a smoke test. Use `python -m py_compile <file>` and `python -c "from handlers import routers"` to sanity-check imports.
- Deps in `requirements.txt`: aiogram>=3.23, pandas==2.2.2, openpyxl==3.1.5, python-dotenv==1.0.1, matplotlib>=3.10 (matplotlib must support numpy 2.x; older pins like 3.8.4 crash with `RecursionError` on `savefig`).

## Architecture

- `bot.py` is thin: it includes routers from `handlers/__init__.py` (`routers` list) and starts the daily-report task `daily_reports_loop` from `handlers/reports.py` (a background asyncio task, not a Router). `init_db()` is called inside `main()`.
- Handlers live in `handlers/` — one module per feature: `start`, `deposit`, `trades`, `history`, `stats`, `accounts`, `settings`, `chart`, `imports`, `admin`, `excel`, `reports`. Each starts with `router = Router()`.
- All handlers must drive the UI through `update_interface()` (`handlers/common.py`). It enforces a "one active bot message per user" invariant: it edits the last message tracked as `bot_msg_id` in FSM state, deletes stale ones, and supports `document=` / `photo=` media (for media it deletes the old message and sends a fresh one). Calling `send_message`/`edit_text` directly from a new handler will break this.
- **`update_interface` answers the callback itself** — do NOT add `callback.answer()` next to it (double answer = BadRequest). Use `callback.answer(...)` only in early-return branches before any `update_interface` call.
- FSM state persists in SQLite (`fsm_states` table via custom `SQLiteFSMStorage`), not memory — a bot restart does not clear in-progress dialogs. `/start` and the `main_menu` callback call `state.clear()`, so users can always recover.
- `database.py` opens a fresh `sqlite3.connect` per call — do the same in new DB code.

## DB schema & invariants (`database.py`)

- Tables: `users` (user_id, active_account_id, tz_offset — offset in minutes, daily_report 0/1), `accounts` (id, user_id, name, deposit, currency, created_at), `operations` (id, user_id, account_id, date, op_type, pair, lot, side, result, amount, commission, balance_after, note, risk_pct), `fsm_states`.
- `op_type`: `Старт` (opening deposit marker), `Сделка`, `Пополнение`, `Вывод`. Trade `amount` is the **net** result: the handler (`handlers/trades.py`) subtracts commission from the entered value before calling `add_trade_operation`. `side`: `Buy`/`Sell`.
- Balance is always recomputed via `recalc_account_balance(account_id)` (a replay: iterate ops by id, `balance = max(0.0, balance + amount)`). Deletion, trade editing and import all go through this replay. The `Старт` row cannot be deleted (`delete_operation` returns False).
- `get_operations(account_id)` returns ascending rows in legacy order `(date, op_type, pair, lot, result, amount, balance_after, note, risk_pct, side, commission, id)` — utils/analytics.py and utils/excel.py rely on indices 0-8.
- Pagination: `get_operations_page(account_id, page, per_page)` returns `(rows, total)` with `id` FIRST in each row.
- Migration: `_migrate()` runs inside `init_db()`; it converts the old single-deposit `users(deposit, currency)` layout into `accounts`, assigns `account_id` to old operations, and backfills the new `users`/`operations` columns. Don't change the schema without updating `_migrate`.
- Timezones: "today/yesterday/ranges" are computed from `now_local(tz_offset)` / `now_local_str` in `database.py`; default 0 (UTC). Set via settings.

## Feature gotchas

- Multiple handlers listen on `curr_` callbacks — they are gated by distinct FSM states (`DepositState`, `AccountState`, `SettingsState`), so the filters do not collide.
- Excel export (`utils/excel.py`) is currency-aware now: it reads the account currency for headers and number formats (don't hardcode `$`). Chart (`utils/chart.py`) uses matplotlib Agg and rotates x labels by hand (avoid `fig.autofmt_xdate` — it triggers the tick-copy path that recurses on matplotlib<numpy2).
- CSV/Excel import (`utils/importer.py`) accepts `date, op_type, pair, lot, result, amount` plus optional `side, commission, risk_pct, note`; amounts are signed (losses negative).
- Backup button only appears for `ADMIN_ID` in `get_main_keyboard` (`keyboards/inline.py`).
