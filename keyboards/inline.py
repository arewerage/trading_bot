from aiogram import types

from config import ADMIN_ID
from database import get_user_pairs


# --- Клавиатуры ---
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
            types.InlineKeyboardButton(
                text="📊 Статистика", callback_data="action_stats"
            ),
            types.InlineKeyboardButton(
                text="📁 Скачать Excel", callback_data="action_excel"
            ),
        ],
    ]

    # Кнопка бэкапа отображается ТОЛЬКО для администратора
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


def get_history_keyboard(has_trades: bool):
    keyboard = []
    if has_trades:
        keyboard.append(
            [
                types.InlineKeyboardButton(
                    text="🗑 Удалить последнюю сделку",
                    callback_data="action_delete_last",
                )
            ]
        )
    keyboard.append(
        [types.InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")]
    )
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_currency_keyboard():
    keyboard = [
        [
            types.InlineKeyboardButton(text="💵 USD ($)", callback_data="curr_USD"),
            types.InlineKeyboardButton(text="💶 EUR (€)", callback_data="curr_EUR"),
        ],
        [types.InlineKeyboardButton(text="🪙 USDT", callback_data="curr_USDT")],
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_pairs_keyboard(user_id):
    pairs = get_user_pairs(user_id)
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


def get_stats_keyboard(user_id):
    pairs = get_user_pairs(user_id)
    keyboard = [
        [
            types.InlineKeyboardButton(text="📅 За день", callback_data="stats_day"),
            types.InlineKeyboardButton(text="📆 За неделю", callback_data="stats_week"),
        ],
        [
            types.InlineKeyboardButton(text="🗓 За месяц", callback_data="stats_month"),
            types.InlineKeyboardButton(
                text="⏱ Произвольный период", callback_data="stats_custom"
            ),
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
