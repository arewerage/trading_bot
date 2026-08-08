from datetime import timedelta

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from database import (
    add_trade_operation,
    fmt_dt,
    get_active_account_id,
    get_user_currency,
    get_user_deposit,
    get_user_tz_offset,
    now_local,
    now_local_str,
)
from handlers.common import update_interface
from keyboards.inline import (
    get_back_keyboard,
    get_date_keyboard,
    get_main_keyboard,
    get_pairs_keyboard,
    get_side_keyboard,
)
from states.fsm import TradeState
from utils.validators import (
    validate_amount,
    validate_commission,
    validate_lot,
    validate_note,
    validate_risk_percent,
    validate_single_date,
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
    account_id = get_active_account_id(callback.from_user.id)
    text = "Выберите торговую пару из списка или введите новую:"
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_pairs_keyboard(account_id),
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
        await update_interface(
            state,
            message,
            f"⚠️ {warning_or_error}",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )
        return
    await state.update_data(lot=lot)
    text = "Выберите направление сделки:"
    if warning_or_error and warning_or_error.startswith("⚠️ Предупреждение"):
        text = f"{warning_or_error}\n\n" + text
    await update_interface(
        state, message, text, reply_markup=get_side_keyboard(), parse_mode="Markdown"
    )
    await state.set_state(TradeState.waiting_for_side)


@router.callback_query(F.data.in_({"side_buy", "side_sell"}), TradeState.waiting_for_side)
async def process_side(callback: types.CallbackQuery, state: FSMContext):
    side = "Buy" if callback.data == "side_buy" else "Sell"
    await state.update_data(side=side)
    curr = get_user_currency(callback.from_user.id)
    text = f"Направление: `{side}`\n\nВведите сумму профита или убытка в {curr}\n*(для прибыли укажите число без знака или с плюсом, для убытка — со знаком минус, например: `50` или `-20`)*:"
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown",
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
                text="⏩ Пропустить комиссию", callback_data="skip_commission"
            )
        ],
        [types.InlineKeyboardButton(text="◀️ Отмена", callback_data="main_menu")],
    ]
    text = "💸 Введите **комиссию по сделке** (опционально).\n\n*Комиссия будет вычтена из указанной суммы.* Например: `2` или `0.5`:"
    await update_interface(
        state,
        message,
        text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.waiting_for_commission)


@router.message(TradeState.waiting_for_commission)
async def process_commission_text(message: types.Message, state: FSMContext):
    commission, error = validate_commission(message.text)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )
        return
    await state.update_data(commission=commission)
    await prompt_for_risk(message, state)


@router.callback_query(F.data == "skip_commission", TradeState.waiting_for_commission)
async def process_commission_skip(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(commission=0.0)
    await prompt_for_risk(callback, state)


async def prompt_for_risk(event, state: FSMContext):
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
        event,
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
    await prompt_for_date(message, state)


@router.callback_query(F.data == "skip_note", TradeState.waiting_for_note)
async def process_note_skip(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(note="")
    await prompt_for_date(callback, state)


async def prompt_for_date(event, state: FSMContext):
    text = "📅 Укажите **дату сделки**:"
    await update_interface(
        state, event, text, reply_markup=get_date_keyboard(), parse_mode="Markdown"
    )
    await state.set_state(TradeState.waiting_for_date)


@router.callback_query(F.data.startswith("opdate_"), TradeState.waiting_for_date)
async def process_date(callback: types.CallbackQuery, state: FSMContext):
    tz = get_user_tz_offset(callback.from_user.id)
    now = now_local(tz)
    if callback.data == "opdate_today":
        date_str = fmt_dt(now)
    elif callback.data == "opdate_yesterday":
        date_str = fmt_dt(now - timedelta(days=1))
    else:
        text = "✍️ Введите дату в формате `ДД.ММ.ГГГГ` (например, `05.01.2026`):"
        await update_interface(
            state,
            callback,
            text,
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )
        await state.set_state(TradeState.waiting_for_custom_date)
        return
    await state.update_data(date=date_str)
    await show_trade_confirmation(callback, state)


@router.message(TradeState.waiting_for_custom_date)
async def process_custom_date(message: types.Message, state: FSMContext):
    d, error = validate_single_date(message.text)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )
        return
    date_str = f"{d.strftime('%Y-%m-%d')} 12:00:00"
    await state.update_data(date=date_str)
    await show_trade_confirmation(message, state)


async def show_trade_confirmation(event, state: FSMContext):
    data = await state.get_data()
    pair, lot, profit_loss = data["pair"], data["lot"], data["profit_loss"]
    commission = data.get("commission", 0.0)
    side = data.get("side", "")
    risk_pct, note = data.get("risk_pct", 0.0), data.get("note", "")
    date_str = data.get("date", "")
    net = profit_loss - commission
    result = "Win" if net >= 0 else "Loss"

    user_id = event.from_user.id
    curr = get_user_currency(user_id)
    current_deposit = get_user_deposit(user_id)
    warnings = validate_trade_confirmation(current_deposit, net)

    await state.update_data(result=result, net=net)

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
    side_str = f"🔹 Направление: `{side}`\n" if side else ""
    commission_str = (
        f"🔹 Комиссия: `{commission:.2f} {curr}` (учтена)\n" if commission > 0 else ""
    )
    date_short = (
        f"{date_str[8:10]}.{date_str[5:7]}.{date_str[0:4]}" if date_str else "—"
    )
    text = (
        f"📋 **Проверьте данные сделки:**\n\n"
        f"📅 Дата: `{date_short}`\n"
        f"🔹 Пара: `{pair}`\n🔹 Лот: `{lot}`\n"
        f"{side_str}"
        f"🔹 Исход: `{'Плюс' if result == 'Win' else 'Минус'}`\n"
        f"🔹 Профит / Убыток: `{net:+.2f} {curr}`\n"
        f"{commission_str}{risk_str}{note_str}"
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
    account_id = get_active_account_id(user_id)
    pair, lot, result, net = (
        data["pair"],
        data["lot"],
        data["result"],
        data["net"],
    )
    commission = data.get("commission", 0.0)
    side = data.get("side", "")
    note, risk_pct = data.get("note", ""), data.get("risk_pct", 0.0)
    date_str = data.get("date") or now_local_str(tz_offset=get_user_tz_offset(user_id))

    await state.clear()
    add_trade_operation(
        user_id,
        account_id,
        date_str,
        pair,
        lot,
        side,
        result,
        net,
        commission,
        note,
        risk_pct,
    )

    curr = get_user_currency(user_id)
    new_deposit = get_user_deposit(user_id)
    text = f"✅ **Сделка сохранена!**\n🔹 Пара: `{pair}`\n💰 Баланс: `{new_deposit:.2f} {curr}`"
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_main_keyboard(user_id),
        parse_mode="Markdown",
    )
