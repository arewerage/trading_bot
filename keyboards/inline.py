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


def _back_button(back_to: str):
    """Кнопка «Назад» в мастере: возвращает к шагу back_to."""
    return types.InlineKeyboardButton(
        text="◀️ Назад", callback_data=f"wb_{back_to}"
    )


def get_wizard_keyboard(back_to: str | None = None):
    """Клавиатура шага мастера: [◀️ Назад] [🏠 Меню]."""
    row = []
    if back_to:
        row.append(_back_button(back_to))
    row.append(types.InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"))
    return types.InlineKeyboardMarkup(inline_keyboard=[row])


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
                text="🟢 Пополнение", callback_data="action_top_up"
            ),
            types.InlineKeyboardButton(
                text="🔴 Вывод", callback_data="action_withdraw"
            ),
        ],
        [
            types.InlineKeyboardButton(text="📊 Аналитика", callback_data="action_analytics")
        ],
        [
            types.InlineKeyboardButton(text="💼 Счета", callback_data="action_accounts"),
            types.InlineKeyboardButton(text="⚙️ Настройки", callback_data="action_settings"),
        ],
        [
            types.InlineKeyboardButton(text="🗂 Данные", callback_data="action_data")
        ],
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


# --- Подменю «Аналитика» ---
def get_analytics_keyboard():
    keyboard = [
        [
            types.InlineKeyboardButton(text="📊 Статистика", callback_data="action_stats"),
            types.InlineKeyboardButton(text="📈 График баланса", callback_data="action_chart"),
        ],
        [
            types.InlineKeyboardButton(text="📁 Скачать Excel", callback_data="action_excel"),
        ],
        [
            types.InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu"),
        ],
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


# --- Подменю «Данные» ---
def get_data_keyboard(user_id: int):
    keyboard = [
        [
            types.InlineKeyboardButton(
                text="📥 Импорт истории", callback_data="action_import"
            ),
        ],
    ]
    if user_id == ADMIN_ID:
        keyboard.append(
            [
                types.InlineKeyboardButton(
                    text="💾 Резервная копия БД", callback_data="action_backup"
                )
            ]
        )
        keyboard.append(
            [
                types.InlineKeyboardButton(
                    text="📊 Отчёт сейчас", callback_data="action_report_now"
                )
            ]
        )
        keyboard.append(
            [
                types.InlineKeyboardButton(
                    text="📢 Сообщение всем", callback_data="action_broadcast"
                )
            ]
        )
    keyboard.append(
        [
            types.InlineKeyboardButton(text="🔄 Сброс данных", callback_data="action_reset"),
        ]
    )
    keyboard.append(
        [
            types.InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu"),
        ]
    )
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


# --- История ---
def get_history_keyboard(
    page: int,
    total: int,
    per_page: int = 6,
    has_trades: bool = False,
    op_filter: str = "all",
):
    keyboard = []
    nav = _nav_row(page, total, per_page, "hist")
    if nav:
        keyboard.append(nav)
    keyboard.append(
        [
            types.InlineKeyboardButton(
                text="✅ 📜 Все" if op_filter == "all" else "📜 Все",
                callback_data="hist_filter_all",
            ),
            types.InlineKeyboardButton(
                text="✅ 🔹 Сделки" if op_filter == "trades" else "🔹 Сделки",
                callback_data="hist_filter_trades",
            ),
        ]
    )
    keyboard.append(
        [
            types.InlineKeyboardButton(
                text="✅ 🟢 Пополнения" if op_filter == "deposits" else "🟢 Пополнения",
                callback_data="hist_filter_deposits",
            ),
            types.InlineKeyboardButton(
                text="✅ 🔴 Выводы" if op_filter == "withdrawals" else "🔴 Выводы",
                callback_data="hist_filter_withdrawals",
            ),
        ]
    )
    actions = []
    if has_trades:
        actions.append(
            types.InlineKeyboardButton(
                text="✏️ Изменить сделку", callback_data="edit_trade_menu"
            )
        )
    actions.append(
        types.InlineKeyboardButton(
            text="✏️ Пополнение/вывод", callback_data="edit_op_menu"
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


def get_edit_ops_keyboard(rows, page: int, total: int, per_page: int = 8):
    keyboard = []
    for op_id, date, op_type, amount, _ in rows:
        label = f"✏️ {date[8:10]}.{date[5:7]} {op_type} ({amount:+.2f})"
        keyboard.append(
            [
                types.InlineKeyboardButton(
                    text=label, callback_data=f"edit_op_{op_id}"
                )
            ]
        )
    nav = _nav_row(page, total, per_page, "editop")
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


def get_edit_op_keyboard(op_id: int):
    keyboard = [
        [
            types.InlineKeyboardButton(
                text="📅 Дата", callback_data="edit_op_field_date"
            ),
            types.InlineKeyboardButton(
                text="💰 Сумма", callback_data="edit_op_field_amount"
            ),
        ],
        [
            types.InlineKeyboardButton(
                text="✍️ Заметка", callback_data="edit_op_field_note"
            ),
        ],
        [
            types.InlineKeyboardButton(
                text="◀️ К списку операций", callback_data="edit_op_menu"
            ),
        ],
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_edit_trade_keyboard(trade_id: int):
    keyboard = [
        [
            types.InlineKeyboardButton(
                text="📅 Дата", callback_data="edit_field_date"
            ),
            types.InlineKeyboardButton(text="🔹 Пара", callback_data="edit_field_pair"),
        ],
        [
            types.InlineKeyboardButton(text="📐 Лот", callback_data="edit_field_lot"),
            types.InlineKeyboardButton(text="↔️ Сторона", callback_data="edit_field_side"),
        ],
        [
            types.InlineKeyboardButton(
                text="💰 Сумма / исход", callback_data="edit_field_amount"
            ),
            types.InlineKeyboardButton(
                text="💸 Комиссия", callback_data="edit_field_commission"
            ),
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
            ),
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


def get_pairs_keyboard(account_id: int, prefix: str = "sel_pair", back_to: str | None = None):
    pairs = get_user_pairs(account_id)
    keyboard = []
    for p in pairs:
        keyboard.append(
            [types.InlineKeyboardButton(text=f"🔹 {p}", callback_data=f"{prefix}_{p}")]
        )
    keyboard.append(
        [
            types.InlineKeyboardButton(
                text="✍️ Другая пара (ввести текстом)", callback_data=f"{prefix}_custom"
            )
        ]
    )
    row = []
    if back_to:
        row.append(_back_button(back_to))
    row.append(types.InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"))
    keyboard.append(row)
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_side_keyboard(prefix: str = "side", back_to: str | None = None):
    keyboard = [
        [
            types.InlineKeyboardButton(text="🟢 Buy", callback_data=f"{prefix}_buy"),
            types.InlineKeyboardButton(text="🔴 Sell", callback_data=f"{prefix}_sell"),
        ],
    ]
    row = []
    if back_to:
        row.append(_back_button(back_to))
    row.append(types.InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"))
    keyboard.append(row)
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_date_keyboard(prefix: str = "opdate", back_to: str | None = None):
    keyboard = [
        [
            types.InlineKeyboardButton(text="📅 Сегодня", callback_data=f"{prefix}_today"),
            types.InlineKeyboardButton(text="↩️ Вчера", callback_data=f"{prefix}_yesterday"),
        ],
        [
            types.InlineKeyboardButton(
                text="✍️ Своя дата (ДД.ММ.ГГГГ)", callback_data=f"{prefix}_custom"
            )
        ],
    ]
    row = []
    if back_to:
        row.append(_back_button(back_to))
    row.append(types.InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"))
    keyboard.append(row)
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
        [types.InlineKeyboardButton(text="📊 По парам", callback_data="stats_pairs")]
    )
    keyboard.append(
        [types.InlineKeyboardButton(text="◀️ В аналитику", callback_data="action_analytics")]
    )
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_chart_keyboard():
    keyboard = [
        [
            types.InlineKeyboardButton(text="🌐 Всё", callback_data="chart_all"),
            types.InlineKeyboardButton(text="🗓 Месяц", callback_data="chart_month"),
            types.InlineKeyboardButton(text="📆 Неделя", callback_data="chart_week"),
        ],
        [
            types.InlineKeyboardButton(text="◀️ В аналитику", callback_data="action_analytics"),
        ],
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_excel_keyboard():
    keyboard = [
        [
            types.InlineKeyboardButton(text="🌐 Всё", callback_data="excel_all"),
            types.InlineKeyboardButton(text="📅 Сегодня", callback_data="excel_today"),
        ],
        [
            types.InlineKeyboardButton(text="📆 Неделя", callback_data="excel_week"),
            types.InlineKeyboardButton(text="🗓 Месяц", callback_data="excel_month"),
        ],
        [
            types.InlineKeyboardButton(
                text="⏱ Свой период", callback_data="excel_custom"
            ),
        ],
        [
            types.InlineKeyboardButton(
                text="◀️ В аналитику", callback_data="action_analytics"
            ),
        ],
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_report_keyboard():
    keyboard = [
        [
            types.InlineKeyboardButton(text="🔄 Ещё раз", callback_data="report_again"),
            types.InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
        ]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_back_keyboard():
    keyboard = [
        [types.InlineKeyboardButton(text="◀️ Отмена / Меню", callback_data="main_menu")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)
