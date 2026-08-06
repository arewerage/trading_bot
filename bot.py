import asyncio
import io
import logging
from datetime import datetime, timedelta
import pandas as pd

import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile
from openpyxl.styles import PatternFill
from openpyxl.utils import get_column_letter

from database import (
    init_db, set_user_deposit, get_user_deposit,
    log_balance_operation, add_trade_operation,
    get_user_operations, get_user_pairs, reset_user_data,
    SQLiteFSMStorage
)

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")

if not API_TOKEN:
    raise ValueError("Не найден API_TOKEN в переменных окружения или файле .env!")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
storage = SQLiteFSMStorage()
dp = Dispatcher(storage=storage)

# Состояния FSM
class DepositState(StatesGroup):
    waiting_for_deposit = State()
    waiting_for_top_up = State()
    waiting_for_withdraw = State()

class TradeState(StatesGroup):
    waiting_for_pair = State()
    waiting_for_lot = State()
    waiting_for_result = State()
    waiting_for_profit = State()

class StatsState(StatesGroup):
    waiting_for_custom_period = State()

# --- Клавиатуры ---
def get_main_keyboard():
    keyboard = [
        [types.InlineKeyboardButton(text="➕ Добавить сделку", callback_data="action_add_trade")],
        [types.InlineKeyboardButton(text="🟢 Пополнить депозит", callback_data="action_top_up")],
        [types.InlineKeyboardButton(text="🔴 Вывести с депозита", callback_data="action_withdraw")],
        [types.InlineKeyboardButton(text="📊 Статистика", callback_data="action_stats")],
        [types.InlineKeyboardButton(text="📁 Скачать Excel", callback_data="action_excel")],
        [types.InlineKeyboardButton(text="🔄 Сброс данных", callback_data="action_reset")]
    ]
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

    if deposit <= 0:
        text = "🤖 **Торговый бот-статистики**\n\nДобро пожаловать! Введите сумму вашего **стартового депозита** цифрами (например, `1000`):"
        await update_interface(state, message, text, parse_mode="Markdown")
        await state.set_state(DepositState.waiting_for_deposit)
    else:
        text = f"🤖 **Главное меню**\n\nТекущий депозит: **{deposit:.2f} USD**\nВыберите действие:"
        await update_interface(state, message, text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "main_menu")
async def process_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    deposit = get_user_deposit(user_id)

    if deposit <= 0:
        text = "🤖 **Торговый бот-статистики**\n\nВведите сумму вашего **стартового депозита** цифрами (например, `1000`):"
        await update_interface(state, callback, text, parse_mode="Markdown")
        await state.set_state(DepositState.waiting_for_deposit)
    else:
        text = f"🤖 **Главное меню**\n\nТекущий депозит: **{deposit:.2f} USD**\nВыберите действие:"
        await update_interface(state, callback, text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

# --- Депозит и сделки ---
@dp.message(DepositState.waiting_for_deposit)
async def process_deposit(message: types.Message, state: FSMContext):
    try:
        deposit = float(message.text.replace(",", "."))
        if deposit <= 0:
            await update_interface(state, message, "⚠️ Депозит должен быть больше нуля:", parse_mode="Markdown")
            return
        set_user_deposit(message.from_user.id, deposit, op_type="Старт", amount=deposit)
        await update_interface(state, message, f"✅ Стартовый депозит установлен: **{deposit:.2f} USD**", reply_markup=get_main_keyboard(), parse_mode="Markdown")
        await state.clear()
    except ValueError:
        await update_interface(state, message, "⚠️ Введите корректное число для депозита.", parse_mode="Markdown")

@dp.callback_query(F.data == "action_top_up")
async def callback_top_up(callback: types.CallbackQuery, state: FSMContext):
    await update_interface(state, callback, "🟢 **Пополнение**\n\nВведите сумму (например, `500`):", reply_markup=get_back_keyboard(), parse_mode="Markdown")
    await state.set_state(DepositState.waiting_for_top_up)

@dp.message(DepositState.waiting_for_top_up)
async def process_top_up(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount <= 0:
            await update_interface(state, message, "⚠️ Сумма должна быть больше нуля.", reply_markup=get_back_keyboard(), parse_mode="Markdown")
            return
        user_id = message.from_user.id
        new_deposit = get_user_deposit(user_id) + amount
        log_balance_operation(user_id, "Пополнение", amount, new_deposit)
        await update_interface(state, message, f"✅ Пополнено на **+{amount:.2f} USD**\n💰 Баланс: **{new_deposit:.2f} USD**", reply_markup=get_main_keyboard(), parse_mode="Markdown")
        await state.clear()
    except ValueError:
        await update_interface(state, message, "⚠️ Введите числовое значение.", reply_markup=get_back_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "action_withdraw")
async def callback_withdraw(callback: types.CallbackQuery, state: FSMContext):
    deposit = get_user_deposit(callback.from_user.id)
    await update_interface(state, callback, f"🔴 **Вывод средств**\n\nБаланс: **{deposit:.2f} USD**\nВведите сумму:", reply_markup=get_back_keyboard(), parse_mode="Markdown")
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
        if amount > current_deposit:
            await update_interface(state, message, f"⚠️ Нельзя вывести больше баланса! Доступно: **{current_deposit:.2f} USD**", reply_markup=get_back_keyboard(), parse_mode="Markdown")
            return
        new_deposit = current_deposit - amount
        log_balance_operation(user_id, "Вывод", -amount, new_deposit)
        await update_interface(state, message, f"✅ Выведено: **-{amount:.2f} USD**\n💰 Баланс: **{new_deposit:.2f} USD**", reply_markup=get_main_keyboard(), parse_mode="Markdown")
        await state.clear()
    except ValueError:
        await update_interface(state, message, "⚠️ Введите числовое значение.", reply_markup=get_back_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "action_reset")
async def callback_reset_confirm(callback: types.CallbackQuery, state: FSMContext):
    keyboard = [[types.InlineKeyboardButton(text="⚠️ Да, удалить всё", callback_data="reset_yes")], [types.InlineKeyboardButton(text="◀️ Отмена", callback_data="main_menu")]]
    await update_interface(state, callback, "🚨 **Внимание!** Вся история будет удалена. Продолжить?", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")

@dp.callback_query(F.data == "reset_yes")
async def callback_reset_execute(callback: types.CallbackQuery, state: FSMContext):
    reset_user_data(callback.from_user.id)
    await update_interface(state, callback, "🔄 Данные сброшены.\n\nВведите новый **стартовый депозит**:", parse_mode="Markdown")
    await state.set_state(DepositState.waiting_for_deposit)

@dp.callback_query(F.data == "action_add_trade")
async def callback_add_trade(callback: types.CallbackQuery, state: FSMContext):
    if get_user_deposit(callback.from_user.id) <= 0:
        await callback.answer("Сначала установите стартовый депозит!", show_alert=True)
        return
    await update_interface(state, callback, "Введите торговую пару текстом (например, `XAUUSD`):", reply_markup=get_back_keyboard(), parse_mode="Markdown")
    await state.set_state(TradeState.waiting_for_pair)

@dp.message(TradeState.waiting_for_pair)
async def process_pair_text(message: types.Message, state: FSMContext):
    pair = message.text.strip().upper()
    if not pair:
        await update_interface(state, message, "⚠️ Пара не может быть пустой:", reply_markup=get_back_keyboard(), parse_mode="Markdown")
        return
    await state.update_data(pair=pair)
    await update_interface(state, message, f"Пара: `{pair}`\n\nВведите объем лота (например, `0.1`):", reply_markup=get_back_keyboard(), parse_mode="Markdown")
    await state.set_state(TradeState.waiting_for_lot)

@dp.message(TradeState.waiting_for_lot)
async def process_lot(message: types.Message, state: FSMContext):
    try:
        lot = float(message.text.replace(",", "."))
        await state.update_data(lot=lot)
        keyboard = [[types.InlineKeyboardButton(text="✅ Плюс", callback_data="result_win"), types.InlineKeyboardButton(text="❌ Минус", callback_data="result_loss")], [types.InlineKeyboardButton(text="◀️ Отмена", callback_data="main_menu")]]
        await update_interface(state, message, "Выберите исход сделки:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
        await state.set_state(TradeState.waiting_for_result)
    except ValueError:
        await update_interface(state, message, "⚠️ Введите корректный лот:", reply_markup=get_back_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("result_"))
async def process_result_callback(callback: types.CallbackQuery, state: FSMContext):
    result = "Win" if callback.data == "result_win" else "Loss"
    await state.update_data(result=result)
    await update_interface(state, callback, f"Исход: `{'Плюс' if result == 'Win' else 'Минус'}`\n\nВведите сумму профита/убытка в USD (`50` или `-20`):", reply_markup=get_back_keyboard(), parse_mode="Markdown")
    await state.set_state(TradeState.waiting_for_profit)

@dp.message(TradeState.waiting_for_profit)
async def process_profit(message: types.Message, state: FSMContext):
    try:
        profit_loss = float(message.text.replace(",", "."))
        data = await state.get_data()
        user_id = message.from_user.id
        new_deposit = get_user_deposit(user_id) + profit_loss
        add_trade_operation(user_id, data["pair"], data["lot"], data["result"], profit_loss, new_deposit)
        text = f"✅ **Сделка сохранена!**\n🔹 Пара: `{data['pair']}`\n🔹 Профит: `{profit_loss:+.2f} USD`\n💰 Баланс: `{new_deposit:.2f} USD`"
        await update_interface(state, message, text, reply_markup=get_main_keyboard(), parse_mode="Markdown")
        await state.clear()
    except ValueError:
        await update_interface(state, message, "⚠️ Введите числовое значение профита:", reply_markup=get_back_keyboard(), parse_mode="Markdown")

# --- Статистика и Метрики ---
@dp.callback_query(F.data == "action_stats")
async def callback_stats_menu(callback: types.CallbackQuery, state: FSMContext):
    await update_interface(state, callback, "📊 **Меню статистики**\n\nВыберите период или пару:", reply_markup=get_stats_keyboard(callback.from_user.id), parse_mode="Markdown")

def calculate_advanced_stats(operations, filter_func):
    filtered = [r for r in operations if r[1] == "Сделка" and filter_func(r)]
    if not filtered:
        return None
    total = len(filtered)
    wins = sum(1 for r in filtered if r[4] == "Win")
    losses = sum(1 for r in filtered if r[4] == "Loss")
    winrate = (wins / total) * 100 if total > 0 else 0
    total_pl = sum(r[5] for r in filtered)
    gross_profit = sum(r[5] for r in filtered if r[5] > 0)
    gross_loss = abs(sum(r[5] for r in filtered if r[5] < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
    avg_win = (gross_profit / wins) if wins > 0 else 0.0
    avg_loss = (gross_loss / losses) if losses > 0 else 0.0

    peak, max_dd = -float('inf'), 0.0
    for r in operations:
        bal = r[6]
        if bal > peak: peak = bal
        dd = peak - bal
        if dd > max_dd: max_dd = dd

    return {"total": total, "wins": wins, "losses": losses, "winrate": winrate, "total_pl": total_pl, "profit_factor": profit_factor, "avg_win": avg_win, "avg_loss": avg_loss, "max_dd": max_dd}

@dp.callback_query(F.data.in_({"stats_day", "stats_week", "stats_month"}))
async def callback_stats_period(callback: types.CallbackQuery, state: FSMContext):
    now = datetime.now()
    period_map = {
        "stats_day": ("день", lambda r: datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S").date() == now.date()),
        "stats_week": ("неделю", lambda r: datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S") >= now - timedelta(days=7)),
        "stats_month": ("месяц", lambda r: (dt := datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S")).year == now.year and dt.month == now.month)
    }
    label, f_func = period_map[callback.data]
    stats = calculate_advanced_stats(get_user_operations(callback.from_user.id), f_func)

    if not stats:
        text = f"📊 **Статистика за {label}**\n\nСделок не найдено."
    else:
        text = f"📊 **Статистика за {label}:**\n\n📁 Сделок: `{stats['total']}`\n✅ Плюсов: `{stats['wins']}` | ❌ Минусов: `{stats['losses']}`\n🎯 Винрейт: `{stats['winrate']:.1f}%`\n💰 Итог: `{stats['total_pl']:+.2f} USD`\n📈 Профит-фактор: `{stats['profit_factor']:.2f}`\n🟢 Ср. прибыль: `+{stats['avg_win']:.2f} USD`\n🔴 Ср. убыток: `-{stats['avg_loss']:.2f} USD`\n📉 Макс. просадка: `{stats['max_dd']:.2f} USD`"
    await update_interface(state, callback, text, reply_markup=get_stats_keyboard(callback.from_user.id), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("stats_pair_"))
async def callback_stats_pair(callback: types.CallbackQuery, state: FSMContext):
    pair = callback.data.replace("stats_pair_", "")
    stats = calculate_advanced_stats(get_user_operations(callback.from_user.id), lambda r: r[2] == pair)
    if not stats:
        text = f"📊 **Статистика по паре {pair}**\n\nСделок не найдено."
    else:
        text = f"📊 **Пара `{pair}`:**\n\n📁 Сделок: `{stats['total']}`\n✅ Плюсов: `{stats['wins']}` | ❌ Минусов: `{stats['losses']}`\n🎯 Винрейт: `{stats['winrate']:.1f}%`\n💰 Итог: `{stats['total_pl']:+.2f} USD`\n📈 Профит-фактор: `{stats['profit_factor']:.2f}`"
    await update_interface(state, callback, text, reply_markup=get_stats_keyboard(callback.from_user.id), parse_mode="Markdown")

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
        stats = calculate_advanced_stats(get_user_operations(message.from_user.id), lambda r: start_date <= datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S").date() <= end_date)
        text = f"📊 **Период:**\n\n📁 Сделок: `{stats['total']}`\n💰 Итог: `{stats['total_pl']:+.2f} USD`" if stats else "📊 Сделок не найдено."
        await update_interface(state, message, text, reply_markup=get_main_keyboard(), parse_mode="Markdown")
        await state.clear()
    except Exception:
        await update_interface(state, message, "⚠️ Ошибка формата. Введите в формате `ДД.ММ.ГГГГ - ДД.ММ.ГГГГ`", reply_markup=get_back_keyboard(), parse_mode="Markdown")

# --- Генерация Excel ---
@dp.callback_query(F.data == "action_excel")
async def callback_excel(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    operations = get_user_operations(callback.from_user.id)
    if not operations:
        await update_interface(state, callback, "⚠️ Нет данных для выгрузки в Excel.", reply_markup=get_main_keyboard(), parse_mode="Markdown")
        return

    try:
        from collections import defaultdict
        sheets_data = defaultdict(list)
        months_ru = {1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 5: "Май", 6: "Июнь", 7: "Июль", 8: "Август", 9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"}

        for row in operations:
            dt_obj = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
            sheet_name = f"{months_ru[dt_obj.month]} {dt_obj.year}"
            sheets_data[sheet_name].append({
                "Дата": dt_obj.strftime("%d.%m.%Y"),
                "Время": dt_obj.strftime("%H:%M:%S"),
                "Тип операции": row[1],
                "Торговая пара": row[2] if row[2] != "-" else "",
                "Лот": row[3] if row[3] > 0 else "",
                "Исход": ("Плюс" if row[4] == "Win" else "Минус") if row[1] == "Сделка" else "-",
                "Сумма операции ($)": row[5],
                "Конечный депозит ($)": row[6]
            })

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            green_fill = PatternFill(start_color="D4EDDA", end_color="D4EDDA", fill_type="solid")
            red_fill = PatternFill(start_color="F8D7DA", end_color="F8D7DA", fill_type="solid")

            for sheet_name, rows in sheets_data.items():
                df = pd.DataFrame(rows)
                df.to_excel(writer, index=False, sheet_name=sheet_name)
                worksheet = writer.sheets[sheet_name]
                worksheet.auto_filter.ref = worksheet.dimensions

                for col_idx in range(1, worksheet.max_column + 1):
                    col_name = worksheet.cell(row=1, column=col_idx).value
                    if col_name in ["Сумма операции ($)", "Конечный депозит ($)"]:
                        for r_idx in range(2, worksheet.max_row + 1):
                            worksheet.cell(row=r_idx, column=col_idx).number_format = '"$"#,##0.00'

                for row_idx in range(2, worksheet.max_row + 1):
                    val = worksheet.cell(row=row_idx, column=6).value
                    if val == "Плюс":
                        for c in range(1, worksheet.max_column + 1): worksheet.cell(row=row_idx, column=c).fill = green_fill
                    elif val == "Минус":
                        for c in range(1, worksheet.max_column + 1): worksheet.cell(row=row_idx, column=c).fill = red_fill

                for col in worksheet.columns:
                    max_len = max(len(str(cell.value or '')) for cell in col)
                    worksheet.column_dimensions[get_column_letter(col[0].column)].width = max(max_len + 4, 12)

        output.seek(0)
        document = BufferedInputFile(output.getvalue(), filename="trading_history.xlsx")
        await update_interface(state, callback, "📁 **Excel-файл готов!**", reply_markup=get_main_keyboard(), parse_mode="Markdown", document=document)
    except Exception as e:
        logging.error(f"Excel error: {e}")
        await update_interface(state, callback, "⚠️ Ошибка генерации Excel.", reply_markup=get_main_keyboard(), parse_mode="Markdown")

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
