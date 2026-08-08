from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

import database
from database import (
    delete_trade_by_id,
    get_last_trade,
    get_recent_operations,
    get_user_currency,
    get_user_deposit,
)
from handlers.common import update_interface
from keyboards.inline import get_back_keyboard, get_history_keyboard, get_main_keyboard

router = Router()


# --- История и удаление сделок ---
@router.callback_query(F.data == "action_history")
async def callback_history(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    operations = get_recent_operations(user_id, limit=10)
    curr = get_user_currency(user_id)

    if not operations:
        text = "📜 **История сделок**\n\nУ вас пока нет сохраненных операций."
        await update_interface(
            state,
            callback,
            text,
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )
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
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_history_keyboard(has_trades),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "action_delete_last")
async def callback_delete_last(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    last_trade = get_last_trade(user_id)
    curr = get_user_currency(user_id)

    if not last_trade:
        await callback.answer("⚠️ Нет совершенных сделок для удаления!", show_alert=True)
        return

    trade_id, date, pair, lot, result, amount, balance_after, note, risk_pct = (
        last_trade
    )

    if not database.is_last_operation(user_id, trade_id):
        await callback.answer(
            "❌ Нельзя удалить эту сделку!\n"
            "После неё были выполнены пополнения или выводы. "
            "Удаление нарушит историю баланса.",
            show_alert=True,
        )

        await callback_history(callback, state)
        return

    await state.update_data(delete_trade_id=trade_id)

    note_str = f"🔹 Заметка: _{note}_\n" if note else ""
    risk_str = f"🔹 Риск: `{risk_pct}%`\n" if risk_pct > 0 else ""
    keyboard = [
        [
            types.InlineKeyboardButton(
                text="🗑 Да, удалить эту сделку", callback_data="confirm_delete_trade"
            )
        ],
        [
            types.InlineKeyboardButton(
                text="◀️ Назад к истории", callback_data="action_history"
            )
        ],
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
    await update_interface(
        state,
        callback,
        text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "confirm_delete_trade")
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

    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_main_keyboard(user_id),
        parse_mode="Markdown",
    )
