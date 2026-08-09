import math
from datetime import timedelta

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from database import (
    delete_operation,
    fmt_dt,
    get_active_account_id,
    get_balance_operation,
    get_balance_operations,
    get_operation,
    get_operations_page,
    get_operations_page_filtered,
    get_trade,
    get_trades,
    get_user_currency,
    get_user_deposit,
    get_user_tz_offset,
    now_local,
    update_operation_amount,
    update_operation_date,
    update_operation_note,
    update_trade_amount,
    update_trade_commission,
    update_trade_date,
    update_trade_lot,
    update_trade_note,
    update_trade_pair,
    update_trade_risk,
    update_trade_side,
)
from handlers.common import update_interface
from keyboards.inline import (
    get_back_keyboard,
    get_date_keyboard,
    get_del_ops_keyboard,
    get_edit_op_keyboard,
    get_edit_ops_keyboard,
    get_edit_trade_keyboard,
    get_edit_trades_keyboard,
    get_history_keyboard,
    get_main_keyboard,
    get_pairs_keyboard,
    get_side_keyboard,
)
from states.fsm import EditOpState, TradeState
from utils.i18n import get_lang, op_type_label, result_label, t
from utils.validators import (
    validate_amount,
    validate_commission,
    validate_lot,
    validate_note,
    validate_risk_percent,
    validate_single_date,
    validate_trading_pair,
)

router = Router()

HIST_PER_PAGE = 6
LIST_PER_PAGE = 8

# Ключи — payload фильтров (all/trades/deposits/withdrawals), значения — типы операций в БД.
# Отображаемые подписи фильтров локализуются в keyboards/inline.py (kb.hist_*).
_OP_TYPE_MAP = {
    "trades": ["Сделка"],
    "deposits": ["Пополнение"],
    "withdrawals": ["Вывод"],
}


def _op_line(row, curr: str, lang: str) -> str:
    op_id, date, op_type, pair, lot, result, amount, balance_after, note, risk_pct, side, commission = row
    if op_type == "Сделка":
        res_emoji = "✅" if result == "Win" else "❌"
        note_str = f" | _{note}_" if note else ""
        risk_str = f" [🛡 {risk_pct}%]" if risk_pct > 0 else ""
        side_str = f" {side}" if side in ("Buy", "Sell") else ""
        return t(
            lang,
            "hist.op_line_trade",
            date=date,
            pair=pair,
            lot=lot,
            side=side_str,
            emoji=res_emoji,
            amount=f"{amount:+.2f}",
            currency=curr,
            risk=risk_str,
            note=note_str,
        )
    return t(
        lang,
        "hist.op_line_op",
        date=date,
        op_type=op_type_label(lang, op_type),
        amount=f"{amount:+.2f}",
        currency=curr,
    )


@router.callback_query(F.data == "noop")
async def callback_noop(callback: types.CallbackQuery):
    await callback.answer()


# --- История (с пагинацией и фильтром) ---
async def render_history(callback: types.CallbackQuery, state: FSMContext, page: int):
    user_id = callback.from_user.id
    lang = get_lang(user_id)
    account_id = get_active_account_id(user_id)
    curr = get_user_currency(user_id)
    data = await state.get_data()
    op_filter = data.get("history_filter", "all")

    if op_filter in _OP_TYPE_MAP:
        rows, total = get_operations_page_filtered(
            account_id, page, HIST_PER_PAGE, _OP_TYPE_MAP[op_filter]
        )
    else:
        op_filter = "all"
        await state.update_data(history_filter="all")
        rows, total = get_operations_page(account_id, page, HIST_PER_PAGE)
    pages = max(1, math.ceil(total / HIST_PER_PAGE))
    page = min(page, pages)

    if not rows:
        text = t(lang, "hist.empty")
        await update_interface(
            state,
            callback,
            text,
            reply_markup=get_history_keyboard(
                page, total, HIST_PER_PAGE, bool(get_trades(account_id)), op_filter, lang=lang
            ),
            parse_mode="Markdown",
        )
        return

    text = t(lang, "hist.title", page=page, pages=pages)
    for row in rows:
        text += _op_line(row, curr, lang)

    has_trades = bool(get_trades(account_id))
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_history_keyboard(
            page, total, HIST_PER_PAGE, has_trades, op_filter, lang=lang
        ),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "action_history")
async def callback_history(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(history_filter="all")
    await render_history(callback, state, 1)


@router.callback_query(F.data.startswith("hist_page_"))
async def callback_history_page(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.replace("hist_page_", ""))
    await render_history(callback, state, page)


@router.callback_query(F.data.startswith("hist_filter_"))
async def callback_history_filter(callback: types.CallbackQuery, state: FSMContext):
    op_filter = callback.data.replace("hist_filter_", "")
    if op_filter not in _OP_TYPE_MAP:
        op_filter = "all"
    await state.update_data(history_filter=op_filter)
    await render_history(callback, state, 1)


# --- Удаление любой операции ---
async def render_del_list(callback: types.CallbackQuery, state: FSMContext, page: int):
    user_id = callback.from_user.id
    lang = get_lang(user_id)
    account_id = get_active_account_id(user_id)
    rows, total = get_operations_page(account_id, page, LIST_PER_PAGE)
    if not rows:
        await callback.answer(t(lang, "hist.no_ops"), show_alert=True)
        await render_history(callback, state, 1)
        return
    text = t(lang, "hist.del_title", page=page)
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_del_ops_keyboard(rows, page, total, LIST_PER_PAGE, lang=lang),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "del_op_menu")
async def callback_del_menu(callback: types.CallbackQuery, state: FSMContext):
    await render_del_list(callback, state, 1)


@router.callback_query(F.data.startswith("del_page_"))
async def callback_del_page(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.replace("del_page_", ""))
    await render_del_list(callback, state, page)


@router.callback_query(F.data.startswith("del_op_"))
async def callback_delete_op(callback: types.CallbackQuery, state: FSMContext):
    op_id = int(callback.data.replace("del_op_", ""))
    user_id = callback.from_user.id
    lang = get_lang(user_id)
    account_id = get_active_account_id(user_id)
    op = get_operation(account_id, op_id)
    if not op:
        await callback.answer(t(lang, "hist.op_not_found"), show_alert=True)
        return

    op_id, date, op_type, pair, lot, result, amount, balance_after, note, risk_pct, side, commission = op
    curr = get_user_currency(user_id)
    await state.update_data(delete_op_id=op_id)

    text = t(lang, "hist.del_confirm_title")
    if op_type == "Сделка":
        text += t(
            lang,
            "hist.del_trade_detail",
            date=date,
            pair=pair,
            lot=lot,
            result=result_label(lang, result),
            amount=f"{amount:+.2f}",
            currency=curr,
        )
    else:
        text += t(
            lang,
            "hist.del_op_detail",
            date=date,
            op_type=op_type_label(lang, op_type),
            amount=f"{amount:+.2f}",
            currency=curr,
        )
    if note:
        text += t(lang, "hist.note_line", note=note)
    text += t(lang, "hist.del_recalc_note")

    keyboard = [
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.yes_delete"), callback_data="confirm_del_op"
            )
        ],
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.back_list"), callback_data="del_op_menu"
            )
        ],
    ]
    await update_interface(
        state,
        callback,
        text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "confirm_del_op")
async def callback_confirm_delete(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    op_id = data.get("delete_op_id")
    user_id = callback.from_user.id
    lang = get_lang(user_id)
    if not op_id:
        await callback.answer(t(lang, "hist.op_already_deleted"), show_alert=True)
        return

    account_id = get_active_account_id(user_id)
    success = delete_operation(account_id, op_id)
    curr = get_user_currency(user_id)
    await state.clear()

    if success:
        new_deposit = get_user_deposit(user_id)
        text = t(lang, "hist.deleted_ok", balance=f"{new_deposit:.2f}", currency=curr)
    else:
        text = t(lang, "hist.delete_failed")

    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_main_keyboard(user_id, lang=lang),
        parse_mode="Markdown",
    )


# --- Редактирование сделки ---
async def render_edit_list(callback: types.CallbackQuery, state: FSMContext, page: int):
    user_id = callback.from_user.id
    lang = get_lang(user_id)
    account_id = get_active_account_id(user_id)
    rows = get_trades(account_id)
    total = len(rows)
    if total == 0:
        await callback.answer(t(lang, "hist.no_trades_edit"), show_alert=True)
        await render_history(callback, state, 1)
        return
    pages = max(1, math.ceil(total / LIST_PER_PAGE))
    page = min(page, pages)
    start = (page - 1) * LIST_PER_PAGE
    page_rows = rows[start : start + LIST_PER_PAGE]
    text = t(lang, "hist.edit_trade_title", page=page, pages=pages)
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_edit_trades_keyboard(page_rows, page, total, LIST_PER_PAGE, lang=lang),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "edit_trade_menu")
async def callback_edit_menu(callback: types.CallbackQuery, state: FSMContext):
    await render_edit_list(callback, state, 1)


@router.callback_query(F.data.startswith("edit_page_"))
async def callback_edit_page(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.replace("edit_page_", ""))
    await render_edit_list(callback, state, page)


@router.callback_query(F.data.startswith("edit_trade_"))
async def callback_edit_trade(callback: types.CallbackQuery, state: FSMContext):
    trade_id = int(callback.data.replace("edit_trade_", ""))
    user_id = callback.from_user.id
    lang = get_lang(user_id)
    account_id = get_active_account_id(user_id)
    trade = get_trade(account_id, trade_id)
    if not trade:
        await callback.answer(t(lang, "hist.trade_not_found"), show_alert=True)
        return
    await state.update_data(edit_trade_id=trade_id)
    await render_edit_detail(callback, state, trade)


async def render_edit_detail(event, state: FSMContext, trade, status: str = ""):
    trade_id, date, pair, lot, side, result, amount, note, risk_pct, commission = trade
    user_id = event.from_user.id
    lang = get_lang(user_id)
    curr = get_user_currency(user_id)
    side_str = f" {side}" if side in ("Buy", "Sell") else ""
    note_str = t(lang, "hist.note_line", note=note) if note else ""
    risk_str = t(lang, "hist.line_risk", risk=risk_pct) if risk_pct > 0 else ""
    commission_str = (
        t(lang, "hist.line_commission", commission=f"{commission:.2f}", currency=curr)
        if commission > 0
        else ""
    )
    status_str = f"{status}\n\n" if status else ""
    text = status_str + t(
        lang,
        "hist.edit_trade_detail",
        date=date,
        pair=pair,
        lot=lot,
        side=side_str,
        result=result_label(lang, result),
        amount=f"{amount:+.2f}",
        currency=curr,
        commission=commission_str,
        risk=risk_str,
        note=note_str,
    )
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_edit_trade_keyboard(trade_id, lang=lang),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "edit_field_amount")
async def callback_edit_amount(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    text = t(lang, "hist.edit_amount_prompt")
    await update_interface(
        state, callback, text, reply_markup=get_back_keyboard(lang=lang), parse_mode="Markdown"
    )
    await state.set_state(TradeState.edit_amount)


@router.callback_query(F.data == "edit_field_note")
async def callback_edit_note(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    text = t(lang, "hist.edit_note_prompt")
    await update_interface(
        state, callback, text, reply_markup=get_back_keyboard(lang=lang), parse_mode="Markdown"
    )
    await state.set_state(TradeState.edit_note)


@router.callback_query(F.data == "edit_field_risk")
async def callback_edit_risk(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    text = t(lang, "hist.edit_risk_prompt")
    await update_interface(
        state, callback, text, reply_markup=get_back_keyboard(lang=lang), parse_mode="Markdown"
    )
    await state.set_state(TradeState.edit_risk)


async def _refresh_edit_detail(event, state: FSMContext, message_ok: str):
    data = await state.get_data()
    trade_id = data.get("edit_trade_id")
    user_id = event.from_user.id
    lang = get_lang(user_id)
    account_id = get_active_account_id(user_id)
    trade = get_trade(account_id, trade_id)
    if trade:
        await render_edit_detail(event, state, trade, status=message_ok)
    else:
        await update_interface(
            state,
            event,
            f"⚠️ {t(lang, 'hist.trade_not_found')}",
            reply_markup=get_main_keyboard(user_id, lang=lang),
            parse_mode="Markdown",
        )


@router.message(TradeState.edit_amount)
async def process_edit_amount(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    amount, error = validate_amount(message.text, lang=lang)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    data = await state.get_data()
    trade_id = data.get("edit_trade_id")
    user_id = message.from_user.id
    account_id = get_active_account_id(user_id)
    update_trade_amount(account_id, trade_id, amount)
    await _refresh_edit_detail(message, state, t(lang, "hist.updated_amount"))


@router.message(TradeState.edit_note)
async def process_edit_note(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    note, error = validate_note(message.text, lang=lang)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    if note == "-":
        note = ""
    data = await state.get_data()
    trade_id = data.get("edit_trade_id")
    user_id = message.from_user.id
    account_id = get_active_account_id(user_id)
    update_trade_note(account_id, trade_id, note)
    await _refresh_edit_detail(message, state, t(lang, "hist.updated_note"))


@router.message(TradeState.edit_risk)
async def process_edit_risk(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    risk, error = validate_risk_percent(message.text, lang=lang)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    data = await state.get_data()
    trade_id = data.get("edit_trade_id")
    user_id = message.from_user.id
    account_id = get_active_account_id(user_id)
    update_trade_risk(account_id, trade_id, risk)
    await _refresh_edit_detail(message, state, t(lang, "hist.updated_risk"))


# --- Дата ---
@router.callback_query(F.data == "edit_field_date")
async def callback_edit_date(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    text = t(lang, "hist.edit_date_prompt")
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_date_keyboard(prefix="editdate", lang=lang),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.edit_date)


async def _apply_edit_date(event, state: FSMContext, date_str: str):
    data = await state.get_data()
    trade_id = data.get("edit_trade_id")
    lang = get_lang(event.from_user.id)
    account_id = get_active_account_id(event.from_user.id)
    update_trade_date(account_id, trade_id, date_str)
    await _refresh_edit_detail(event, state, t(lang, "hist.updated_date"))


@router.callback_query(F.data.startswith("editdate_"), TradeState.edit_date)
async def process_edit_date(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    if callback.data == "editdate_custom":
        await update_interface(
            state,
            callback,
            t(lang, "trades.custom_date_prompt"),
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        await state.set_state(TradeState.edit_date_custom)
        return
    tz = get_user_tz_offset(callback.from_user.id)
    now = now_local(tz)
    if callback.data == "editdate_today":
        date_str = fmt_dt(now)
    else:
        date_str = fmt_dt(now - timedelta(days=1))
    await _apply_edit_date(callback, state, date_str)


@router.message(TradeState.edit_date_custom)
async def process_edit_date_custom(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    d, error = validate_single_date(message.text, lang=lang)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    date_str = f"{d.strftime('%Y-%m-%d')} 12:00:00"
    await _apply_edit_date(message, state, date_str)


# --- Пара ---
@router.callback_query(F.data == "edit_field_pair")
async def callback_edit_pair(callback: types.CallbackQuery, state: FSMContext):
    account_id = get_active_account_id(callback.from_user.id)
    lang = get_lang(callback.from_user.id)
    text = t(lang, "hist.edit_pair_prompt")
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_pairs_keyboard(account_id, prefix="editpair", lang=lang),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.edit_pair)


async def _apply_edit_pair(event, state: FSMContext, pair: str):
    data = await state.get_data()
    trade_id = data.get("edit_trade_id")
    lang = get_lang(event.from_user.id)
    account_id = get_active_account_id(event.from_user.id)
    update_trade_pair(account_id, trade_id, pair)
    await _refresh_edit_detail(event, state, t(lang, "hist.updated_pair"))


@router.callback_query(F.data.startswith("editpair_"), TradeState.edit_pair)
async def process_edit_pair(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    val = callback.data.replace("editpair_", "")
    if val == "custom":
        await update_interface(
            state,
            callback,
            t(lang, "hist.edit_pair_custom"),
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        await state.set_state(TradeState.edit_pair_custom)
        return
    await _apply_edit_pair(callback, state, val)


@router.message(TradeState.edit_pair_custom)
async def process_edit_pair_custom(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    pair, error = validate_trading_pair(message.text, lang=lang)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    await _apply_edit_pair(message, state, pair)


# --- Лот ---
@router.callback_query(F.data == "edit_field_lot")
async def callback_edit_lot(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    text = t(lang, "hist.edit_lot_prompt")
    await update_interface(
        state, callback, text, reply_markup=get_back_keyboard(lang=lang), parse_mode="Markdown"
    )
    await state.set_state(TradeState.edit_lot)


@router.message(TradeState.edit_lot)
async def process_edit_lot(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    lot, warning_or_error, is_warning = validate_lot(message.text, lang=lang)
    if warning_or_error and not is_warning:
        await update_interface(
            state,
            message,
            f"⚠️ {warning_or_error}",
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    data = await state.get_data()
    trade_id = data.get("edit_trade_id")
    account_id = get_active_account_id(message.from_user.id)
    update_trade_lot(account_id, trade_id, lot)
    await _refresh_edit_detail(message, state, t(lang, "hist.updated_lot"))


# --- Сторона ---
@router.callback_query(F.data == "edit_field_side")
async def callback_edit_side(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    text = t(lang, "hist.edit_side_prompt")
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_side_keyboard(prefix="editside", lang=lang),
        parse_mode="Markdown",
    )
    await state.set_state(TradeState.edit_side)


@router.callback_query(
    F.data.in_({"editside_buy", "editside_sell"}), TradeState.edit_side
)
async def process_edit_side(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    side = "Buy" if callback.data == "editside_buy" else "Sell"
    data = await state.get_data()
    trade_id = data.get("edit_trade_id")
    account_id = get_active_account_id(callback.from_user.id)
    update_trade_side(account_id, trade_id, side)
    await _refresh_edit_detail(callback, state, t(lang, "hist.updated_side"))


# --- Комиссия ---
@router.callback_query(F.data == "edit_field_commission")
async def callback_edit_commission(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    text = t(lang, "hist.edit_commission_prompt")
    await update_interface(
        state, callback, text, reply_markup=get_back_keyboard(lang=lang), parse_mode="Markdown"
    )
    await state.set_state(TradeState.edit_commission)


@router.message(TradeState.edit_commission)
async def process_edit_commission(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    commission, error = validate_commission(message.text, lang=lang)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    data = await state.get_data()
    trade_id = data.get("edit_trade_id")
    account_id = get_active_account_id(message.from_user.id)
    update_trade_commission(account_id, trade_id, commission)
    await _refresh_edit_detail(message, state, t(lang, "hist.updated_commission"))


# ==================== Редактирование пополнений/выводов ====================


async def render_edit_op_list(event, state: FSMContext, page: int):
    user_id = event.from_user.id
    lang = get_lang(user_id)
    account_id = get_active_account_id(user_id)
    ops = get_balance_operations(account_id)
    total = len(ops)
    if total == 0:
        await event.answer(t(lang, "hist.no_ops_edit"), show_alert=True)
        await render_history(event, state, 1)
        return
    pages = max(1, math.ceil(total / LIST_PER_PAGE))
    page = min(page, pages)
    start = (page - 1) * LIST_PER_PAGE
    page_rows = ops[start : start + LIST_PER_PAGE]
    text = t(lang, "hist.edit_op_title", page=page, pages=pages)
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_edit_ops_keyboard(page_rows, page, total, LIST_PER_PAGE, lang=lang),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "edit_op_menu")
async def callback_edit_op_menu(callback: types.CallbackQuery, state: FSMContext):
    await render_edit_op_list(callback, state, 1)


@router.callback_query(F.data.startswith("editop_page_"))
async def callback_edit_op_page(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.replace("editop_page_", ""))
    await render_edit_op_list(callback, state, page)


@router.callback_query(F.data.startswith("edit_op_"))
async def callback_edit_op(callback: types.CallbackQuery, state: FSMContext):
    op_id = int(callback.data.replace("edit_op_", ""))
    user_id = callback.from_user.id
    lang = get_lang(user_id)
    account_id = get_active_account_id(user_id)
    op = get_balance_operation(account_id, op_id)
    if not op:
        await callback.answer(t(lang, "hist.op_not_found"), show_alert=True)
        return
    await state.update_data(edit_op_id=op_id)
    await render_edit_op_detail(callback, state, op)


async def render_edit_op_detail(event, state: FSMContext, op, status: str = ""):
    op_id, date, op_type, amount, note = op
    user_id = event.from_user.id
    lang = get_lang(user_id)
    curr = get_user_currency(user_id)
    note_str = t(lang, "hist.note_line", note=note) if note else ""
    status_str = f"{status}\n\n" if status else ""
    text = status_str + t(
        lang,
        "hist.edit_op_detail",
        date=date,
        op_type=op_type_label(lang, op_type),
        amount=f"{amount:+.2f}",
        currency=curr,
        note=note_str,
    )
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_edit_op_keyboard(op_id, lang=lang),
        parse_mode="Markdown",
    )


async def _refresh_edit_op_detail(event, state: FSMContext, status: str):
    data = await state.get_data()
    op_id = data.get("edit_op_id")
    lang = get_lang(event.from_user.id)
    account_id = get_active_account_id(event.from_user.id)
    op = get_balance_operation(account_id, op_id)
    if op:
        await render_edit_op_detail(event, state, op, status)
    else:
        await update_interface(
            state,
            event,
            f"⚠️ {t(lang, 'hist.op_not_found')}",
            reply_markup=get_main_keyboard(event.from_user.id, lang=lang),
            parse_mode="Markdown",
        )


# --- Дата ---
@router.callback_query(F.data == "edit_op_field_date")
async def callback_edit_op_date(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    await update_interface(
        state,
        callback,
        t(lang, "hist.edit_op_date_prompt"),
        reply_markup=get_date_keyboard(prefix="editopdate", lang=lang),
        parse_mode="Markdown",
    )
    await state.set_state(EditOpState.edit_date)


async def _apply_edit_op_date(event, state: FSMContext, date_str: str):
    data = await state.get_data()
    op_id = data.get("edit_op_id")
    lang = get_lang(event.from_user.id)
    account_id = get_active_account_id(event.from_user.id)
    update_operation_date(account_id, op_id, date_str)
    await _refresh_edit_op_detail(event, state, t(lang, "hist.updated_date"))


@router.callback_query(F.data.startswith("editopdate_"), EditOpState.edit_date)
async def process_edit_op_date(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    if callback.data == "editopdate_custom":
        await update_interface(
            state,
            callback,
            t(lang, "trades.custom_date_prompt"),
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        await state.set_state(EditOpState.edit_date_custom)
        return
    tz = get_user_tz_offset(callback.from_user.id)
    now = now_local(tz)
    if callback.data == "editopdate_today":
        date_str = fmt_dt(now)
    else:
        date_str = fmt_dt(now - timedelta(days=1))
    await _apply_edit_op_date(callback, state, date_str)


@router.message(EditOpState.edit_date_custom)
async def process_edit_op_date_custom(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    d, error = validate_single_date(message.text, lang=lang)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    date_str = f"{d.strftime('%Y-%m-%d')} 12:00:00"
    await _apply_edit_op_date(message, state, date_str)


# --- Сумма ---
@router.callback_query(F.data == "edit_op_field_amount")
async def callback_edit_op_amount(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    op_id = data.get("edit_op_id")
    lang = get_lang(callback.from_user.id)
    account_id = get_active_account_id(callback.from_user.id)
    op = get_balance_operation(account_id, op_id)
    is_withdraw = bool(op) and op[2] == "Вывод"
    sign_hint = (
        t(lang, "hist.sign_hint_withdraw")
        if is_withdraw
        else t(lang, "hist.sign_hint_deposit")
    )
    await update_interface(
        state,
        callback,
        t(lang, "hist.edit_op_amount_prompt", hint=sign_hint),
        reply_markup=get_back_keyboard(lang=lang),
        parse_mode="Markdown",
    )
    await state.set_state(EditOpState.edit_amount)


@router.message(EditOpState.edit_amount)
async def process_edit_op_amount(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    amount, error = validate_amount(message.text, lang=lang)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    data = await state.get_data()
    op_id = data.get("edit_op_id")
    user_id = message.from_user.id
    account_id = get_active_account_id(user_id)
    op = get_balance_operation(account_id, op_id)
    if not op:
        await update_interface(
            state,
            message,
            f"⚠️ {t(lang, 'hist.op_not_found')}",
            reply_markup=get_main_keyboard(user_id, lang=lang),
            parse_mode="Markdown",
        )
        return
    if op[2] == "Вывод":
        amount = -abs(amount)
    elif op[2] == "Пополнение":
        amount = abs(amount)
    update_operation_amount(account_id, op_id, amount)
    await _refresh_edit_op_detail(message, state, t(lang, "hist.updated_amount"))


# --- Заметка ---
@router.callback_query(F.data == "edit_op_field_note")
async def callback_edit_op_note(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    await update_interface(
        state,
        callback,
        t(lang, "hist.edit_note_prompt"),
        reply_markup=get_back_keyboard(lang=lang),
        parse_mode="Markdown",
    )
    await state.set_state(EditOpState.edit_note)


@router.message(EditOpState.edit_note)
async def process_edit_op_note(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    note, error = validate_note(message.text, lang=lang)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    if note == "-":
        note = ""
    data = await state.get_data()
    op_id = data.get("edit_op_id")
    account_id = get_active_account_id(message.from_user.id)
    update_operation_note(account_id, op_id, note)
    await _refresh_edit_op_detail(message, state, t(lang, "hist.updated_note"))
