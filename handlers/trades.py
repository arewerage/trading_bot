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
from utils.i18n import get_lang, result_label, t
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


async def render_pair_prompt(event, state: FSMContext, lang: str):
    """Шаг 1: выбор пары. Обратно хода нет — это первый шаг."""
    data = await state.get_data()
    pair = data.get("pair", "")
    text = t(lang, "trades.pair_prompt")
    if pair:
        text += t(lang, "trades.current_pair", pair=pair)
    account_id = get_active_account_id(event.from_user.id)
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_pairs_keyboard(account_id, lang=lang),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.waiting_for_pair)


async def render_lot_prompt(event, state: FSMContext, lang: str):
    """Шаг 2: лот."""
    data = await state.get_data()
    lot = data.get("lot")
    text = t(lang, "trades.lot_prompt")
    if lot is not None:
        text += t(lang, "trades.current_lot", lot=lot)
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_wizard_keyboard("pair", lang=lang),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.waiting_for_lot)


async def render_side_prompt(event, state: FSMContext, lang: str, extra: str = ""):
    """Шаг 3: сторона."""
    data = await state.get_data()
    side = data.get("side")
    text = t(lang, "trades.side_prompt")
    if side:
        text += t(lang, "trades.current_side", side=side)
    if extra:
        text = f"{extra}\n\n" + text
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_side_keyboard(back_to="lot", lang=lang),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.waiting_for_side)


async def render_profit_prompt(event, state: FSMContext, lang: str):
    """Шаг 4: сумма профита/убытка."""
    data = await state.get_data()
    curr = get_user_currency(event.from_user.id)
    profit = data.get("profit_loss")
    text = t(lang, "trades.profit_prompt", currency=curr)
    if profit is not None:
        text += t(lang, "trades.current_profit", value=f"{profit:+.2f}")
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_wizard_keyboard("side", lang=lang),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.waiting_for_profit)


async def render_commission_prompt(event, state: FSMContext, lang: str):
    """Шаг 5: комиссия (опционально)."""
    data = await state.get_data()
    commission = data.get("commission")
    keyboard = [
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.skip_commission"), callback_data="skip_commission"
            )
        ],
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.back"), callback_data="wb_profit"
            ),
            types.InlineKeyboardButton(text=t(lang, "kb.menu"), callback_data="main_menu"),
        ],
    ]
    text = t(lang, "trades.commission_prompt")
    if commission is not None:
        text += t(lang, "trades.current_commission", value=f"{commission:g}")
    await update_interface(
        state,
        event,
        text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.waiting_for_commission)


async def render_risk_prompt(event, state: FSMContext, lang: str):
    """Шаг 6: риск (опционально)."""
    data = await state.get_data()
    risk = data.get("risk_pct")
    keyboard = [
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.skip_risk"), callback_data="skip_risk"
            )
        ],
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.back"), callback_data="wb_commission"
            ),
            types.InlineKeyboardButton(text=t(lang, "kb.menu"), callback_data="main_menu"),
        ],
    ]
    text = t(lang, "trades.risk_prompt")
    if risk is not None:
        text += t(lang, "trades.current_risk", risk=risk)
    await update_interface(
        state,
        event,
        text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.waiting_for_risk)


async def render_note_prompt(event, state: FSMContext, lang: str):
    """Шаг 7: заметка (опционально)."""
    data = await state.get_data()
    note = data.get("note")
    keyboard = [
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.skip_note"), callback_data="skip_note"
            )
        ],
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.back"), callback_data="wb_risk"
            ),
            types.InlineKeyboardButton(text=t(lang, "kb.menu"), callback_data="main_menu"),
        ],
    ]
    text = t(lang, "trades.note_prompt")
    if note:
        text += t(lang, "trades.current_note", note=note)
    await update_interface(
        state,
        event,
        text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.waiting_for_note)


async def render_date_prompt(event, state: FSMContext, lang: str):
    """Шаг 8: дата."""
    data = await state.get_data()
    date_str = data.get("date")
    text = t(lang, "trades.date_prompt")
    if date_str:
        date_short = f"{date_str[8:10]}.{date_str[5:7]}.{date_str[0:4]}"
        text += t(lang, "trades.current_date", date=date_short)
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_date_keyboard(back_to="note", lang=lang),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.waiting_for_date)


async def render_custom_date_prompt(event, state: FSMContext, lang: str):
    text = t(lang, "trades.custom_date_prompt")
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_wizard_keyboard("date", lang=lang),
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
        await render(callback, state, get_lang(callback.from_user.id))


# ==================== Добавление сделки ====================


@router.callback_query(F.data == "action_add_trade")
async def callback_add_trade(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    if get_user_deposit(callback.from_user.id) <= 0:
        await callback.answer(t(lang, "trades.need_deposit"), show_alert=True)
        return
    await render_pair_prompt(callback, state, lang)


@router.callback_query(F.data.startswith("sel_pair_"), TradeState.waiting_for_pair)
async def process_pair_callback(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    val = callback.data.replace("sel_pair_", "")
    if val == "custom":
        text = t(lang, "trades.new_pair_text")
        await update_interface(
            state,
            callback,
            text,
            reply_markup=get_wizard_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        await state.set_state(TradeState.waiting_for_pair)
        return
    await state.update_data(pair=val)
    await render_lot_prompt(callback, state, lang)


@router.message(TradeState.waiting_for_pair)
async def process_pair_text(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    pair, error = validate_trading_pair(message.text, lang=lang)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_wizard_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    await state.update_data(pair=pair)
    await render_lot_prompt(message, state, lang)


@router.message(TradeState.waiting_for_lot)
async def process_lot(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    lot, warning_or_error, is_warning = validate_lot(message.text, lang=lang)
    if warning_or_error and not is_warning:
        await update_interface(
            state,
            message,
            f"⚠️ {warning_or_error}",
            reply_markup=get_wizard_keyboard("pair", lang=lang),
            parse_mode="Markdown",
        )
        return
    await state.update_data(lot=lot)
    extra = warning_or_error if warning_or_error and is_warning else ""
    await render_side_prompt(message, state, lang, extra=extra)


@router.callback_query(F.data.in_({"side_buy", "side_sell"}), TradeState.waiting_for_side)
async def process_side(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    side = "Buy" if callback.data == "side_buy" else "Sell"
    await state.update_data(side=side)
    await render_profit_prompt(callback, state, lang)


@router.message(TradeState.waiting_for_profit)
async def process_profit(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    amount, error = validate_amount(message.text, lang=lang)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_wizard_keyboard("side", lang=lang),
            parse_mode="Markdown",
        )
        return
    await state.update_data(profit_loss=amount)
    await render_commission_prompt(message, state, lang)


@router.message(TradeState.waiting_for_commission)
async def process_commission_text(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    commission, error = validate_commission(message.text, lang=lang)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_wizard_keyboard("profit", lang=lang),
            parse_mode="Markdown",
        )
        return
    await state.update_data(commission=commission)
    await render_risk_prompt(message, state, lang)


@router.callback_query(F.data == "skip_commission", TradeState.waiting_for_commission)
async def process_commission_skip(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    await state.update_data(commission=0.0)
    await render_risk_prompt(callback, state, lang)


@router.message(TradeState.waiting_for_risk)
async def process_risk_text(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    risk, error = validate_risk_percent(message.text, lang=lang)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_wizard_keyboard("commission", lang=lang),
            parse_mode="Markdown",
        )
        return
    await state.update_data(risk_pct=risk)
    await render_note_prompt(message, state, lang)


@router.callback_query(F.data == "skip_risk", TradeState.waiting_for_risk)
async def process_risk_skip(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    await state.update_data(risk_pct=0.0)
    await render_note_prompt(callback, state, lang)


@router.message(TradeState.waiting_for_note)
async def process_note_text(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    note, error = validate_note(message.text, lang=lang)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_wizard_keyboard("risk", lang=lang),
            parse_mode="Markdown",
        )
        return
    await state.update_data(note=note)
    await render_date_prompt(message, state, lang)


@router.callback_query(F.data == "skip_note", TradeState.waiting_for_note)
async def process_note_skip(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    await state.update_data(note="")
    await render_date_prompt(callback, state, lang)


@router.callback_query(F.data.startswith("opdate_"), TradeState.waiting_for_date)
async def process_date(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    tz = get_user_tz_offset(callback.from_user.id)
    now = now_local(tz)
    if callback.data == "opdate_today":
        date_str = fmt_dt(now)
    elif callback.data == "opdate_yesterday":
        date_str = fmt_dt(now - timedelta(days=1))
    else:
        await render_custom_date_prompt(callback, state, lang)
        return
    await state.update_data(date=date_str)
    await show_trade_confirmation(callback, state, lang)


@router.message(TradeState.waiting_for_custom_date)
async def process_custom_date(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    d, error = validate_single_date(message.text, lang=lang)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_wizard_keyboard("date", lang=lang),
            parse_mode="Markdown",
        )
        return
    date_str = f"{d.strftime('%Y-%m-%d')} 12:00:00"
    await state.update_data(date=date_str)
    await show_trade_confirmation(message, state, lang)


async def show_trade_confirmation(event, state: FSMContext, lang: str):
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
    warnings = validate_trade_confirmation(current_deposit, net, lang=lang)

    await state.update_data(result=result, net=net)

    keyboard = [
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.confirm_save"), callback_data="trade_confirm"
            )
        ],
        [
            types.InlineKeyboardButton(text=t(lang, "kb.change"), callback_data="wb_date"),
            types.InlineKeyboardButton(text=t(lang, "kb.cancel"), callback_data="main_menu"),
        ],
    ]
    risk_str = t(lang, "trades.line_risk", risk=risk_pct) if risk_pct > 0 else ""
    note_str = t(lang, "trades.line_note", note=note) if note else ""
    side_str = t(lang, "trades.line_side", side=side) if side else ""
    commission_str = (
        t(
            lang,
            "trades.line_commission",
            commission=f"{commission:.2f}",
            currency=curr,
        )
        if commission > 0
        else ""
    )
    date_short = (
        f"{date_str[8:10]}.{date_str[5:7]}.{date_str[0:4]}" if date_str else "—"
    )
    text = t(
        lang,
        "trades.confirm",
        date=date_short,
        pair=pair,
        lot=lot,
        side=side_str,
        result=result_label(lang, result),
        net=f"{net:+.2f}",
        currency=curr,
        commission=commission_str,
        risk=risk_str,
        note=note_str,
    )
    if warnings:
        text += t(lang, "trades.warnings_header") + "\n".join(warnings)

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
    lang = get_lang(callback.from_user.id)
    data = await state.get_data()
    if "pair" not in data or "profit_loss" not in data:
        await callback.answer(t(lang, "trades.already_saved"), show_alert=True)
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
    text = t(
        lang,
        "trades.saved",
        pair=pair,
        balance=f"{new_deposit:.2f}",
        currency=curr,
    )
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_main_keyboard(user_id, lang=lang),
        parse_mode="Markdown",
    )
