import math

from aiogram import types

from config import ADMIN_ID
from database import get_accounts, get_user_pairs


def _nav_row(current: int, total: int, per_page: int, prefix: str):
    pages = max(1, math.ceil(total / per_page))
    row = []
    if current > 1:
        row.append(
            types.InlineKeyboardButton(
                text="◀️", callback_data=f"{prefix}_page_{current - 1}"
            )
        )
    row.append(
        types.InlineKeyboardButton(text=f"{current}/{pages}", callback_data="noop")
    )
    if current < pages:
        row.append(
            types.InlineKeyboardButton(
                text="▶️", callback_data=f"{prefix}_page_{current + 1}"
            )
        )
    return row


# --- Главное меню ---
def get_main_keyboard(user_id: int):
    keyboard = [
        [
            types.InlineKeyboardButton(
                text="➕ Добавить сделку", callback_data="action_add_trade"
            )
        ],
        [
            types.InlineKeyboardButton(
                text="📜 История сделок", callback_data="action_history"
            )
        ],
        [
            types.InlineKeyboardButton(
                text="🟢 Пополнить депозит", callback_data="action_top_up"
            ),
            types.InlineKeyboardButton(
                text="🔴 Вывести с депозита", callback_data="action_withdraw"
            ),
        ],
        [
            types.InlineKeyboardButton(text="📊 Статистика", callback_data="action_stats"),
            types.InlineKeyboardButton(text="📈 График баланса", callback_data="action_chart"),
        ],
        [
            types.InlineKeyboardButton(text="📁 Скачать Excel", callback_data="action_excel"),
            types.InlineKeyboardButton(text="📥 Импорт истории", callback_data="action_import"),
        ],
        [
            types.InlineKeyboardButton(text="💼 Счета", callback_data="action_accounts"),
            types.InlineKeyboardButton(text="⚙️ Настройки", callback_data="action_settings"),
        ],
    ]

    row_admin = []
    if user_id == ADMIN_ID:
        row_admin.append(
            types.InlineKeyboardButton(
                text="💾 Резервная копия БД", callback_data="action_backup"
            )
        )
    row_admin.append(
        types.InlineKeyboardButton(text="🔄 Сброс данных", callback_data="action_reset")
    )
    keyboard.append(row_admin)
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


# --- История ---
def get_history_keyboard(
    page: int, total: int, per_page: int = 6, has_trades: bool = False
):
    keyboard = []
    nav = _nav_row(page, total, per_page, "hist")
    if nav:
        keyboard.append(nav)
    actions = []
    if has_trades:
        actions.append(
            types.InlineKeyboardButton(
                text="✏️ Изменить сделку", callback_data="edit_trade_menu"
            )
        )
    if total:
        actions.append(
            types.InlineKeyboardButton(
                text="🗑 Удалить операцию", callback_data="del_op_menu"
            )
        )
    if actions:
        keyboard.append(actions)
    keyboard.append(
        [types.InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")]
    )
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_del_ops_keyboard(rows, page: int, total: int, per_page: int = 8):
    keyboard = []
    for op_id, date, op_type, *_ in rows:
        label = f"🗑 {date[8:10]}.{date[5:7]} {op_type}"
        keyboard.append(
            [
                types.InlineKeyboardButton(
                    text=label, callback_data=f"del_op_{op_id}"
                )
            ]
        )
    nav = _nav_row(page, total, per_page, "del")
    if nav:
        keyboard.append(nav)
    keyboard.append(
        [
            types.InlineKeyboardButton(
                text="◀️ Назад к истории", callback_data="action_history"
            )
        ]
    )
    keyboard.append(
        [types.InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")]
    )
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_edit_trades_keyboard(rows, page: int, total: int, per_page: int = 8):
    keyboard = []
    for trade_id, date, pair, lot, *_ in rows:
        label = f"✏️ {date[8:10]}.{date[5:7]} {pair} ({lot})"
        keyboard.append(
            [
                types.InlineKeyboardButton(
                    text=label, callback_data=f"edit_trade_{trade_id}"
                )
            ]
        )
    nav = _nav_row(page, total, per_page, "edit")
    if nav:
        keyboard.append(nav)
    keyboard.append(
        [
            types.InlineKeyboardButton(
                text="◀️ Назад к истории", callback_data="action_history"
            )
        ]
    )
    keyboard.append(
        [types.InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")]
    )
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_edit_trade_keyboard(trade_id: int):
    keyboard = [
        [
            types.InlineKeyboardButton(
                text="💰 Сумма / исход", callback_data="edit_field_amount"
            )
        ],
        [
            types.InlineKeyboardButton(
                text="✍️ Заметка", callback_data="edit_field_note"
            ),
            types.InlineKeyboardButton(text="🛡 Риск", callback_data="edit_field_risk"),
        ],
        [
            types.InlineKeyboardButton(
                text="◀️ К списку сделок", callback_data="edit_trade_menu"
            )
        ],
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


# --- Счета ---
def get_accounts_keyboard(user_id: int, active_id: int):
    keyboard = []
    for acc_id, name, deposit, currency in get_accounts(user_id):
        mark = "▶️ " if acc_id == active_id else ""
        keyboard.append(
            [
                types.InlineKeyboardButton(
                    text=f"{mark}{name} — {deposit:.2f} {currency}",
                    callback_data=f"switch_acc_{acc_id}",
                )
            ]
        )
    keyboard.append(
        [
            types.InlineKeyboardButton(
                text="➕ Создать счёт", callback_data="acc_create"
            )
        ]
    )
    keyboard.append(
        [
            types.InlineKeyboardButton(
                text="✏️ Переименовать", callback_data="acc_rename_menu"
            ),
            types.InlineKeyboardButton(
                text="🗑 Удалить счёт", callback_data="acc_delete_menu"
            ),
        ]
    )
    keyboard.append(
        [types.InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")]
    )
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_account_select_keyboard(user_id: int, action: str):
    """Клавиатура выбора счёта для переименования (acc_ren) или удаления (acc_del)."""
    keyboard = []
    for acc_id, name, deposit, currency in get_accounts(user_id):
        keyboard.append(
            [
                types.InlineKeyboardButton(
                    text=f"{name} — {deposit:.2f} {currency}",
                    callback_data=f"{action}_{acc_id}",
                )
            ]
        )
    keyboard.append(
        [
            types.InlineKeyboardButton(
                text="◀️ Назад к счетам", callback_data="action_accounts"
            )
        ]
    )
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


# --- Настройки ---
def get_settings_keyboard(tz_offset: int, daily_report: bool):
    hours = tz_offset / 60
    tz_label = f"UTC{'+' if hours >= 0 else '-'}{abs(hours):g}"
    report_label = "✅ Включён" if daily_report else "❌ Выключен"
    keyboard = [
        [
            types.InlineKeyboardButton(
                text=f"🌍 Часовой пояс ({tz_label})", callback_data="action_tz"
            )
        ],
        [
            types.InlineKeyboardButton(
                text=f"📈 Ежедневный отчёт: {report_label}",
                callback_data="action_toggle_report",
            )
        ],
        [
            types.InlineKeyboardButton(
                text="💱 Сменить валюту счёта", callback_data="action_change_currency"
            )
        ],
    ]
    keyboard.append(
        [types.InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")]
    )
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


# --- Прочее ---
def get_currency_keyboard():
    keyboard = [
        [
            types.InlineKeyboardButton(text="💵 USD ($)", callback_data="curr_USD"),
            types.InlineKeyboardButton(text="💶 EUR (€)", callback_data="curr_EUR"),
        ],
        [types.InlineKeyboardButton(text="🪙 USDT", callback_data="curr_USDT")],
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_pairs_keyboard(account_id: int):
    pairs = get_user_pairs(account_id)
    keyboard = []
    for p in pairs:
        keyboard.append(
            [types.InlineKeyboardButton(text=f"🔹 {p}", callback_data=f"sel_pair_{p}")]
        )
    keyboard.append(
        [
            types.InlineKeyboardButton(
                text="✍️ Другая пара (ввести текстом)", callback_data="sel_pair_custom"
            )
        ]
    )
    keyboard.append(
        [types.InlineKeyboardButton(text="◀️ Отмена", callback_data="main_menu")]
    )
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_side_keyboard():
    keyboard = [
        [
            types.InlineKeyboardButton(text="🟢 Buy", callback_data="side_buy"),
            types.InlineKeyboardButton(text="🔴 Sell", callback_data="side_sell"),
        ],
        [types.InlineKeyboardButton(text="◀️ Отмена", callback_data="main_menu")],
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_date_keyboard():
    keyboard = [
        [
            types.InlineKeyboardButton(text="📅 Сегодня", callback_data="opdate_today"),
            types.InlineKeyboardButton(text="↩️ Вчера", callback_data="opdate_yesterday"),
        ],
        [
            types.InlineKeyboardButton(
                text="✍️ Своя дата (ДД.ММ.ГГГГ)", callback_data="opdate_custom"
            )
        ],
        [types.InlineKeyboardButton(text="◀️ Отмена", callback_data="main_menu")],
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_stats_keyboard(account_id: int):
    pairs = get_user_pairs(account_id)
    keyboard = [
        [
            types.InlineKeyboardButton(text="📅 За день", callback_data="stats_day"),
            types.InlineKeyboardButton(text="📆 За неделю", callback_data="stats_week"),
        ],
        [
            types.InlineKeyboardButton(text="🗓 За месяц", callback_data="stats_month"),
            types.InlineKeyboardButton(text="🌐 Вся история", callback_data="stats_all"),
        ],
        [
            types.InlineKeyboardButton(
                text="⏱ Произвольный период", callback_data="stats_custom"
            )
        ],
    ]
    if pairs:
        pair_buttons = [
            types.InlineKeyboardButton(
                text=f"🔍 Пара: {p}", callback_data=f"stats_pair_{p}"
            )
            for p in pairs
        ]
        keyboard.append(pair_buttons)
    keyboard.append(
        [types.InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")]
    )
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_back_keyboard():
    keyboard = [
        [types.InlineKeyboardButton(text="◀️ Отмена / Меню", callback_data="main_menu")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)
