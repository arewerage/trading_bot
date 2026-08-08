import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey

DB_DIR = "data"
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR, exist_ok=True)
DB_NAME = os.path.join(DB_DIR, "trading_bot.db")

DEFAULT_CURRENCY = "USD"


def _connect():
    return sqlite3.connect(DB_NAME)


def _now_utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def now_local(tz_offset: int) -> datetime:
    """Текущие дата/время в локальном поясе пользователя (naive, без tzinfo)."""
    return datetime.now(timezone.utc) + timedelta(minutes=tz_offset)


def now_local_str(tz_offset: int) -> str:
    return now_local(tz_offset).strftime("%Y-%m-%d %H:%M:%S")


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class SQLiteFSMStorage(BaseStorage):
    def __init__(self, db_path=DB_NAME):
        self.db_path = db_path
        self._init_fsm_table()

    def _init_fsm_table(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS fsm_states (
                bot_id INTEGER,
                chat_id INTEGER,
                user_id INTEGER,
                state TEXT,
                data TEXT,
                PRIMARY KEY (bot_id, chat_id, user_id)
            )
        """
        )
        conn.commit()
        conn.close()

    async def set_state(
        self, key: StorageKey, state: State | str | None = None
    ) -> None:
        state_str = state.state if isinstance(state, State) else state
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO fsm_states (bot_id, chat_id, user_id, state, data)
            VALUES (?, ?, ?, ?, COALESCE((SELECT data FROM fsm_states WHERE bot_id=? AND chat_id=? AND user_id=?), '{}'))
            ON CONFLICT(bot_id, chat_id, user_id) DO UPDATE SET state = ?
        """,
            (
                key.bot_id,
                key.chat_id,
                key.user_id,
                state_str,
                key.bot_id,
                key.chat_id,
                key.user_id,
                state_str,
            ),
        )
        conn.commit()
        conn.close()

    async def get_state(self, key: StorageKey) -> str | None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT state FROM fsm_states WHERE bot_id = ? AND chat_id = ? AND user_id = ?",
            (key.bot_id, key.chat_id, key.user_id),
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row and row[0] else None

    async def set_data(self, key: StorageKey, data: dict) -> None:
        data_str = json.dumps(data)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO fsm_states (bot_id, chat_id, user_id, state, data)
            VALUES (?, ?, ?, (SELECT state FROM fsm_states WHERE bot_id=? AND chat_id=? AND user_id=?), ?)
            ON CONFLICT(bot_id, chat_id, user_id) DO UPDATE SET data = ?
        """,
            (
                key.bot_id,
                key.chat_id,
                key.user_id,
                key.bot_id,
                key.chat_id,
                key.user_id,
                data_str,
                data_str,
            ),
        )
        conn.commit()
        conn.close()

    async def get_data(self, key: StorageKey) -> dict:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT data FROM fsm_states WHERE bot_id = ? AND chat_id = ? AND user_id = ?",
            (key.bot_id, key.chat_id, key.user_id),
        )
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            try:
                return json.loads(row[0])
            except Exception:
                return {}
        return {}

    async def close(self) -> None:
        pass


# ==================== Инициализация и миграция ====================


def init_db():
    conn = _connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            active_account_id INTEGER DEFAULT 0,
            tz_offset INTEGER DEFAULT 0,
            daily_report INTEGER DEFAULT 0
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT DEFAULT 'Основной',
            deposit REAL DEFAULT 0,
            currency TEXT DEFAULT 'USD',
            created_at TEXT
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            account_id INTEGER DEFAULT 0,
            date TEXT,
            op_type TEXT,
            pair TEXT,
            lot REAL,
            side TEXT DEFAULT '',
            result TEXT,
            amount REAL,
            commission REAL DEFAULT 0.0,
            balance_after REAL,
            note TEXT DEFAULT '',
            risk_pct REAL DEFAULT 0.0
        )
    """
    )

    conn.commit()
    _migrate(conn)
    conn.close()

    recalc_all_accounts()


def _table_cols(cur, table: str) -> set:
    return {r[1] for r in cur.execute(f"PRAGMA table_info({table})")}


def _ensure_account(cur, user_id: int, name: str, currency: str, deposit: float):
    """Создаёт счёт и делает его активным, если активного ещё нет."""
    cur.execute(
        "INSERT INTO accounts (user_id, name, deposit, currency, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, name, deposit, currency, _now_utc_str()),
    )
    acc_id = cur.lastrowid
    cur.execute(
        "UPDATE users SET active_account_id=? WHERE user_id=? AND (active_account_id IS NULL OR active_account_id = 0)",
        (acc_id, user_id),
    )
    return acc_id


def _migrate(conn):
    """Доводит старую схему (users с deposit/currency, операции без новых колонок)
    до новой. Данные переносятся в таблицу accounts."""
    cur = conn.cursor()

    user_cols = _table_cols(cur, "users")
    for col, ddl in [
        ("active_account_id", "INTEGER DEFAULT 0"),
        ("tz_offset", "INTEGER DEFAULT 0"),
        ("daily_report", "INTEGER DEFAULT 0"),
    ]:
        if col not in user_cols:
            cur.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")

    op_cols = _table_cols(cur, "operations")
    for col, ddl in [
        ("account_id", "INTEGER DEFAULT 0"),
        ("side", "TEXT DEFAULT ''"),
        ("commission", "REAL DEFAULT 0.0"),
        ("note", "TEXT DEFAULT ''"),
        ("risk_pct", "REAL DEFAULT 0.0"),
    ]:
        if col not in op_cols:
            cur.execute(f"ALTER TABLE operations ADD COLUMN {col} {ddl}")

    # Старая схема: депозит и валюта жили прямо в users → переносим в accounts.
    has_deposit = "deposit" in user_cols
    has_currency = "currency" in user_cols
    if has_deposit or has_currency:
        select_cols = ["user_id"]
        if has_deposit:
            select_cols.append("deposit")
        if has_currency:
            select_cols.append("currency")
        q = f"SELECT {', '.join(select_cols)} FROM users"
        for row in cur.execute(q):
            uid = row[0]
            dep = row[1] if has_deposit else 0.0
            curr = row[2] if has_currency else DEFAULT_CURRENCY
            _ensure_account(cur, uid, "Основной", curr, dep)

    # Пользователи без счёта (новая схема) — заводим основной счёт.
    for (uid,) in cur.execute("SELECT user_id FROM users"):
        acc = cur.execute(
            "SELECT id FROM accounts WHERE user_id=? ORDER BY id ASC LIMIT 1", (uid,)
        ).fetchone()
        if not acc:
            _ensure_account(cur, uid, "Основной", DEFAULT_CURRENCY, 0.0)
        else:
            cur.execute(
                "UPDATE users SET active_account_id=? WHERE user_id=? AND (active_account_id IS NULL OR active_account_id = 0)",
                (acc[0], uid),
            )

    # Операции без счёта привязываем к активному счёту пользователя.
    cur.execute(
        """
        UPDATE operations
        SET account_id = COALESCE(
            (SELECT active_account_id FROM users WHERE users.user_id = operations.user_id), 0)
        WHERE account_id = 0
        """
    )

    # Убираем устаревшие колонки users, если SQLite позволяет.
    for col in ("deposit", "currency"):
        if col in _table_cols(cur, "users"):
            try:
                cur.execute(f"ALTER TABLE users DROP COLUMN {col}")
            except Exception:
                pass

    conn.commit()


# ==================== Счета ====================


def get_active_account(user_id: int):
    """Возвращает кортеж (id, name, deposit, currency) активного счёта или None."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT a.id, a.name, a.deposit, a.currency
        FROM accounts a
        JOIN users u ON u.active_account_id = a.id
        WHERE u.user_id = ?
        """,
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()
    if row:
        return tuple(row)
    accounts = get_accounts(user_id)
    return accounts[0] if accounts else None


def get_active_account_id(user_id: int) -> int | None:
    acc = get_active_account(user_id)
    return acc[0] if acc else None


def get_accounts(user_id: int):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, deposit, currency FROM accounts WHERE user_id = ? ORDER BY id ASC",
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [tuple(r) for r in rows]


def get_account(account_id: int):
    """Кортеж (id, user_id, name, deposit, currency)."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, user_id, name, deposit, currency FROM accounts WHERE id = ?",
        (account_id,),
    )
    row = cur.fetchone()
    conn.close()
    return tuple(row) if row else None


def ensure_default_account(user_id: int):
    """Гарантирует существование активного счёта (для онбординга)."""
    acc = get_active_account(user_id)
    if acc:
        return acc
    conn = _connect()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    _ensure_account(cur, user_id, "Основной", DEFAULT_CURRENCY, 0.0)
    conn.commit()
    conn.close()
    return get_active_account(user_id)


def set_active_account(user_id: int, account_id: int):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    cur.execute(
        "UPDATE users SET active_account_id = ? WHERE user_id = ?",
        (account_id, user_id),
    )
    conn.commit()
    conn.close()


def create_account(user_id: int, name: str, currency: str, deposit: float) -> int:
    """Создаёт счёт. Если deposit > 0, логирует операцию «Старт». Возвращает id счёта."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    cur.execute(
        "INSERT INTO accounts (user_id, name, deposit, currency, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, name, 0.0, currency, _now_utc_str()),
    )
    acc_id = cur.lastrowid
    if deposit > 0:
        cur.execute(
            "UPDATE accounts SET deposit = ? WHERE id = ?", (deposit, acc_id)
        )
        cur.execute(
            """
            INSERT INTO operations (user_id, account_id, date, op_type, pair, lot, side, result, amount, commission, balance_after, note, risk_pct)
            VALUES (?, ?, ?, 'Старт', '-', 0.0, '', '-', ?, 0.0, ?, '', 0.0)
            """,
            (user_id, acc_id, _now_utc_str(), deposit, deposit),
        )
    cur.execute(
        "SELECT active_account_id FROM users WHERE user_id = ?", (user_id,)
    )
    active = cur.fetchone()[0]
    if not active:
        cur.execute(
            "UPDATE users SET active_account_id = ? WHERE user_id = ?",
            (acc_id, user_id),
        )
    conn.commit()
    conn.close()
    return acc_id


def rename_account(account_id: int, name: str):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("UPDATE accounts SET name = ? WHERE id = ?", (name, account_id))
    conn.commit()
    conn.close()


def delete_account(user_id: int, account_id: int) -> bool:
    """Удаляет счёт и его операции. Если он был активным — переключает на другой."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM accounts WHERE id = ? AND user_id = ?", (account_id, user_id)
    )
    if not cur.fetchone():
        conn.close()
        return False
    cur.execute("DELETE FROM operations WHERE account_id = ?", (account_id,))
    cur.execute(
        "DELETE FROM accounts WHERE id = ? AND user_id = ?", (account_id, user_id)
    )
    cur.execute("SELECT active_account_id FROM users WHERE user_id = ?", (user_id,))
    if cur.fetchone()[0] == account_id:
        nxt = cur.execute(
            "SELECT id FROM accounts WHERE user_id = ? ORDER BY id ASC LIMIT 1",
            (user_id,),
        ).fetchone()
        cur.execute(
            "UPDATE users SET active_account_id = ? WHERE user_id = ?",
            (nxt[0] if nxt else 0, user_id),
        )
    conn.commit()
    conn.close()
    return True


def set_account_deposit_and_currency(
    user_id: int, account_id: int, deposit: float, currency: str
):
    """Онбординг: задаёт депозит и валюту счёта (логирует операцию «Старт»)."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    cur.execute(
        "UPDATE accounts SET deposit = ?, currency = ? WHERE id = ? AND user_id = ?",
        (deposit, currency, account_id, user_id),
    )
    cur.execute(
        "SELECT COUNT(*) FROM operations WHERE account_id = ? AND op_type = 'Старт'",
        (account_id,),
    )
    if cur.fetchone()[0] == 0:
        cur.execute(
            """
            INSERT INTO operations (user_id, account_id, date, op_type, pair, lot, side, result, amount, commission, balance_after, note, risk_pct)
            VALUES (?, ?, ?, 'Старт', '-', 0.0, '', '-', ?, 0.0, ?, '', 0.0)
            """,
            (user_id, account_id, _now_utc_str(), deposit, deposit),
        )
    conn.commit()
    conn.close()


def change_account_currency(account_id: int, currency: str):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("UPDATE accounts SET currency = ? WHERE id = ?", (currency, account_id))
    conn.commit()
    conn.close()


def get_user_deposit(user_id: int) -> float:
    acc = get_active_account(user_id)
    return acc[2] if acc else 0.0


def get_user_currency(user_id: int) -> str:
    acc = get_active_account(user_id)
    return acc[3] if acc else DEFAULT_CURRENCY


# ==================== Операции ====================


def _insert_operation(
    cur,
    user_id: int,
    account_id: int,
    date_str: str,
    op_type: str,
    pair: str,
    lot: float,
    side: str,
    result: str,
    amount: float,
    commission: float,
    note: str,
    risk_pct: float,
):
    cur.execute(
        """
        INSERT INTO operations (user_id, account_id, date, op_type, pair, lot, side, result, amount, commission, balance_after, note, risk_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?)
        """,
        (
            user_id,
            account_id,
            date_str,
            op_type,
            pair,
            lot,
            side,
            result,
            amount,
            commission,
            note,
            risk_pct,
        ),
    )


def add_trade_operation(
    user_id: int,
    account_id: int,
    date_str: str,
    pair: str,
    lot: float,
    side: str,
    result: str,
    amount: float,
    commission: float = 0.0,
    note: str = "",
    risk_pct: float = 0.0,
):
    conn = _connect()
    cur = conn.cursor()
    _insert_operation(
        cur,
        user_id,
        account_id,
        date_str,
        "Сделка",
        pair,
        lot,
        side,
        result,
        amount,
        commission,
        note,
        risk_pct,
    )
    conn.commit()
    conn.close()
    recalc_account_balance(account_id)


def log_balance_operation(
    user_id: int,
    account_id: int,
    op_type: str,
    amount: float,
    note: str = "",
    date_str: str | None = None,
):
    date_str = date_str or _now_utc_str()
    conn = _connect()
    cur = conn.cursor()
    _insert_operation(
        cur,
        user_id,
        account_id,
        date_str,
        op_type,
        "-",
        0.0,
        "",
        "-",
        amount,
        0.0,
        note,
        0.0,
    )
    conn.commit()
    conn.close()
    recalc_account_balance(account_id)


def get_operations(account_id: int):
    """Операции счёта (по возрастанию id). Порядок колонок совместим со старым кодом:
    (date, op_type, pair, lot, result, amount, balance_after, note, risk_pct, side, commission, id)."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT date, op_type, pair, lot, result, amount, balance_after, note, risk_pct, side, commission, id
        FROM operations
        WHERE account_id = ?
        ORDER BY id ASC
        """,
        (account_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_user_operations(user_id: int):
    account_id = get_active_account_id(user_id)
    if not account_id:
        return []
    return get_operations(account_id)


def get_operations_total(account_id: int) -> int:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM operations WHERE account_id = ?", (account_id,)
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0


def get_operations_page(account_id: int, page: int, per_page: int = 6):
    """Страница операций (по убыванию id). Возвращает (rows, total).
    Строка: (id, date, op_type, pair, lot, result, amount, balance_after, note, risk_pct, side, commission)."""
    conn = _connect()
    cur = conn.cursor()
    total = cur.execute(
        "SELECT COUNT(*) FROM operations WHERE account_id = ?", (account_id,)
    ).fetchone()[0]
    cur.execute(
        """
        SELECT id, date, op_type, pair, lot, result, amount, balance_after, note, risk_pct, side, commission
        FROM operations
        WHERE account_id = ?
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        (account_id, per_page, (page - 1) * per_page),
    )
    rows = cur.fetchall()
    conn.close()
    return rows, total


def get_operation(account_id: int, op_id: int):
    """Операция с id. (id, date, op_type, pair, lot, result, amount, balance_after, note, risk_pct, side, commission)."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, date, op_type, pair, lot, result, amount, balance_after, note, risk_pct, side, commission
        FROM operations
        WHERE id = ? AND account_id = ?
        """,
        (op_id, account_id),
    )
    row = cur.fetchone()
    conn.close()
    return tuple(row) if row else None


def get_trades(account_id: int):
    """Сделки счёта (по убыванию id). (id, date, pair, lot, side, result, amount, note, risk_pct)."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, date, pair, lot, side, result, amount, note, risk_pct
        FROM operations
        WHERE account_id = ? AND op_type = 'Сделка'
        ORDER BY id DESC
        """,
        (account_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_trade(account_id: int, trade_id: int):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, date, pair, lot, side, result, amount, note, risk_pct
        FROM operations
        WHERE id = ? AND account_id = ? AND op_type = 'Сделка'
        """,
        (trade_id, account_id),
    )
    row = cur.fetchone()
    conn.close()
    return tuple(row) if row else None


def update_trade_amount(account_id: int, trade_id: int, new_amount: float):
    result = "Win" if new_amount >= 0 else "Loss"
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE operations SET amount = ?, result = ? WHERE id = ? AND account_id = ? AND op_type = 'Сделка'",
        (new_amount, result, trade_id, account_id),
    )
    conn.commit()
    conn.close()
    recalc_account_balance(account_id)


def update_trade_note(account_id: int, trade_id: int, note: str):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE operations SET note = ? WHERE id = ? AND account_id = ? AND op_type = 'Сделка'",
        (note, trade_id, account_id),
    )
    conn.commit()
    conn.close()


def update_trade_risk(account_id: int, trade_id: int, risk_pct: float):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE operations SET risk_pct = ? WHERE id = ? AND account_id = ? AND op_type = 'Сделка'",
        (risk_pct, trade_id, account_id),
    )
    conn.commit()
    conn.close()


def delete_operation(account_id: int, op_id: int) -> bool:
    """Удаляет операцию и пересчитывает баланс. Операцию «Старт» удалить нельзя."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT op_type FROM operations WHERE id = ? AND account_id = ?",
        (op_id, account_id),
    )
    row = cur.fetchone()
    if not row or row[0] == "Старт":
        conn.close()
        return False
    cur.execute(
        "DELETE FROM operations WHERE id = ? AND account_id = ?", (op_id, account_id)
    )
    conn.commit()
    conn.close()
    recalc_account_balance(account_id)
    return True


def recalc_account_balance(account_id: int):
    """Пересчитывает balance_after для всех операций счёта и финальный депозит."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, amount FROM operations WHERE account_id = ? ORDER BY id ASC",
        (account_id,),
    )
    rows = cur.fetchall()
    balance = 0.0
    for op_id, amount in rows:
        balance = max(0.0, balance + (amount or 0.0))
        cur.execute(
            "UPDATE operations SET balance_after = ? WHERE id = ?", (balance, op_id)
        )
    cur.execute(
        "UPDATE accounts SET deposit = ? WHERE id = ?", (balance, account_id)
    )
    conn.commit()
    conn.close()


def recalc_all_accounts():
    conn = _connect()
    cur = conn.cursor()
    ids = [r[0] for r in cur.execute("SELECT id FROM accounts")]
    conn.close()
    for acc_id in ids:
        recalc_account_balance(acc_id)


def import_operations(user_id: int, account_id: int, ops):
    """Пакетный импорт операций (список словарей от utils.importer). Вставляет
    все строки и пересчитывает баланс один раз."""
    conn = _connect()
    cur = conn.cursor()
    for o in ops:
        _insert_operation(
            cur,
            user_id,
            account_id,
            o["date"],
            o["op_type"],
            o["pair"],
            o["lot"],
            o["side"],
            o["result"],
            o["amount"],
            o["commission"],
            o["note"],
            o["risk_pct"],
        )
    conn.commit()
    conn.close()
    recalc_account_balance(account_id)


def get_user_pairs(account_id: int):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT pair FROM operations
        WHERE account_id = ? AND op_type = 'Сделка' AND pair != '-'
        ORDER BY pair ASC
        """,
        (account_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def reset_user_data(user_id: int):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM operations WHERE user_id = ?", (user_id,))
    cur.execute("DELETE FROM accounts WHERE user_id = ?", (user_id,))
    cur.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    cur.execute("DELETE FROM fsm_states WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# ==================== Настройки пользователя ====================


def get_user_tz_offset(user_id: int) -> int:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT tz_offset FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0


def set_user_tz_offset(user_id: int, minutes: int):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    cur.execute(
        "UPDATE users SET tz_offset = ? WHERE user_id = ?", (minutes, user_id)
    )
    conn.commit()
    conn.close()


def get_daily_report(user_id: int) -> bool:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT daily_report FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return bool(row[0]) if row else False


def set_daily_report(user_id: int, enabled: bool):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    cur.execute(
        "UPDATE users SET daily_report = ? WHERE user_id = ?",
        (1 if enabled else 0, user_id),
    )
    conn.commit()
    conn.close()


def get_report_users():
    """Пользователи с включённым ежедневным отчётом: (user_id, tz_offset, account_id)."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id, tz_offset, active_account_id FROM users
        WHERE daily_report = 1 AND active_account_id != 0
        """
    )
    rows = cur.fetchall()
    conn.close()
    return [tuple(r) for r in rows]
