import math

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from database import (
    delete_operation,
    get_active_account_id,
    get_operation,
    get_operations_page,
    get_trade,
    get_trades,
    get_user_currency,
    get_user_deposit,
    update_trade_amount,
    update_trade_note,
    update_trade_risk,
)
from handlers.common import update_interface
from keyboards.inline import (
    get_back_keyboard,
    get_del_ops_keyboard,
    get_edit_trade_keyboard,
    get_edit_trades_keyboard,
    get_history_keyboard,
    get_main_keyboard,
)
from states.fsm import TradeState
from utils.validators import validate_amount, validate_note, validate_risk_percent

router = Router()

HIST_PER_PAGE = 6
LIST_PER_PAGE = 8


def _op_line(row, curr: str) -> str:
    op_id, date, op_type, pair, lot, result, amount, balance_after, note, risk_pct, side, commission = row
    if op_type == "Сделка":
        res_emoji = "✅" if result == "Win" else "❌"
        note_str = f" | _{note}_" if note else ""
        risk_str = f" [🛡 {risk_pct}%]" if risk_pct > 0 else ""
        side_str = f" {side}" if side in ("Buy", "Sell") else ""
        return f"`{date}` | 🔹 **{pair}** ({lot} лот{side_str}) {res_emoji} `{amount:+.2f} {curr}`{risk_str}{note_str}\n"
    return f"`{date}` | 🔹 *{op_type}*: `{amount:+.2f} {curr}`\n"


@router.callback_query(F.data == "noop")
async def callback_noop(callback: types.CallbackQuery):
    await callback.answer()


# --- История (с пагинацией) ---
async def render_history(callback: types.CallbackQuery, state: FSMContext, page: int):
    user_id = callback.from_user.id
    account_id = get_active_account_id(user_id)
    curr = get_user_currency(user_id)
    rows, total = get_operations_page(account_id, page, HIST_PER_PAGE)
    pages = max(1, math.ceil(total / HIST_PER_PAGE))
    page = min(page, pages)

    if not rows:
        text = "📜 **История сделок**\n\nУ вас пока нет сохраненных операций."
        await update_interface(
            state,
            callback,
            text,
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )
        return

    text = f"📜 **История операций** (стр. {page}/{pages}):\n\n"
    for row in rows:
        text += _op_line(row, curr)

    has_trades = bool(get_trades(account_id))
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_history_keyboard(page, total, HIST_PER_PAGE, has_trades),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "action_history")
async def callback_history(callback: types.CallbackQuery, state: FSMContext):
    await render_history(callback, state, 1)


@router.callback_query(F.data.startswith("hist_page_"))
async def callback_history_page(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.replace("hist_page_", ""))
    await render_history(callback, state, page)


# --- Удаление любой операции ---
async def render_del_list(callback: types.CallbackQuery, state: FSMContext, page: int):
    user_id = callback.from_user.id
    account_id = get_active_account_id(user_id)
    rows, total = get_operations_page(account_id, page, LIST_PER_PAGE)
    if not rows:
        await callback.answer("Операций нет.", show_alert=True)
        await render_history(callback, state, 1)
        return
    text = f"🗑 **Удаление операции** (стр. {page}):\n\nВыберите операцию для удаления:"
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_del_ops_keyboard(rows, page, total, LIST_PER_PAGE),
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
    account_id = get_active_account_id(user_id)
    op = get_operation(account_id, op_id)
    if not op:
        await callback.answer("Операция не найдена.", show_alert=True)
        return

    op_id, date, op_type, pair, lot, result, amount, balance_after, note, risk_pct, side, commission = op
    curr = get_user_currency(user_id)
    await state.update_data(delete_op_id=op_id)

    text = "⚠️ **Подтвердите удаление операции:**\n\n"
    if op_type == "Сделка":
        text += (
            f"📅 Дата: `{date}`\n"
            f"🔹 Пара: `{pair}`\n🔹 Лот: `{lot}`\n"
            f"🔹 Исход: `{'Плюс' if result == 'Win' else 'Минус'}`\n"
            f"🔹 Профит / Убыток: `{amount:+.2f} {curr}`\n"
        )
    else:
        text += f"📅 Дата: `{date}`\n🔹 Операция: *{op_type}*\n🔹 Сумма: `{amount:+.2f} {curr}`\n"
    if note:
        text += f"📝 Заметка: _{note}_\n"
    text += "\n*Баланс депозита будет пересчитан автоматически.*"

    keyboard = [
        [
            types.InlineKeyboardButton(
                text="🗑 Да, удалить", callback_data="confirm_del_op"
            )
        ],
        [
            types.InlineKeyboardButton(
                text="◀️ Назад к списку", callback_data="del_op_menu"
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
    if not op_id:
        await callback.answer("Операция уже удалена.", show_alert=True)
        return

    user_id = callback.from_user.id
    account_id = get_active_account_id(user_id)
    success = delete_operation(account_id, op_id)
    curr = get_user_currency(user_id)
    await state.clear()

    if success:
        new_deposit = get_user_deposit(user_id)
        text = f"🗑 **Операция успешно удалена!**\n\n💰 Пересчитанный баланс депозита: **{new_deposit:.2f} {curr}**"
    else:
        text = "⚠️ Не удалось удалить операцию (стартовый депозит удалить нельзя)."

    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_main_keyboard(user_id),
        parse_mode="Markdown",
    )


# --- Редактирование сделки ---
async def render_edit_list(callback: types.CallbackQuery, state: FSMContext, page: int):
    user_id = callback.from_user.id
    account_id = get_active_account_id(user_id)
    rows = get_trades(account_id)
    total = len(rows)
    if total == 0:
        await callback.answer("Сделок для редактирования нет.", show_alert=True)
        await render_history(callback, state, 1)
        return
    pages = max(1, math.ceil(total / LIST_PER_PAGE))
    page = min(page, pages)
    start = (page - 1) * LIST_PER_PAGE
    page_rows = rows[start : start + LIST_PER_PAGE]
    text = f"✏️ **Выберите сделку для редактирования** (стр. {page}/{pages}):"
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_edit_trades_keyboard(page_rows, page, total, LIST_PER_PAGE),
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
    account_id = get_active_account_id(user_id)
    trade = get_trade(account_id, trade_id)
    if not trade:
        await callback.answer("Сделка не найдена.", show_alert=True)
        return
    await state.update_data(edit_trade_id=trade_id)
    await render_edit_detail(callback, state, trade)


async def render_edit_detail(event, state: FSMContext, trade, status: str = ""):
    trade_id, date, pair, lot, side, result, amount, note, risk_pct = trade
    curr = get_user_currency(event.from_user.id)
    side_str = f" {side}" if side in ("Buy", "Sell") else ""
    note_str = f"📝 Заметка: _{note}_\n" if note else ""
    risk_str = f"🛡 Риск: `{risk_pct}%`\n" if risk_pct > 0 else ""
    status_str = f"{status}\n\n" if status else ""
    text = (
        f"{status_str}✏️ **Редактирование сделки**\n\n"
        f"📅 Дата: `{date}`\n"
        f"🔹 Пара: `{pair}`\n🔹 Лот: `{lot}`{side_str}\n"
        f"🔹 Исход: `{'Плюс' if result == 'Win' else 'Минус'}`\n"
        f"🔹 Профит / Убыток: `{amount:+.2f} {curr}`\n"
        f"{risk_str}{note_str}"
    )
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_edit_trade_keyboard(trade_id),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "edit_field_amount")
async def callback_edit_amount(callback: types.CallbackQuery, state: FSMContext):
    text = "💰 Введите новую **сумму/исход** (число со знаком, например `50` или `-20`):"
    await update_interface(
        state, callback, text, reply_markup=get_back_keyboard(), parse_mode="Markdown"
    )
    await state.set_state(TradeState.edit_amount)


@router.callback_query(F.data == "edit_field_note")
async def callback_edit_note(callback: types.CallbackQuery, state: FSMContext):
    text = "✍️ Введите новую **заметку** (или `-` чтобы очистить):"
    await update_interface(
        state, callback, text, reply_markup=get_back_keyboard(), parse_mode="Markdown"
    )
    await state.set_state(TradeState.edit_note)


@router.callback_query(F.data == "edit_field_risk")
async def callback_edit_risk(callback: types.CallbackQuery, state: FSMContext):
    text = "🛡 Введите новый **риск в %** (например `1` или `1.5`, или `0` чтобы убрать):"
    await update_interface(
        state, callback, text, reply_markup=get_back_keyboard(), parse_mode="Markdown"
    )
    await state.set_state(TradeState.edit_risk)


async def _refresh_edit_detail(event, state: FSMContext, message_ok: str):
    data = await state.get_data()
    trade_id = data.get("edit_trade_id")
    user_id = event.from_user.id
    account_id = get_active_account_id(user_id)
    trade = get_trade(account_id, trade_id)
    if trade:
        await render_edit_detail(event, state, trade, status=message_ok)
    else:
        await update_interface(
            state,
            event,
            "⚠️ Сделка не найдена.",
            reply_markup=get_main_keyboard(user_id),
            parse_mode="Markdown",
        )


@router.message(TradeState.edit_amount)
async def process_edit_amount(message: types.Message, state: FSMContext):
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
    data = await state.get_data()
    trade_id = data.get("edit_trade_id")
    user_id = message.from_user.id
    account_id = get_active_account_id(user_id)
    update_trade_amount(account_id, trade_id, amount)
    await _refresh_edit_detail(message, state, "✅ Сумма обновлена")


@router.message(TradeState.edit_note)
async def process_edit_note(message: types.Message, state: FSMContext):
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
    if note == "-":
        note = ""
    data = await state.get_data()
    trade_id = data.get("edit_trade_id")
    user_id = message.from_user.id
    account_id = get_active_account_id(user_id)
    update_trade_note(account_id, trade_id, note)
    await _refresh_edit_detail(message, state, "✅ Заметка обновлена")


@router.message(TradeState.edit_risk)
async def process_edit_risk(message: types.Message, state: FSMContext):
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
    data = await state.get_data()
    trade_id = data.get("edit_trade_id")
    user_id = message.from_user.id
    account_id = get_active_account_id(user_id)
    update_trade_risk(account_id, trade_id, risk)
    await _refresh_edit_detail(message, state, "✅ Риск обновлён")
