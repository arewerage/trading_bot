import os
import sqlite3
import json
from datetime import datetime
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.fsm.state import State

# Указываем папку и путь к базе данных
DB_DIR = "data"
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR, exist_ok=True)
DB_NAME = os.path.join(DB_DIR, "trading_bot.db")

class SQLiteFSMStorage(BaseStorage):
    """Персистентное хранилище состояний FSM на базе SQLite"""
    def __init__(self, db_path=DB_NAME):
        self.db_path = db_path
        self._init_fsm_table()

    def _init_fsm_table(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fsm_states (
                bot_id INTEGER,
                chat_id INTEGER,
                user_id INTEGER,
                state TEXT,
                data TEXT,
                PRIMARY KEY (bot_id, chat_id, user_id)
            )
        """)
        conn.commit()
        conn.close()

    async def set_state(self, key: StorageKey, state: State | str | None = None) -> None:
        state_str = state.state if isinstance(state, State) else state
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO fsm_states (bot_id, chat_id, user_id, state, data)
            VALUES (?, ?, ?, ?, COALESCE((SELECT data FROM fsm_states WHERE bot_id=? AND chat_id=? AND user_id=?), '{}'))
            ON CONFLICT(bot_id, chat_id, user_id) DO UPDATE SET state = ?
        """, (key.bot_id, key.chat_id, key.user_id, state_str, key.bot_id, key.chat_id, key.user_id, state_str))
        conn.commit()
        conn.close()

    async def get_state(self, key: StorageKey) -> str | None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT state FROM fsm_states WHERE bot_id = ? AND chat_id = ? AND user_id = ?",
                       (key.bot_id, key.chat_id, key.user_id))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row and row[0] else None

    async def set_data(self, key: StorageKey, data: dict) -> None:
        data_str = json.dumps(data)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO fsm_states (bot_id, chat_id, user_id, state, data)
            VALUES (?, ?, ?, (SELECT state FROM fsm_states WHERE bot_id=? AND chat_id=? AND user_id=?), ?)
            ON CONFLICT(bot_id, chat_id, user_id) DO UPDATE SET data = ?
        """, (key.bot_id, key.chat_id, key.user_id, key.bot_id, key.chat_id, key.user_id, data_str, data_str))
        conn.commit()
        conn.close()

    async def get_data(self, key: StorageKey) -> dict:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT data FROM fsm_states WHERE bot_id = ? AND chat_id = ? AND user_id = ?",
                       (key.bot_id, key.chat_id, key.user_id))
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


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            deposit REAL DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,
            op_type TEXT,          -- "Старт", "Пополнение", "Вывод", "Сделка"
            pair TEXT,             -- Пара (для сделок)
            lot REAL,              -- Лот (для сделок)
            result TEXT,           -- "Win" / "Loss" (для сделок)
            amount REAL,           -- Изменение суммы (+/-)
            balance_after REAL,    -- Депозит после операции
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)

    conn.commit()
    conn.close()

def set_user_deposit(user_id: int, deposit: float, op_type="Старт", amount=0.0):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO users (user_id, deposit) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET deposit = ?
    """, (user_id, deposit, deposit))

    cursor.execute("""
        INSERT INTO operations (user_id, date, op_type, pair, lot, result, amount, balance_after)
        VALUES (?, ?, ?, '-', 0.0, '-', ?, ?)
    """, (user_id, date_str, op_type, amount, deposit))

    conn.commit()
    conn.close()

def log_balance_operation(user_id: int, op_type: str, amount: int | float, new_deposit: float):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("UPDATE users SET deposit = ? WHERE user_id = ?", (new_deposit, user_id))

    cursor.execute("""
        INSERT INTO operations (user_id, date, op_type, pair, lot, result, amount, balance_after)
        VALUES (?, ?, ?, '-', 0.0, '-', ?, ?)
    """, (user_id, date_str, op_type, amount, new_deposit))

    conn.commit()
    conn.close()

def get_user_deposit(user_id: int) -> float:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT deposit FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0.0

def add_trade_operation(user_id: int, pair: str, lot: float, result: str, profit_loss: float, new_deposit: float):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("UPDATE users SET deposit = ? WHERE user_id = ?", (new_deposit, user_id))

    cursor.execute("""
        INSERT INTO operations (user_id, date, op_type, pair, lot, result, amount, balance_after)
        VALUES (?, ?, 'Сделка', ?, ?, ?, ?, ?)
    """, (user_id, date_str, pair, lot, result, profit_loss, new_deposit))

    conn.commit()
    conn.close()

def get_user_operations(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT date, op_type, pair, lot, result, amount, balance_after
        FROM operations
        WHERE user_id = ?
        ORDER BY id ASC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_user_pairs(user_id: int):
    """Получить список всех уникальных торговых пар пользователя"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT pair FROM operations
        WHERE user_id = ? AND op_type = 'Сделка' AND pair != '-'
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

def reset_user_data(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM operations WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM fsm_states WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
