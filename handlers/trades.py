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
    get_date_keyboard,
    get_main_keyboard,
    get_pairs_keyboard,
    get_side_keyboard,
    get_wizard_keyboard,
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


# ==================== Промпты шагов мастера ====================


async def render_pair_prompt(event, state: FSMContext):
    """Шаг 1: выбор пары. Обратно хода нет — это первый шаг."""
    data = await state.get_data()
    pair = data.get("pair", "")
    text = "Выберите торговую пару из списка или введите новую:"
    if pair:
        text += f"\n\nТекущая пара: `{pair}`"
    account_id = get_active_account_id(event.from_user.id)
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_pairs_keyboard(account_id),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.waiting_for_pair)


async def render_lot_prompt(event, state: FSMContext):
    """Шаг 2: лот."""
    data = await state.get_data()
    lot = data.get("lot")
    text = "Введите объем лота (например, `0.1`):"
    if lot is not None:
        text += f"\n\nТекущий лот: `{lot}`"
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_wizard_keyboard("pair"),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.waiting_for_lot)


async def render_side_prompt(event, state: FSMContext, extra: str = ""):
    """Шаг 3: сторона."""
    data = await state.get_data()
    side = data.get("side")
    text = "Выберите направление сделки:"
    if side:
        text += f"\n\nТекущее направление: `{side}`"
    if extra:
        text = f"{extra}\n\n" + text
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_side_keyboard(back_to="lot"),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.waiting_for_side)


async def render_profit_prompt(event, state: FSMContext):
    """Шаг 4: сумма профита/убытка."""
    data = await state.get_data()
    curr = get_user_currency(event.from_user.id)
    profit = data.get("profit_loss")
    text = (
        f"Введите сумму профита или убытка в {curr}\n"
        "*(для прибыли укажите число без знака или с плюсом, для убытка — со знаком "
        "минус, например: `50` или `-20`)*:"
    )
    if profit is not None:
        text += f"\n\nТекущее значение: `{profit:+.2f}`"
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_wizard_keyboard("side"),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.waiting_for_profit)


async def render_commission_prompt(event, state: FSMContext):
    """Шаг 5: комиссия (опционально)."""
    data = await state.get_data()
    commission = data.get("commission")
    keyboard = [
        [
            types.InlineKeyboardButton(
                text="⏩ Пропустить комиссию", callback_data="skip_commission"
            )
        ],
        [
            types.InlineKeyboardButton(
                text="◀️ Назад", callback_data="wb_profit"
            ),
            types.InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
        ],
    ]
    text = (
        "💸 Введите **комиссию по сделке** (опционально).\n\n"
        "*Комиссия будет вычтена из указанной суммы.* Например: `2` или `0.5`:"
    )
    if commission is not None:
        text += f"\n\nТекущая комиссия: `{commission:g}`"
    await update_interface(
        state,
        event,
        text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.waiting_for_commission)


async def render_risk_prompt(event, state: FSMContext):
    """Шаг 6: риск (опционально)."""
    data = await state.get_data()
    risk = data.get("risk_pct")
    keyboard = [
        [
            types.InlineKeyboardButton(
                text="⏩ Пропустить риск", callback_data="skip_risk"
            )
        ],
        [
            types.InlineKeyboardButton(
                text="◀️ Назад", callback_data="wb_commission"
            ),
            types.InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
        ],
    ]
    text = (
        "🛡️ Введите **планируемый риск на сделку в % от депозита** "
        "(опционально, например `1` или `1.5`):"
    )
    if risk is not None:
        text += f"\n\nТекущий риск: `{risk}%`"
    await update_interface(
        state,
        event,
        text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.waiting_for_risk)


async def render_note_prompt(event, state: FSMContext):
    """Шаг 7: заметка (опционально)."""
    data = await state.get_data()
    note = data.get("note")
    keyboard = [
        [
            types.InlineKeyboardButton(
                text="⏩ Пропустить заметку", callback_data="skip_note"
            )
        ],
        [
            types.InlineKeyboardButton(
                text="◀️ Назад", callback_data="wb_risk"
            ),
            types.InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
        ],
    ]
    text = "✍️ Введите **заметку к сделке** (опционально):\n\nИли нажмите кнопку пропустить:"
    if note:
        text += f"\n\nТекущая заметка: _{note}_"
    await update_interface(
        state,
        event,
        text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.waiting_for_note)


async def render_date_prompt(event, state: FSMContext):
    """Шаг 8: дата."""
    data = await state.get_data()
    date_str = data.get("date")
    text = "📅 Укажите **дату сделки**:"
    if date_str:
        date_short = f"{date_str[8:10]}.{date_str[5:7]}.{date_str[0:4]}"
        text += f"\n\nТекущая дата: `{date_short}`"
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_date_keyboard(back_to="note"),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.waiting_for_date)


async def render_custom_date_prompt(event, state: FSMContext):
    text = "✍️ Введите дату в формате `ДД.ММ.ГГГГ` (например, `05.01.2026`):"
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_wizard_keyboard("date"),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.waiting_for_custom_date)


# ==================== Навигация «Назад» в мастере ====================

_BACK_HANDLERS = {
    "wb_pair": render_pair_prompt,
    "wb_lot": render_lot_prompt,
    "wb_side": render_side_prompt,
    "wb_profit": render_profit_prompt,
    "wb_commission": render_commission_prompt,
    "wb_risk": render_risk_prompt,
    "wb_note": render_note_prompt,
    "wb_date": render_date_prompt,
}


@router.callback_query(F.data.startswith("wb_"))
async def wizard_back(callback: types.CallbackQuery, state: FSMContext):
    render = _BACK_HANDLERS.get(callback.data)
    if render:
        await render(callback, state)


# ==================== Добавление сделки ====================


@router.callback_query(F.data == "action_add_trade")
async def callback_add_trade(callback: types.CallbackQuery, state: FSMContext):
    if get_user_deposit(callback.from_user.id) <= 0:
        await callback.answer("Сначала установите стартовый депозит!", show_alert=True)
        return
    await render_pair_prompt(callback, state)


@router.callback_query(F.data.startswith("sel_pair_"), TradeState.waiting_for_pair)
async def process_pair_callback(callback: types.CallbackQuery, state: FSMContext):
    val = callback.data.replace("sel_pair_", "")
    if val == "custom":
        text = "Введите название новой торговой пары текстом (например, `EURUSD`):"
        await update_interface(
            state,
            callback,
            text,
            reply_markup=get_wizard_keyboard(),
            parse_mode="Markdown",
        )
        await state.set_state(TradeState.waiting_for_pair)
        return
    await state.update_data(pair=val)
    await render_lot_prompt(callback, state)


@router.message(TradeState.waiting_for_pair)
async def process_pair_text(message: types.Message, state: FSMContext):
    pair, error = validate_trading_pair(message.text)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_wizard_keyboard(),
            parse_mode="Markdown",
        )
        return
    await state.update_data(pair=pair)
    await render_lot_prompt(message, state)


@router.message(TradeState.waiting_for_lot)
async def process_lot(message: types.Message, state: FSMContext):
    lot, warning_or_error = validate_lot(message.text)
    if warning_or_error and not warning_or_error.startswith("⚠️ Предупреждение"):
        await update_interface(
            state,
            message,
            f"⚠️ {warning_or_error}",
            reply_markup=get_wizard_keyboard("pair"),
            parse_mode="Markdown",
        )
        return
    await state.update_data(lot=lot)
    extra = warning_or_error if warning_or_error and warning_or_error.startswith("⚠️ Предупреждение") else ""
    await render_side_prompt(message, state, extra=extra)


@router.callback_query(F.data.in_({"side_buy", "side_sell"}), TradeState.waiting_for_side)
async def process_side(callback: types.CallbackQuery, state: FSMContext):
    side = "Buy" if callback.data == "side_buy" else "Sell"
    await state.update_data(side=side)
    await render_profit_prompt(callback, state)


@router.message(TradeState.waiting_for_profit)
async def process_profit(message: types.Message, state: FSMContext):
    amount, error = validate_amount(message.text)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_wizard_keyboard("side"),
            parse_mode="Markdown",
        )
        return
    await state.update_data(profit_loss=amount)
    await render_commission_prompt(message, state)


@router.message(TradeState.waiting_for_commission)
async def process_commission_text(message: types.Message, state: FSMContext):
    commission, error = validate_commission(message.text)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_wizard_keyboard("profit"),
            parse_mode="Markdown",
        )
        return
    await state.update_data(commission=commission)
    await render_risk_prompt(message, state)


@router.callback_query(F.data == "skip_commission", TradeState.waiting_for_commission)
async def process_commission_skip(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(commission=0.0)
    await render_risk_prompt(callback, state)


@router.message(TradeState.waiting_for_risk)
async def process_risk_text(message: types.Message, state: FSMContext):
    risk, error = validate_risk_percent(message.text)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_wizard_keyboard("commission"),
            parse_mode="Markdown",
        )
        return
    await state.update_data(risk_pct=risk)
    await render_note_prompt(message, state)


@router.callback_query(F.data == "skip_risk", TradeState.waiting_for_risk)
async def process_risk_skip(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(risk_pct=0.0)
    await render_note_prompt(callback, state)


@router.message(TradeState.waiting_for_note)
async def process_note_text(message: types.Message, state: FSMContext):
    note, error = validate_note(message.text)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_wizard_keyboard("risk"),
            parse_mode="Markdown",
        )
        return
    await state.update_data(note=note)
    await render_date_prompt(message, state)


@router.callback_query(F.data == "skip_note", TradeState.waiting_for_note)
async def process_note_skip(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(note="")
    await render_date_prompt(callback, state)


@router.callback_query(F.data.startswith("opdate_"), TradeState.waiting_for_date)
async def process_date(callback: types.CallbackQuery, state: FSMContext):
    tz = get_user_tz_offset(callback.from_user.id)
    now = now_local(tz)
    if callback.data == "opdate_today":
        date_str = fmt_dt(now)
    elif callback.data == "opdate_yesterday":
        date_str = fmt_dt(now - timedelta(days=1))
    else:
        await render_custom_date_prompt(callback, state)
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
            reply_markup=get_wizard_keyboard("date"),
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
        [
            types.InlineKeyboardButton(text="✏️ Изменить", callback_data="wb_date"),
            types.InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu"),
        ],
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
