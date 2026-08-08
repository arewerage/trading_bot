from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from database import (
    ensure_default_account,
    get_active_account_id,
    get_user_currency,
    get_user_deposit,
    log_balance_operation,
    reset_user_data,
    set_account_deposit_and_currency,
)
from handlers.common import update_interface
from keyboards.inline import get_back_keyboard, get_currency_keyboard, get_main_keyboard
from states.fsm import DepositState
from utils.validators import validate_deposit, validate_note, validate_withdrawal

router = Router()


# --- Онбординг: валюта и стартовый депозит ---
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
    account_id = data.get("account_id")
    if not account_id:
        account_id = ensure_default_account(user_id)[0]

    set_account_deposit_and_currency(user_id, account_id, amount, curr)
    await update_interface(
        state,
        message,
        f"✅ Стартовый депозит успешно установлен: **{amount:.2f} {curr}**",
        reply_markup=get_main_keyboard(user_id),
        parse_mode="Markdown",
    )
    await state.clear()


# --- Пополнение депозита ---
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
    await state.update_data(top_up_amount=amount)
    keyboard = [
        [
            types.InlineKeyboardButton(
                text="⏩ Пропустить заметку", callback_data="skip_top_up_note"
            )
        ],
        [types.InlineKeyboardButton(text="◀️ Отмена", callback_data="main_menu")],
    ]
    text = "✍️ Введите **заметку к пополнению** (опционально):"
    await update_interface(
        state,
        message,
        text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown",
    )
    await state.set_state(DepositState.waiting_for_top_up_note)


@router.message(DepositState.waiting_for_top_up_note)
async def process_top_up_note(message: types.Message, state: FSMContext):
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
    await save_top_up(message, state, note)


@router.callback_query(
    F.data == "skip_top_up_note", DepositState.waiting_for_top_up_note
)
async def process_top_up_note_skip(callback: types.CallbackQuery, state: FSMContext):
    await save_top_up(callback, state, "")


async def save_top_up(event, state: FSMContext, note: str):
    data = await state.get_data()
    amount = data["top_up_amount"]
    user_id = event.from_user.id
    account_id = get_active_account_id(user_id)
    curr = get_user_currency(user_id)

    log_balance_operation(user_id, account_id, "Пополнение", amount, note)
    await state.clear()
    new_deposit = get_user_deposit(user_id)
    note_str = f"\n📝 Заметка: `{note}`" if note else ""
    text = f"✅ Баланс успешно пополнен на **+{amount:.2f} {curr}**{note_str}\n💰 Новый депозит: **{new_deposit:.2f} {curr}**"
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_main_keyboard(user_id),
        parse_mode="Markdown",
    )


# --- Вывод средств ---
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
    except ValueError:
        await update_interface(
            state,
            message,
            "⚠️ Введите числовое значение.",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )
        return
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
    await state.update_data(withdraw_amount=amount)
    keyboard = [
        [
            types.InlineKeyboardButton(
                text="⏩ Пропустить заметку", callback_data="skip_withdraw_note"
            )
        ],
        [types.InlineKeyboardButton(text="◀️ Отмена", callback_data="main_menu")],
    ]
    text = "✍️ Введите **заметку к выводу** (опционально):"
    await update_interface(
        state,
        message,
        text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown",
    )
    await state.set_state(DepositState.waiting_for_withdraw_note)


@router.message(DepositState.waiting_for_withdraw_note)
async def process_withdraw_note(message: types.Message, state: FSMContext):
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
    await save_withdraw(message, state, note)


@router.callback_query(
    F.data == "skip_withdraw_note", DepositState.waiting_for_withdraw_note
)
async def process_withdraw_note_skip(callback: types.CallbackQuery, state: FSMContext):
    await save_withdraw(callback, state, "")


async def save_withdraw(event, state: FSMContext, note: str):
    data = await state.get_data()
    amount = data["withdraw_amount"]
    user_id = event.from_user.id
    account_id = get_active_account_id(user_id)
    curr = get_user_currency(user_id)

    log_balance_operation(user_id, account_id, "Вывод", -amount, note)
    await state.clear()
    new_deposit = get_user_deposit(user_id)
    note_str = f"\n📝 Заметка: `{note}`" if note else ""
    text = f"✅ Успешно выведено: **-{amount:.2f} {curr}**{note_str}\n💰 Новый депозит: **{new_deposit:.2f} {curr}**"
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_main_keyboard(user_id),
        parse_mode="Markdown",
    )


# --- Сброс данных ---
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
    acc = ensure_default_account(callback.from_user.id)
    await state.update_data(account_id=acc[0])
    text = "🔄 Данные успешно сброшены.\n\nВыберите **валюту счета**:"
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_currency_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(DepositState.waiting_for_currency)
