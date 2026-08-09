import math

from aiogram import types

from config import ADMIN_ID
from database import get_accounts, get_user_pairs
from utils.i18n import lang_name, op_type_label, t


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


def _back_button(back_to: str, lang: str = "ru"):
    """Кнопка «Назад» в мастере: возвращает к шагу back_to."""
    return types.InlineKeyboardButton(
        text=t(lang, "kb.back"), callback_data=f"wb_{back_to}"
    )


def get_wizard_keyboard(back_to: str | None = None, lang: str = "ru"):
    """Клавиатура шага мастера: [◀️ Назад] [🏠 Меню]."""
    row = []
    if back_to:
        row.append(_back_button(back_to, lang))
    row.append(types.InlineKeyboardButton(text=t(lang, "kb.menu"), callback_data="main_menu"))
    return types.InlineKeyboardMarkup(inline_keyboard=[row])


# --- Главное меню ---
def get_main_keyboard(user_id: int, lang: str = "ru"):
    keyboard = [
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.add_trade"), callback_data="action_add_trade"
            )
        ],
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.history"), callback_data="action_history"
            )
        ],
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.top_up"), callback_data="action_top_up"
            ),
            types.InlineKeyboardButton(
                text=t(lang, "kb.withdraw"), callback_data="action_withdraw"
            ),
        ],
        [
            types.InlineKeyboardButton(text=t(lang, "kb.analytics"), callback_data="action_analytics")
        ],
        [
            types.InlineKeyboardButton(text=t(lang, "kb.accounts"), callback_data="action_accounts"),
            types.InlineKeyboardButton(text=t(lang, "kb.settings"), callback_data="action_settings"),
        ],
        [
            types.InlineKeyboardButton(text=t(lang, "kb.data"), callback_data="action_data")
        ],
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


# --- Подменю «Аналитика» ---
def get_analytics_keyboard(lang: str = "ru"):
    keyboard = [
        [
            types.InlineKeyboardButton(text=t(lang, "kb.stats"), callback_data="action_stats"),
            types.InlineKeyboardButton(text=t(lang, "kb.chart"), callback_data="action_chart"),
        ],
        [
            types.InlineKeyboardButton(text=t(lang, "kb.excel"), callback_data="action_excel"),
        ],
        [
            types.InlineKeyboardButton(text=t(lang, "kb.back_main"), callback_data="main_menu"),
        ],
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


# --- Подменю «Данные» ---
def get_data_keyboard(user_id: int, lang: str = "ru"):
    keyboard = [
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.import_data"), callback_data="action_import"
            ),
        ],
    ]
    if user_id == ADMIN_ID:
        keyboard.append(
            [
                types.InlineKeyboardButton(
                    text=t(lang, "kb.backup"), callback_data="action_backup"
                )
            ]
        )
        keyboard.append(
            [
                types.InlineKeyboardButton(
                    text=t(lang, "kb.report_now"), callback_data="action_report_now"
                )
            ]
        )
        keyboard.append(
            [
                types.InlineKeyboardButton(
                    text=t(lang, "kb.broadcast"), callback_data="action_broadcast"
                )
            ]
        )
    keyboard.append(
        [
            types.InlineKeyboardButton(text=t(lang, "kb.reset"), callback_data="action_reset"),
        ]
    )
    keyboard.append(
        [
            types.InlineKeyboardButton(text=t(lang, "kb.back_main"), callback_data="main_menu"),
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
    lang: str = "ru",
):
    keyboard = []
    nav = _nav_row(page, total, per_page, "hist")
    if nav:
        keyboard.append(nav)
    keyboard.append(
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.hist_all_active")
                if op_filter == "all"
                else t(lang, "kb.hist_all"),
                callback_data="hist_filter_all",
            ),
            types.InlineKeyboardButton(
                text=t(lang, "kb.hist_trades_active")
                if op_filter == "trades"
                else t(lang, "kb.hist_trades"),
                callback_data="hist_filter_trades",
            ),
        ]
    )
    keyboard.append(
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.hist_deposits_active")
                if op_filter == "deposits"
                else t(lang, "kb.hist_deposits"),
                callback_data="hist_filter_deposits",
            ),
            types.InlineKeyboardButton(
                text=t(lang, "kb.hist_withdrawals_active")
                if op_filter == "withdrawals"
                else t(lang, "kb.hist_withdrawals"),
                callback_data="hist_filter_withdrawals",
            ),
        ]
    )
    actions = []
    if has_trades:
        actions.append(
            types.InlineKeyboardButton(
                text=t(lang, "kb.edit_trade"), callback_data="edit_trade_menu"
            )
        )
    actions.append(
        types.InlineKeyboardButton(
            text=t(lang, "kb.edit_op"), callback_data="edit_op_menu"
        )
    )
    if total:
        actions.append(
            types.InlineKeyboardButton(
                text=t(lang, "kb.del_op"), callback_data="del_op_menu"
            )
        )
    if actions:
        keyboard.append(actions)
    keyboard.append(
        [types.InlineKeyboardButton(text=t(lang, "kb.back_main"), callback_data="main_menu")]
    )
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_del_ops_keyboard(rows, page: int, total: int, per_page: int = 8, lang: str = "ru"):
    keyboard = []
    for op_id, date, op_type, *_ in rows:
        label = f"🗑 {date[8:10]}.{date[5:7]} {op_type_label(lang, op_type)}"
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
                text=t(lang, "kb.back_history"), callback_data="action_history"
            )
        ]
    )
    keyboard.append(
        [types.InlineKeyboardButton(text=t(lang, "kb.back_main"), callback_data="main_menu")]
    )
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_edit_trades_keyboard(rows, page: int, total: int, per_page: int = 8, lang: str = "ru"):
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
                text=t(lang, "kb.back_history"), callback_data="action_history"
            )
        ]
    )
    keyboard.append(
        [types.InlineKeyboardButton(text=t(lang, "kb.back_main"), callback_data="main_menu")]
    )
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_edit_ops_keyboard(rows, page: int, total: int, per_page: int = 8, lang: str = "ru"):
    keyboard = []
    for op_id, date, op_type, amount, _ in rows:
        label = f"✏️ {date[8:10]}.{date[5:7]} {op_type_label(lang, op_type)} ({amount:+.2f})"
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
                text=t(lang, "kb.back_history"), callback_data="action_history"
            )
        ]
    )
    keyboard.append(
        [types.InlineKeyboardButton(text=t(lang, "kb.back_main"), callback_data="main_menu")]
    )
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_edit_op_keyboard(op_id: int, lang: str = "ru"):
    keyboard = [
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.field_date"), callback_data="edit_op_field_date"
            ),
            types.InlineKeyboardButton(
                text=t(lang, "kb.field_amount_short"), callback_data="edit_op_field_amount"
            ),
        ],
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.field_note"), callback_data="edit_op_field_note"
            ),
        ],
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.back_op_list"), callback_data="edit_op_menu"
            ),
        ],
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_edit_trade_keyboard(trade_id: int, lang: str = "ru"):
    keyboard = [
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.field_date"), callback_data="edit_field_date"
            ),
            types.InlineKeyboardButton(text=t(lang, "kb.field_pair"), callback_data="edit_field_pair"),
        ],
        [
            types.InlineKeyboardButton(text=t(lang, "kb.field_lot"), callback_data="edit_field_lot"),
            types.InlineKeyboardButton(text=t(lang, "kb.field_side"), callback_data="edit_field_side"),
        ],
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.field_amount"), callback_data="edit_field_amount"
            ),
            types.InlineKeyboardButton(
                text=t(lang, "kb.field_commission"), callback_data="edit_field_commission"
            ),
        ],
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.field_note"), callback_data="edit_field_note"
            ),
            types.InlineKeyboardButton(text=t(lang, "kb.field_risk"), callback_data="edit_field_risk"),
        ],
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.back_trade_list"), callback_data="edit_trade_menu"
            ),
        ],
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


# --- Счета ---
def get_accounts_keyboard(user_id: int, active_id: int, lang: str = "ru"):
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
                text=t(lang, "kb.acc_create"), callback_data="acc_create"
            )
        ]
    )
    keyboard.append(
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.acc_rename"), callback_data="acc_rename_menu"
            ),
            types.InlineKeyboardButton(
                text=t(lang, "kb.acc_delete"), callback_data="acc_delete_menu"
            ),
        ]
    )
    keyboard.append(
        [types.InlineKeyboardButton(text=t(lang, "kb.back_main"), callback_data="main_menu")]
    )
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_account_select_keyboard(user_id: int, action: str, lang: str = "ru"):
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
                text=t(lang, "kb.back_accounts"), callback_data="action_accounts"
            )
        ]
    )
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


# --- Настройки ---
def get_settings_keyboard(tz_offset: int, daily_report: bool, lang: str = "ru"):
    hours = tz_offset / 60
    tz_label = f"UTC{'+' if hours >= 0 else '-'}{abs(hours):g}"
    report_label = (
        t(lang, "kb.report_enabled") if daily_report else t(lang, "kb.report_disabled")
    )
    keyboard = [
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.tz", tz=tz_label), callback_data="action_tz"
            )
        ],
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.daily_report", report=report_label),
                callback_data="action_toggle_report",
            )
        ],
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.change_currency"), callback_data="action_change_currency"
            )
        ],
        [
            types.InlineKeyboardButton(
                text=t(lang, "settings.language", language=lang_name(lang)),
                callback_data="action_lang",
            )
        ],
    ]
    keyboard.append(
        [types.InlineKeyboardButton(text=t(lang, "kb.back_main"), callback_data="main_menu")]
    )
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_language_keyboard(lang: str = "ru", hide_back: bool = False):
    """Клавиатура выбора языка.

    hide_back=True используется на первом входе (шлюз выбора языка):
    кнопка «Назад в настройки» скрыта, чтобы новый пользователь
    не мог выйти из выбора языка до его завершения.
    """
    keyboard = [
        [
            types.InlineKeyboardButton(text=t(lang, "kb.lang_ru"), callback_data="lang_ru"),
            types.InlineKeyboardButton(text=t(lang, "kb.lang_en"), callback_data="lang_en"),
        ],
    ]
    if not hide_back:
        keyboard.append(
            [
                types.InlineKeyboardButton(
                    text=t(lang, "kb.back_settings"), callback_data="back_settings"
                ),
            ]
        )
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


# --- Прочее ---
def get_currency_keyboard(lang: str = "ru"):
    keyboard = [
        [
            types.InlineKeyboardButton(text=t(lang, "kb.curr_usd"), callback_data="curr_USD"),
            types.InlineKeyboardButton(text=t(lang, "kb.curr_eur"), callback_data="curr_EUR"),
        ],
        [types.InlineKeyboardButton(text=t(lang, "kb.curr_usdt"), callback_data="curr_USDT")],
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_pairs_keyboard(
    account_id: int, prefix: str = "sel_pair", back_to: str | None = None, lang: str = "ru"
):
    pairs = get_user_pairs(account_id)
    keyboard = []
    for p in pairs:
        keyboard.append(
            [types.InlineKeyboardButton(text=f"🔹 {p}", callback_data=f"{prefix}_{p}")]
        )
    keyboard.append(
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.other_pair"), callback_data=f"{prefix}_custom"
            )
        ]
    )
    row = []
    if back_to:
        row.append(_back_button(back_to, lang))
    row.append(types.InlineKeyboardButton(text=t(lang, "kb.menu"), callback_data="main_menu"))
    keyboard.append(row)
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_side_keyboard(prefix: str = "side", back_to: str | None = None, lang: str = "ru"):
    keyboard = [
        [
            types.InlineKeyboardButton(text=t(lang, "kb.side_buy"), callback_data=f"{prefix}_buy"),
            types.InlineKeyboardButton(text=t(lang, "kb.side_sell"), callback_data=f"{prefix}_sell"),
        ],
    ]
    row = []
    if back_to:
        row.append(_back_button(back_to, lang))
    row.append(types.InlineKeyboardButton(text=t(lang, "kb.menu"), callback_data="main_menu"))
    keyboard.append(row)
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_date_keyboard(prefix: str = "opdate", back_to: str | None = None, lang: str = "ru"):
    keyboard = [
        [
            types.InlineKeyboardButton(text=t(lang, "kb.today_btn"), callback_data=f"{prefix}_today"),
            types.InlineKeyboardButton(text=t(lang, "kb.yesterday"), callback_data=f"{prefix}_yesterday"),
        ],
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.custom_date"), callback_data=f"{prefix}_custom"
            )
        ],
    ]
    row = []
    if back_to:
        row.append(_back_button(back_to, lang))
    row.append(types.InlineKeyboardButton(text=t(lang, "kb.menu"), callback_data="main_menu"))
    keyboard.append(row)
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_stats_keyboard(account_id: int, lang: str = "ru"):
    pairs = get_user_pairs(account_id)
    keyboard = [
        [
            types.InlineKeyboardButton(text=t(lang, "kb.stats_day"), callback_data="stats_day"),
            types.InlineKeyboardButton(text=t(lang, "kb.stats_week"), callback_data="stats_week"),
        ],
        [
            types.InlineKeyboardButton(text=t(lang, "kb.stats_month"), callback_data="stats_month"),
            types.InlineKeyboardButton(text=t(lang, "kb.stats_all"), callback_data="stats_all"),
        ],
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.stats_custom"), callback_data="stats_custom"
            )
        ],
    ]
    if pairs:
        pair_buttons = [
            types.InlineKeyboardButton(
                text=t(lang, "kb.stats_pair", pair=p), callback_data=f"stats_pair_{p}"
            )
            for p in pairs
        ]
        keyboard.append(pair_buttons)
    keyboard.append(
        [types.InlineKeyboardButton(text=t(lang, "kb.stats_by_pair"), callback_data="stats_pairs")]
    )
    keyboard.append(
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.back_analytics"), callback_data="action_analytics"
            )
        ]
    )
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_chart_keyboard(lang: str = "ru"):
    keyboard = [
        [
            types.InlineKeyboardButton(text=t(lang, "kb.chart_all"), callback_data="chart_all"),
            types.InlineKeyboardButton(text=t(lang, "kb.chart_month"), callback_data="chart_month"),
            types.InlineKeyboardButton(text=t(lang, "kb.chart_week"), callback_data="chart_week"),
        ],
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.back_analytics"), callback_data="action_analytics"
            ),
        ],
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_excel_keyboard(lang: str = "ru"):
    keyboard = [
        [
            types.InlineKeyboardButton(text=t(lang, "kb.chart_all"), callback_data="excel_all"),
            types.InlineKeyboardButton(text=t(lang, "kb.today_btn"), callback_data="excel_today"),
        ],
        [
            types.InlineKeyboardButton(text=t(lang, "kb.chart_week"), callback_data="excel_week"),
            types.InlineKeyboardButton(text=t(lang, "kb.chart_month"), callback_data="excel_month"),
        ],
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.excel_custom"), callback_data="excel_custom"
            ),
        ],
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.back_analytics"), callback_data="action_analytics"
            ),
        ],
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_report_keyboard(lang: str = "ru"):
    keyboard = [
        [
            types.InlineKeyboardButton(text=t(lang, "kb.report_again"), callback_data="report_again"),
            types.InlineKeyboardButton(text=t(lang, "kb.menu"), callback_data="main_menu"),
        ]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_back_keyboard(lang: str = "ru"):
    keyboard = [
        [types.InlineKeyboardButton(text=t(lang, "kb.cancel_menu"), callback_data="main_menu")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)
