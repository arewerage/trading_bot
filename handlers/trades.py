from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from database import add_trade_operation, get_user_currency, get_user_deposit
from handlers.common import update_interface
from keyboards.inline import get_back_keyboard, get_main_keyboard, get_pairs_keyboard
from states.fsm import TradeState
from utils.validators import (
    validate_amount,
    validate_lot,
    validate_note,
    validate_risk_percent,
    validate_trade_confirmation,
    validate_trading_pair,
)

router = Router()


# --- Добавление сделки ---
@router.callback_query(F.data == "action_add_trade")
async def callback_add_trade(callback: types.CallbackQuery, state: FSMContext):
    if get_user_deposit(callback.from_user.id) <= 0:
        await callback.answer("Сначала установите стартовый депозит!", show_alert=True)
        return
    text = "Выберите торговую пару из списка или введите новую:"
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_pairs_keyboard(callback.from_user.id),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.waiting_for_pair)


@router.callback_query(F.data.startswith("sel_pair_"), TradeState.waiting_for_pair)
async def process_pair_callback(callback: types.CallbackQuery, state: FSMContext):
    val = callback.data.replace("sel_pair_", "")
    if val == "custom":
        text = "Введите название новой торговой пары текстом (например, `EURUSD`):"
        await update_interface(
            state,
            callback,
            text,
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )
    else:
        await state.update_data(pair=val)
        text = f"Выбрана пара: `{val}`\n\nВведите объем лота (например, `0.1`):"
        await update_interface(
            state,
            callback,
            text,
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )
        await state.set_state(TradeState.waiting_for_lot)


@router.message(TradeState.waiting_for_pair)
async def process_pair_text(message: types.Message, state: FSMContext):
    pair, error = validate_trading_pair(message.text)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )
        return
    await state.update_data(pair=pair)
    text = f"Выбрана пара: `{pair}`\n\nВведите объем лота (например, `0.1`):"
    await update_interface(
        state, message, text, reply_markup=get_back_keyboard(), parse_mode="Markdown"
    )
    await state.set_state(TradeState.waiting_for_lot)


@router.message(TradeState.waiting_for_lot)
async def process_lot(message: types.Message, state: FSMContext):
    lot, warning_or_error = validate_lot(message.text)
    if warning_or_error and not warning_or_error.startswith("⚠️ Предупреждение"):
        # Это ошибка
        await update_interface(
            state,
            message,
            f"⚠️ {warning_or_error}",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )
        return
    # Если ошибок нет (или есть предупреждение)
    await state.update_data(lot=lot)
    curr = get_user_currency(message.from_user.id)
    text = f"Введите сумму профита или убытка в {curr}\n*(для прибыли укажите число без знака или с плюсом, для убытка — со знаком минус, например: `50` или `-20`)*:"
    if warning_or_error and warning_or_error.startswith("⚠️ Предупреждение"):
        text = f"{warning_or_error}\n\n" + text
    await update_interface(
        state, message, text, reply_markup=get_back_keyboard(), parse_mode="Markdown"
    )
    await state.set_state(TradeState.waiting_for_profit)


@router.message(TradeState.waiting_for_profit)
async def process_profit(message: types.Message, state: FSMContext):
    amount, error = validate_amount(message.text)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )
        return
    await state.update_data(profit_loss=amount)
    keyboard = [
        [
            types.InlineKeyboardButton(
                text="⏩ Пропустить риск", callback_data="skip_risk"
            )
        ],
        [types.InlineKeyboardButton(text="◀️ Отмена", callback_data="main_menu")],
    ]
    text = "🛡️ Введите **планируемый риск на сделку в % от депозита** (опционально, например `1` или `1.5`):"
    await update_interface(
        state,
        message,
        text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.waiting_for_risk)


@router.message(TradeState.waiting_for_risk)
async def process_risk_text(message: types.Message, state: FSMContext):
    risk, error = validate_risk_percent(message.text)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )
        return
    await state.update_data(risk_pct=risk)
    await prompt_for_note(message, state)


@router.callback_query(F.data == "skip_risk", TradeState.waiting_for_risk)
async def process_risk_skip(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(risk_pct=0.0)
    await prompt_for_note(callback, state)


async def prompt_for_note(event, state: FSMContext):
    keyboard = [
        [
            types.InlineKeyboardButton(
                text="⏩ Пропустить заметку", callback_data="skip_note"
            )
        ],
        [types.InlineKeyboardButton(text="◀️ Отмена", callback_data="main_menu")],
    ]
    text = "✍️ Введите **заметку к сделке** (опционально):\n\nИли нажмите кнопку пропустить:"
    await update_interface(
        state,
        event,
        text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.waiting_for_note)


@router.message(TradeState.waiting_for_note)
async def process_note_text(message: types.Message, state: FSMContext):
    note, error = validate_note(message.text)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )
        return
    await state.update_data(note=note)
    await show_trade_confirmation(message, state)


@router.callback_query(F.data == "skip_note", TradeState.waiting_for_note)
async def process_note_skip(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(note="")
    await show_trade_confirmation(callback, state)


async def show_trade_confirmation(event, state: FSMContext):
    data = await state.get_data()
    pair, lot, profit_loss = data["pair"], data["lot"], data["profit_loss"]
    risk_pct, note = data.get("risk_pct", 0.0), data.get("note", "")
    result = "Win" if profit_loss >= 0 else "Loss"

    user_id = event.from_user.id
    curr = get_user_currency(user_id)
    current_deposit = get_user_deposit(user_id)
    warnings = validate_trade_confirmation(current_deposit, profit_loss)

    await state.update_data(result=result)

    keyboard = [
        [
            types.InlineKeyboardButton(
                text="✅ Подтвердить и сохранить", callback_data="trade_confirm"
            )
        ],
        [types.InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")],
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
    if warnings:
        text += "\n\n⚠️ **Предупреждения:**\n" + "\n".join(warnings)

    await update_interface(
        state,
        event,
        text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.waiting_for_confirmation)


@router.callback_query(F.data == "trade_confirm", TradeState.waiting_for_confirmation)
async def process_trade_confirm(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if "pair" not in data or "profit_loss" not in data:
        await callback.answer("⚠️ Сделка уже сохранена.", show_alert=True)
        return

    user_id = callback.from_user.id
    pair, lot, result, profit_loss = (
        data["pair"],
        data["lot"],
        data["result"],
        data["profit_loss"],
    )
    note, risk_pct = data.get("note", ""), data.get("risk_pct", 0.0)

    await state.clear()
    current_deposit = get_user_deposit(user_id)
    curr = get_user_currency(user_id)
    new_deposit = max(0.0, current_deposit + profit_loss)

    add_trade_operation(
        user_id, pair, lot, result, profit_loss, new_deposit, note, risk_pct
    )

    text = f"✅ **Сделка сохранена!**\n🔹 Пара: `{pair}`\n💰 Баланс: `{new_deposit:.2f} {curr}`"
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_main_keyboard(user_id),
        parse_mode="Markdown",
    )
