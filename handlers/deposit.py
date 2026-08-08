from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from database import (
    get_user_currency,
    get_user_deposit,
    log_balance_operation,
    reset_user_data,
    set_user_deposit_and_currency,
)
from handlers.common import update_interface
from keyboards.inline import get_back_keyboard, get_currency_keyboard, get_main_keyboard
from states.fsm import DepositState
from utils.validators import validate_deposit, validate_withdrawal

router = Router()


# --- Депозит и валюта ---
@router.callback_query(F.data.startswith("curr_"), DepositState.waiting_for_currency)
async def process_currency_choice(callback: types.CallbackQuery, state: FSMContext):
    curr = callback.data.replace("curr_", "")
    await state.update_data(currency=curr)
    text = f"Выбрана валюта: **{curr}**\n\nВведите сумму вашего **стартового депозита** цифрами (например, `1000`):"
    await update_interface(
        state, callback, text, reply_markup=get_back_keyboard(), parse_mode="Markdown"
    )
    await state.set_state(DepositState.waiting_for_deposit)


@router.message(DepositState.waiting_for_deposit)
async def process_deposit(message: types.Message, state: FSMContext):
    amount, error = validate_deposit(message.text)
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
    curr = data.get("currency", "USD")
    user_id = message.from_user.id

    set_user_deposit_and_currency(user_id, amount, curr, op_type="Старт", amount=amount)
    await update_interface(
        state,
        message,
        f"✅ Стартовый депозит успешно установлен: **{amount:.2f} {curr}**",
        reply_markup=get_main_keyboard(user_id),
        parse_mode="Markdown",
    )
    await state.clear()


@router.callback_query(F.data == "action_top_up")
async def callback_top_up(callback: types.CallbackQuery, state: FSMContext):
    curr = get_user_currency(callback.from_user.id)
    await update_interface(
        state,
        callback,
        f"🟢 **Пополнение депозита**\n\nВведите сумму в {curr} (например, `500`):",
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(DepositState.waiting_for_top_up)


@router.message(DepositState.waiting_for_top_up)
async def process_top_up(message: types.Message, state: FSMContext):
    amount, error = validate_deposit(message.text)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )
        return
    user_id = message.from_user.id
    curr = get_user_currency(user_id)
    new_deposit = get_user_deposit(user_id) + amount
    log_balance_operation(user_id, "Пополнение", amount, new_deposit)
    await update_interface(
        state,
        message,
        f"✅ Баланс успешно пополнен на **+{amount:.2f} {curr}**\n💰 Новый депозит: **{new_deposit:.2f} {curr}**",
        reply_markup=get_main_keyboard(user_id),
        parse_mode="Markdown",
    )
    await state.clear()


@router.callback_query(F.data == "action_withdraw")
async def callback_withdraw(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    deposit = get_user_deposit(user_id)
    curr = get_user_currency(user_id)
    await update_interface(
        state,
        callback,
        f"🔴 **Вывод средств**\n\nТекущий баланс: **{deposit:.2f} {curr}**\nВведите сумму:",
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(DepositState.waiting_for_withdraw)


@router.message(DepositState.waiting_for_withdraw)
async def process_withdraw(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        user_id = message.from_user.id
        current_deposit = get_user_deposit(user_id)
        error = validate_withdrawal(amount, current_deposit)
        if error:
            await update_interface(
                state,
                message,
                f"⚠️ {error}",
                reply_markup=get_back_keyboard(),
                parse_mode="Markdown",
            )
            return
        curr = get_user_currency(user_id)
        new_deposit = current_deposit - amount
        log_balance_operation(user_id, "Вывод", -amount, new_deposit)
        await update_interface(
            state,
            message,
            f"✅ Успешно выведено: **-{amount:.2f} {curr}**\n💰 Новый депозит: **{new_deposit:.2f} {curr}**",
            reply_markup=get_main_keyboard(user_id),
            parse_mode="Markdown",
        )
        await state.clear()
    except ValueError:
        await update_interface(
            state,
            message,
            "⚠️ Введите числовое значение.",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )


@router.callback_query(F.data == "action_reset")
async def callback_reset_confirm(callback: types.CallbackQuery, state: FSMContext):
    keyboard = [
        [
            types.InlineKeyboardButton(
                text="⚠️ Да, удалить всё", callback_data="reset_yes"
            )
        ],
        [types.InlineKeyboardButton(text="◀️ Отмена", callback_data="main_menu")],
    ]
    await update_interface(
        state,
        callback,
        "🚨 **Внимание!** Вся история операций будет удалена. Продолжить?",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "reset_yes")
async def callback_reset_execute(callback: types.CallbackQuery, state: FSMContext):
    reset_user_data(callback.from_user.id)
    text = "🔄 Данные успешно сброшены.\n\nВыберите **валюту счета**:"
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_currency_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(DepositState.waiting_for_currency)
