import asyncio
import io
import logging
import pandas as pd
import os
import openpyxl

from dotenv import load_dotenv
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile
from openpyxl.styles import PatternFill, Font
from openpyxl.utils import get_column_letter

from database import (
    init_db, set_user_deposit_and_currency, get_user_deposit, get_user_currency,
    log_balance_operation, add_trade_operation,
    get_user_operations, get_recent_operations, get_last_trade, delete_trade_by_id,
    get_user_pairs, reset_user_data, SQLiteFSMStorage
)

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

if not API_TOKEN:
    raise ValueError("Не найден API_TOKEN в переменных окружения или файле .env!")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
storage = SQLiteFSMStorage()
dp = Dispatcher(storage=storage)

# Состояния FSM
class DepositState(StatesGroup):
    waiting_for_currency = State()
    waiting_for_deposit = State()
    waiting_for_top_up = State()
    waiting_for_withdraw = State()

class TradeState(StatesGroup):
    waiting_for_pair = State()
    waiting_for_lot = State()
    waiting_for_profit = State()
    waiting_for_risk = State()
    waiting_for_note = State()
    waiting_for_confirmation = State()

class StatsState(StatesGroup):
    waiting_for_custom_period = State()

# --- Клавиатуры ---
def get_main_keyboard(user_id: int):
    keyboard = [
        [types.InlineKeyboardButton(text="➕ Добавить сделку", callback_data="action_add_trade")],
        [types.InlineKeyboardButton(text="📜 История сделок", callback_data="action_history")],
        [types.InlineKeyboardButton(text="🟢 Пополнить депозит", callback_data="action_top_up"),
         types.InlineKeyboardButton(text="🔴 Вывести с депозита", callback_data="action_withdraw")],
        [types.InlineKeyboardButton(text="📊 Статистика", callback_data="action_stats"),
         types.InlineKeyboardButton(text="📁 Скачать Excel", callback_data="action_excel")]
    ]

    # Кнопка бэкапа отображается ТОЛЬКО для администратора
    row_admin = []
    if user_id == ADMIN_ID:
        row_admin.append(types.InlineKeyboardButton(text="💾 Резервная копия БД", callback_data="action_backup"))
    row_admin.append(types.InlineKeyboardButton(text="🔄 Сброс данных", callback_data="action_reset"))

    keyboard.append(row_admin)
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_history_keyboard(has_trades: bool):
    keyboard = []
    if has_trades:
        keyboard.append([types.InlineKeyboardButton(text="🗑 Удалить последнюю сделку", callback_data="action_delete_last")])
    keyboard.append([types.InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")])
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_currency_keyboard():
    keyboard = [
        [types.InlineKeyboardButton(text="💵 USD ($)", callback_data="curr_USD"),
         types.InlineKeyboardButton(text="💶 EUR (€)", callback_data="curr_EUR")],
        [types.InlineKeyboardButton(text="🪙 USDT", callback_data="curr_USDT")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_pairs_keyboard(user_id):
    pairs = get_user_pairs(user_id)
    keyboard = []
    for p in pairs:
        keyboard.append([types.InlineKeyboardButton(text=f"🔹 {p}", callback_data=f"sel_pair_{p}")])
    keyboard.append([types.InlineKeyboardButton(text="✍️ Другая пара (ввести текстом)", callback_data="sel_pair_custom")])
    keyboard.append([types.InlineKeyboardButton(text="◀️ Отмена", callback_data="main_menu")])
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_stats_keyboard(user_id):
    pairs = get_user_pairs(user_id)
    keyboard = [
        [types.InlineKeyboardButton(text="📅 За день", callback_data="stats_day"),
         types.InlineKeyboardButton(text="📆 За неделю", callback_data="stats_week")],
        [types.InlineKeyboardButton(text="🗓 За месяц", callback_data="stats_month"),
         types.InlineKeyboardButton(text="⏱ Произвольный период", callback_data="stats_custom")]
    ]
    if pairs:
        pair_buttons = [types.InlineKeyboardButton(text=f"🔍 Пара: {p}", callback_data=f"stats_pair_{p}") for p in pairs]
        keyboard.append(pair_buttons)

    keyboard.append([types.InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")])
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_back_keyboard():
    keyboard = [
        [types.InlineKeyboardButton(text="◀️ Отмена / Меню", callback_data="main_menu")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)

# --- Универсальное управление интерфейсом (строго 1 активное сообщение) ---
async def update_interface(
    state: FSMContext,
    event: types.Message | types.CallbackQuery,
    text: str,
    reply_markup=None,
    parse_mode="Markdown",
    document=None
):
    if isinstance(event, types.CallbackQuery):
        await event.answer()
        bot_instance = event.bot
        chat_id = event.message.chat.id
    else:
        bot_instance = event.bot
        chat_id = event.chat.id
        try:
            await event.delete()
        except Exception:
            pass

    data = await state.get_data()
    old_msg_id = data.get("bot_msg_id")

    if isinstance(event, types.CallbackQuery) and not document:
        try:
            await event.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            await state.update_data(bot_msg_id=event.message.message_id)
            return
        except Exception:
            pass

    if old_msg_id:
        try:
            await bot_instance.delete_message(chat_id=chat_id, message_id=old_msg_id)
        except Exception:
            pass

    if document:
        msg = await bot_instance.send_document(chat_id=chat_id, document=document, caption=text, reply_markup=reply_markup, parse_mode=parse_mode)
    else:
        msg = await bot_instance.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)

    await state.update_data(bot_msg_id=msg.message_id)

# --- Главное меню ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    deposit = get_user_deposit(user_id)
    curr = get_user_currency(user_id)

    if deposit <= 0:
        text = "🤖 **Бот для торговой статистики**\n\nДобро пожаловать! Сначала выберите **валюту счета**:"
        await update_interface(state, message, text, reply_markup=get_currency_keyboard(), parse_mode="Markdown")
        await state.set_state(DepositState.waiting_for_currency)
    else:
        text = f"🤖 **Главное меню**\n\nТекущий депозит: **{deposit:.2f} {curr}**\nВыберите действие:"
        await update_interface(state, message, text, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

@dp.callback_query(F.data == "main_menu")
async def process_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    deposit = get_user_deposit(user_id)
    curr = get_user_currency(user_id)

    if deposit <= 0:
        text = "🤖 **Бот для торговой статистики**\n\nВыберите **валюту счета**:"
        await update_interface(state, callback, text, reply_markup=get_currency_keyboard(), parse_mode="Markdown")
        await state.set_state(DepositState.waiting_for_currency)
    else:
        text = f"🤖 **Главное меню**\n\nТекущий депозит: **{deposit:.2f} {curr}**\nВыберите действие:"
        await update_interface(state, callback, text, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

# --- Резервная копия базы данных (Только для администратора) ---
@dp.callback_query(F.data == "action_backup")
async def callback_backup(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⚠️ У вас нет доступа к этой функции.", show_alert=True)
        return

    await callback.answer()
    db_path = os.path.join("data", "trading_bot.db")
    if os.path.exists(db_path):
        document = BufferedInputFile.from_file(db_path, filename="trading_bot_backup.db")
        await update_interface(
            state, callback,
            "💾 **Резервная копия базы данных:**\n\nФайл актуальной базы данных успешно выгружен.",
            reply_markup=get_main_keyboard(callback.from_user.id),
            parse_mode="Markdown",
            document=document
        )
    else:
        await callback.answer("⚠️ Файл базы данных не найден!", show_alert=True)

# --- Депозит и валюта ---
@dp.callback_query(F.data.startswith("curr_"), DepositState.waiting_for_currency)
async def process_currency_choice(callback: types.CallbackQuery, state: FSMContext):
    curr = callback.data.replace("curr_", "")
    await state.update_data(currency=curr)
    text = f"Выбрана валюта: **{curr}**\n\nВведите сумму вашего **стартового депозита** цифрами (например, `1000`):"
    await update_interface(state, callback, text, reply_markup=get_back_keyboard(), parse_mode="Markdown")
    await state.set_state(DepositState.waiting_for_deposit)

@dp.message(DepositState.waiting_for_deposit)
async def process_deposit(message: types.Message, state: FSMContext):
    try:
        deposit = float(message.text.replace(",", "."))
        if deposit <= 0:
            await update_interface(state, message, "⚠️ Депозит должен быть больше нуля:", parse_mode="Markdown")
            return
        data = await state.get_data()
        curr = data.get("currency", "USD")
        user_id = message.from_user.id

        set_user_deposit_and_currency(user_id, deposit, curr, op_type="Старт", amount=deposit)
        await update_interface(state, message, f"✅ Стартовый депозит успешно установлен: **{deposit:.2f} {curr}**", reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
        await state.clear()
    except ValueError:
        await update_interface(state, message, "⚠️ Пожалуйста, введите корректное число для депозита.", parse_mode="Markdown")

@dp.callback_query(F.data == "action_top_up")
async def callback_top_up(callback: types.CallbackQuery, state: FSMContext):
    curr = get_user_currency(callback.from_user.id)
    await update_interface(state, callback, f"🟢 **Пополнение депозита**\n\nВведите сумму в {curr} (например, `500`):", reply_markup=get_back_keyboard(), parse_mode="Markdown")
    await state.set_state(DepositState.waiting_for_top_up)

@dp.message(DepositState.waiting_for_top_up)
async def process_top_up(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount <= 0:
            await update_interface(state, message, "⚠️ Сумма должна быть больше нуля.", reply_markup=get_back_keyboard(), parse_mode="Markdown")
            return
        user_id = message.from_user.id
        curr = get_user_currency(user_id)
        new_deposit = get_user_deposit(user_id) + amount
        log_balance_operation(user_id, "Пополнение", amount, new_deposit)
        await update_interface(state, message, f"✅ Баланс успешно пополнен на **+{amount:.2f} {curr}**\n💰 Новый депозит: **{new_deposit:.2f} {curr}**", reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
        await state.clear()
    except ValueError:
        await update_interface(state, message, "⚠️ Введите числовое значение.", reply_markup=get_back_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "action_withdraw")
async def callback_withdraw(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    deposit = get_user_deposit(user_id)
    curr = get_user_currency(user_id)
    await update_interface(state, callback, f"🔴 **Вывод средств**\n\nТекущий баланс: **{deposit:.2f} {curr}**\nВведите сумму:", reply_markup=get_back_keyboard(), parse_mode="Markdown")
    await state.set_state(DepositState.waiting_for_withdraw)

@dp.message(DepositState.waiting_for_withdraw)
async def process_withdraw(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount <= 0:
            await update_interface(state, message, "⚠️ Сумма должна быть больше нуля.", reply_markup=get_back_keyboard(), parse_mode="Markdown")
            return
        user_id = message.from_user.id
        current_deposit = get_user_deposit(user_id)
        curr = get_user_currency(user_id)
        if amount > current_deposit:
            await update_interface(state, message, f"⚠️ Нельзя вывести больше, чем есть на балансе! Доступно: **{current_deposit:.2f} {curr}**", reply_markup=get_back_keyboard(), parse_mode="Markdown")
            return
        new_deposit = current_deposit - amount
        log_balance_operation(user_id, "Вывод", -amount, new_deposit)
        await update_interface(state, message, f"✅ Успешно выведено: **-{amount:.2f} {curr}**\n💰 Новый депозит: **{new_deposit:.2f} {curr}**", reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
        await state.clear()
    except ValueError:
        await update_interface(state, message, "⚠️ Введите числовое значение.", reply_markup=get_back_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "action_reset")
async def callback_reset_confirm(callback: types.CallbackQuery, state: FSMContext):
    keyboard = [[types.InlineKeyboardButton(text="⚠️ Да, удалить всё", callback_data="reset_yes")], [types.InlineKeyboardButton(text="◀️ Отмена", callback_data="main_menu")]]
    await update_interface(state, callback, "🚨 **Внимание!** Вся история операций будет удалена. Продолжить?", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")

@dp.callback_query(F.data == "reset_yes")
async def callback_reset_execute(callback: types.CallbackQuery, state: FSMContext):
    reset_user_data(callback.from_user.id)
    text = "🔄 Данные успешно сброшены.\n\nВыберите **валюту счета**:"
    await update_interface(state, callback, text, reply_markup=get_currency_keyboard(), parse_mode="Markdown")
    await state.set_state(DepositState.waiting_for_currency)

# --- История и удаление сделок ---
@dp.callback_query(F.data == "action_history")
async def callback_history(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    operations = get_recent_operations(user_id, limit=10)
    curr = get_user_currency(user_id)

    if not operations:
        text = "📜 **История сделок**\n\nУ вас пока нет сохраненных операций."
        await update_interface(state, callback, text, reply_markup=get_back_keyboard(), parse_mode="Markdown")
        return

    text = "📜 **Последние операции и сделки:**\n\n"
    for row in operations:
        date, op_type, pair, lot, result, amount, balance_after, note, risk_pct = row
        if op_type == "Сделка":
            res_emoji = "✅" if result == "Win" else "❌"
            note_str = f" | _{note}_" if note else ""
            risk_str = f" [🛡 {risk_pct}%]" if risk_pct > 0 else ""
            text += f"`{date}` | 🔹 **{pair}** ({lot} лот) {res_emoji} `{amount:+.2f} {curr}`{risk_str}{note_str}\n"
        else:
            text += f"`{date}` | 🔹 *{op_type}*: `{amount:+.2f} {curr}`\n"

    last_trade = get_last_trade(user_id)
    has_trades = last_trade is not None
    await update_interface(state, callback, text, reply_markup=get_history_keyboard(has_trades), parse_mode="Markdown")

@dp.callback_query(F.data == "action_delete_last")
async def callback_delete_last(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    last_trade = get_last_trade(user_id)
    curr = get_user_currency(user_id)

    if not last_trade:
        await callback.answer("⚠️ Нет совершенных сделок для удаления!", show_alert=True)
        return

    trade_id, date, pair, lot, result, amount, balance_after, note, risk_pct = last_trade
    await state.update_data(delete_trade_id=trade_id)

    note_str = f"🔹 Заметка: _{note}_\n" if note else ""
    risk_str = f"🔹 Риск: `{risk_pct}%`\n" if risk_pct > 0 else ""
    keyboard = [
        [types.InlineKeyboardButton(text="🗑 Да, удалить эту сделку", callback_data="confirm_delete_trade")],
        [types.InlineKeyboardButton(text="◀️ Назад к истории", callback_data="action_history")]
    ]
    text = (
        "⚠️ **Подтвердите удаление последней сделки:**\n\n"
        f"📅 Дата: `{date}`\n"
        f"🔹 Пара: `{pair}`\n"
        f"🔹 Лот: `{lot}`\n"
        f"🔹 Исход: `{'Плюс' if result == 'Win' else 'Минус'}`\n"
        f"🔹 Профит / Убыток: `{amount:+.2f} {curr}`\n"
        f"{risk_str}"
        f"{note_str}\n"
        "*Баланс депозита будет пересчитан автоматически.*"
    )
    await update_interface(state, callback, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")

@dp.callback_query(F.data == "confirm_delete_trade")
async def callback_confirm_delete(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    trade_id = data.get("delete_trade_id")

    if not trade_id:
        await callback.answer("⚠️ Сделка уже удалена или истек срок.", show_alert=True)
        return

    user_id = callback.from_user.id
    success = delete_trade_by_id(user_id, trade_id)
    curr = get_user_currency(user_id)
    new_deposit = get_user_deposit(user_id)

    await state.clear()

    if success:
        text = f"🗑 **Сделка успешно удалена!**\n\n💰 Пересчитанный баланс депозита: **{new_deposit:.2f} {curr}**"
    else:
        text = "⚠️ Не удалось найти или удалить указанную сделку."

    await update_interface(state, callback, text, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

# --- Добавление сделки ---
@dp.callback_query(F.data == "action_add_trade")
async def callback_add_trade(callback: types.CallbackQuery, state: FSMContext):
    if get_user_deposit(callback.from_user.id) <= 0:
        await callback.answer("Сначала установите стартовый депозит!", show_alert=True)
        return
    text = "Выберите торговую пару из списка или введите новую:"
    await update_interface(state, callback, text, reply_markup=get_pairs_keyboard(callback.from_user.id), parse_mode="Markdown")
    await state.set_state(TradeState.waiting_for_pair)

@dp.callback_query(F.data.startswith("sel_pair_"), TradeState.waiting_for_pair)
async def process_pair_callback(callback: types.CallbackQuery, state: FSMContext):
    val = callback.data.replace("sel_pair_", "")
    if val == "custom":
        text = "Введите название новой торговой пары текстом (например, `EURUSD`):"
        await update_interface(state, callback, text, reply_markup=get_back_keyboard(), parse_mode="Markdown")
    else:
        await state.update_data(pair=val)
        text = f"Выбрана пара: `{val}`\n\nВведите объем лота (например, `0.1`):"
        await update_interface(state, callback, text, reply_markup=get_back_keyboard(), parse_mode="Markdown")
        await state.set_state(TradeState.waiting_for_lot)

@dp.message(TradeState.waiting_for_pair)
async def process_pair_text(message: types.Message, state: FSMContext):
    pair = message.text.strip().upper().replace("/", "").replace("-", "").replace(" ", "")
    if not pair:
        text = "⚠️ Пара не может быть пустой. Введите название пары (например, `XAUUSD`):"
        await update_interface(state, message, text, reply_markup=get_back_keyboard(), parse_mode="Markdown")
        return
    await state.update_data(pair=pair)
    text = f"Выбрана пара: `{pair}`\n\nВведите объем лота (например, `0.1`):"
    await update_interface(state, message, text, reply_markup=get_back_keyboard(), parse_mode="Markdown")
    await state.set_state(TradeState.waiting_for_lot)

@dp.message(TradeState.waiting_for_lot)
async def process_lot(message: types.Message, state: FSMContext):
    try:
        lot = float(message.text.replace(",", "."))
        if lot <= 0:
            raise ValueError()
        await state.update_data(lot=lot)
        curr = get_user_currency(message.from_user.id)
        text = f"Введите сумму профита или убытка в {curr}\n*(для прибыли укажите число без знака или с плюсом, для убытка — со знаком минус, например: `50` или `-20`)*:"
        await update_interface(state, message, text, reply_markup=get_back_keyboard(), parse_mode="Markdown")
        await state.set_state(TradeState.waiting_for_profit)
    except ValueError:
        await update_interface(state, message, "⚠️ Введите корректный объем лота (> 0):", reply_markup=get_back_keyboard(), parse_mode="Markdown")

@dp.message(TradeState.waiting_for_profit)
async def process_profit(message: types.Message, state: FSMContext):
    try:
        profit_loss = float(message.text.replace(",", "."))
        await state.update_data(profit_loss=profit_loss)
        keyboard = [
            [types.InlineKeyboardButton(text="⏩ Пропустить риск", callback_data="skip_risk")],
            [types.InlineKeyboardButton(text="◀️ Отмена", callback_data="main_menu")]
        ]
        text = "🛡️ Введите **планируемый риск на сделку в % от депозита** (опционально, например `1` или `1.5`):"
        await update_interface(state, message, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
        await state.set_state(TradeState.waiting_for_risk)
    except ValueError:
        curr = get_user_currency(message.from_user.id)
        await update_interface(state, message, f"⚠️ Введите числовое значение суммы в {curr}:", reply_markup=get_back_keyboard(), parse_mode="Markdown")

@dp.message(TradeState.waiting_for_risk)
async def process_risk_text(message: types.Message, state: FSMContext):
    try:
        risk_pct = float(message.text.replace(",", "."))
        if risk_pct < 0 or risk_pct > 100: raise ValueError()
        await state.update_data(risk_pct=risk_pct)
        await prompt_for_note(message, state)
    except ValueError:
        await update_interface(state, message, "⚠️ Введите корректный процент риска (от 0 до 100):", reply_markup=get_back_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "skip_risk", TradeState.waiting_for_risk)
async def process_risk_skip(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(risk_pct=0.0)
    await prompt_for_note(callback, state)

async def prompt_for_note(event, state: FSMContext):
    keyboard = [
        [types.InlineKeyboardButton(text="⏩ Пропустить заметку", callback_data="skip_note")],
        [types.InlineKeyboardButton(text="◀️ Отмена", callback_data="main_menu")]
    ]
    text = "✍️ Введите **заметку к сделке** (опционально):\n\nИли нажмите кнопку пропустить:"
    await update_interface(state, event, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    await state.set_state(TradeState.waiting_for_note)

@dp.message(TradeState.waiting_for_note)
async def process_note_text(message: types.Message, state: FSMContext):
    await state.update_data(note=message.text.strip())
    await show_trade_confirmation(message, state)

@dp.callback_query(F.data == "skip_note", TradeState.waiting_for_note)
async def process_note_skip(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(note="")
    await show_trade_confirmation(callback, state)

async def show_trade_confirmation(event, state: FSMContext):
    data = await state.get_data()
    pair, lot, profit_loss = data["pair"], data["lot"], data["profit_loss"]
    risk_pct, note = data.get("risk_pct", 0.0), data.get("note", "")
    result = "Win" if profit_loss >= 0 else "Loss"

    curr = get_user_currency(event.from_user.id)
    await state.update_data(result=result)

    keyboard = [
        [types.InlineKeyboardButton(text="✅ Подтвердить и сохранить", callback_data="trade_confirm")],
        [types.InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")]
    ]
    risk_str = f"🔹 Риск: `{risk_pct}%`\n" if risk_pct > 0 else ""
    note_str = f"🔹 Заметка: `{note}`\n" if note else ""
    text = (
        f"📋 **Проверьте данные сделки:**\n\n"
        f"🔹 Пара: `{pair}`\n🔹 Лот: `{lot}`\n"
        f"🔹 Исход: `{'Плюс' if result == 'Win' else 'Минус'}`\n"
        f"🔹 Профит / Убыток: `{profit_loss:+.2f} {curr}`\n"
        f"{risk_str}{note_str}"
    )
    await update_interface(state, event, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    await state.set_state(TradeState.waiting_for_confirmation)

@dp.callback_query(F.data == "trade_confirm", TradeState.waiting_for_confirmation)
async def process_trade_confirm(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if "pair" not in data or "profit_loss" not in data:
        await callback.answer("⚠️ Сделка уже сохранена.", show_alert=True)
        return

    user_id = callback.from_user.id
    pair, lot, result, profit_loss = data["pair"], data["lot"], data["result"], data["profit_loss"]
    note, risk_pct = data.get("note", ""), data.get("risk_pct", 0.0)

    await state.clear()
    current_deposit = get_user_deposit(user_id)
    curr = get_user_currency(user_id)
    new_deposit = max(0.0, current_deposit + profit_loss)

    add_trade_operation(user_id, pair, lot, result, profit_loss, new_deposit, note, risk_pct)

    text = f"✅ **Сделка сохранена!**\n🔹 Пара: `{pair}`\n💰 Баланс: `{new_deposit:.2f} {curr}`"
    await update_interface(state, callback, text, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

# --- Статистика ---
@dp.callback_query(F.data == "action_stats")
async def callback_stats_menu(callback: types.CallbackQuery, state: FSMContext):
    await update_interface(state, callback, "📊 **Меню статистики**\n\nВыберите период или пару:", reply_markup=get_stats_keyboard(callback.from_user.id), parse_mode="Markdown")

@dp.callback_query(F.data.in_({"stats_day", "stats_week", "stats_month"}))
async def callback_stats_period(callback: types.CallbackQuery, state: FSMContext):
    now = datetime.now()
    user_id = callback.from_user.id
    curr = get_user_currency(user_id)

    if callback.data == "stats_day":
        label, start_date, end_date = "день", now.date(), now.date()
        f_func = lambda r: datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S").date() == now.date()
    elif callback.data == "stats_week":
        label, end_date = "неделю", now.date()
        start_date = (now - timedelta(days=7)).date()
        f_func = lambda r: datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S") >= now - timedelta(days=7)
    else:
        label, start_date = "месяц", now.replace(day=1).date()
        next_m = now.replace(year=now.year + 1, month=1, day=1) if now.month == 12 else now.replace(month=now.month + 1, day=1)
        end_date = (next_m - timedelta(days=1)).date()
        f_func = lambda r: (dt := datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S")).year == now.year and dt.month == now.month

    date_str = f"{start_date.strftime('%d.%m.%Y')}" if label == "день" else f"{start_date.strftime('%d.%m.%Y')} — {end_date.strftime('%d.%m.%Y')}"
    stats = calculate_advanced_stats(get_user_operations(user_id), f_func)

    text = f"📊 **Статистика за {label} ({date_str}):**\n\nСделок не найдено." if not stats else f"📊 **Статистика за {label} ({date_str}):**\n\n📁 Сделок: `{stats['total']}`\n✅ Плюсов: `{stats['wins']}` | ❌ Минусов: `{stats['losses']}`\n🎯 Винрейт: `{stats['winrate']:.1f}%`\n💰 Итог: `{stats['total_pl']:+.2f} {curr}`\n📈 Профит-фактор: `{stats['profit_factor']:.2f}`"
    await update_interface(state, callback, text, reply_markup=get_stats_keyboard(user_id), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("stats_pair_"))
async def callback_stats_pair(callback: types.CallbackQuery, state: FSMContext):
    pair = callback.data.replace("stats_pair_", "")
    user_id = callback.from_user.id
    curr = get_user_currency(user_id)
    stats = calculate_advanced_stats(get_user_operations(user_id), lambda r: r[2] == pair)
    text = f"📊 **Пара `{pair}`:**\n\nСделок не найдено." if not stats else f"📊 **Пара `{pair}`:**\n\n📁 Сделок: `{stats['total']}`\n💰 Итог: `{stats['total_pl']:+.2f} {curr}`\n📈 Профит-фактор: `{stats['profit_factor']:.2f}`"
    await update_interface(state, callback, text, reply_markup=get_stats_keyboard(user_id), parse_mode="Markdown")

@dp.callback_query(F.data == "stats_custom")
async def callback_stats_custom(callback: types.CallbackQuery, state: FSMContext):
    await update_interface(state, callback, "⏱ **Произвольный период**\n\nВведите диапазон дат в формате `ДД.ММ.ГГГГ - ДД.ММ.ГГГГ`", reply_markup=get_back_keyboard(), parse_mode="Markdown")
    await state.set_state(StatsState.waiting_for_custom_period)

@dp.message(StatsState.waiting_for_custom_period)
async def process_custom_period(message: types.Message, state: FSMContext):
    try:
        parts = message.text.strip().split("-")
        start_date = datetime.strptime(parts[0].strip(), "%d.%m.%Y").date()
        end_date = datetime.strptime(parts[1].strip(), "%d.%m.%Y").date()
        user_id = message.from_user.id
        curr = get_user_currency(user_id)
        stats = calculate_advanced_stats(get_user_operations(user_id), lambda r: start_date <= datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S").date() <= end_date)
        text = f"📊 **Период:**\n\n📁 Сделок: `{stats['total']}`\n💰 Итог: `{stats['total_pl']:+.2f} {curr}`" if stats else "📊 Сделок не найдено."
        await update_interface(state, message, text, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
        await state.clear()
    except Exception:
        await update_interface(state, message, "⚠️ Ошибка формата. Введите в формате `ДД.ММ.ГГГГ - ДД.ММ.ГГГГ`", reply_markup=get_back_keyboard(), parse_mode="Markdown")

# --- Генерация Excel ---
@dp.callback_query(F.data == "action_excel")
async def callback_excel(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    operations = get_user_operations(user_id)
    if not operations:
        await update_interface(state, callback, "⚠️ Нет данных для выгрузки.", reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
        return
    excel_bytes = generate_excel_bytes(operations, user_id)
    document = BufferedInputFile(excel_bytes, filename="trading_history.xlsx")
    await update_interface(state, callback, "📁 **Ваш Excel-файл готов!**", reply_markup=get_main_keyboard(user_id), parse_mode="Markdown", document=document)

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
