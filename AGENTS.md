# AGENTS.md

Telegram trading-statistics bot (aiogram 3.x). All UI text, DB `op_type` values, and code comments are in Russian (`"Сделка"`, `"Пополнение"`, `"Вывод"`); trade `result` is English (`"Win"`/`"Loss"`). Keep these strings consistent when editing.

## Run

- Local: `python bot.py` — requires `.env` with `API_TOKEN`; bot raises `ValueError` if missing. `ADMIN_ID` is optional (defaults to 0 = no admin).
- Docker: `docker compose up -d --build` (only thing in README). SQLite DB lives at `data/trading_bot.db`, volume-mounted, so it survives rebuilds.
- No tests, linter, CI, or lockfile exist. Nothing to run before committing beyond a smoke test.

## Architecture gotchas

- `bot.py` is the only real entrypoint, and it re-defines everything it imports from the submodules. It imports `keyboards/inline.py` and `states/fsm.py` (bot.py:25-30) but then shadows those names with local definitions (keyboards: bot.py:80-142, states: bot.py:62-77). The local versions win, so **editing `keyboards/inline.py` or `states/fsm.py` has no effect** — edit the copies in `bot.py`. The local `get_main_keyboard(user_id)` differs from the module one: it only shows the backup button to `ADMIN_ID`.
- All handlers must drive the UI through `update_interface()` (bot.py:145). It enforces a "one active bot message per user" invariant: it edits the last message tracked as `bot_msg_id` in FSM state and deletes stale ones. Calling `send_message`/`edit_text` directly from a new handler will break this.
- FSM state persists in SQLite (`fsm_states` table via custom `SQLiteFSMStorage`), not memory — a bot restart does not clear in-progress dialogs. `/start` and the `main_menu` callback call `state.clear()`, so users can always recover.
- DB schema (`users`, `operations`, `fsm_states`) is auto-created at startup (`init_db()`, `SQLiteFSMStorage.__init__`); there are no migrations. `database.py` opens a fresh `sqlite3.connect` per call — do the same in new DB code.
- Deposit is clamped at 0 (`max(0.0, ...)` when saving a trade). A trade can only be deleted if it is the last operation (`is_last_operation`), otherwise the balance history would be corrupted — keep that guard if you touch deletion.
- Excel export (utils/excel.py) is currency-agnostic: column headers and number formats hardcode `$` regardless of the user's chosen currency.
