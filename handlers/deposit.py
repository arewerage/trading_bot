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
from utils.i18n import get_lang, t
from utils.validators import validate_deposit, validate_note, validate_withdrawal

router = Router()


# --- Онбординг: валюта и стартовый депозит ---
@router.callback_query(F.data.startswith("curr_"), DepositState.waiting_for_currency)
async def process_currency_choice(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    curr = callback.data.replace("curr_", "")
    await state.update_data(currency=curr)
    text = t(lang, "deposit.currency_chosen", currency=curr)
    await update_interface(
        state, callback, text, reply_markup=get_back_keyboard(lang=lang), parse_mode="Markdown"
    )
    await state.set_state(DepositState.waiting_for_deposit)


@router.message(DepositState.waiting_for_deposit)
async def process_deposit(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    lang = get_lang(user_id)
    amount, error = validate_deposit(message.text, lang)
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
    curr = data.get("currency", "USD")
    account_id = data.get("account_id")
    if not account_id:
        account_id = ensure_default_account(user_id)[0]

    set_account_deposit_and_currency(user_id, account_id, amount, curr)
    await update_interface(
        state,
        message,
        t(lang, "deposit.set_ok", amount=f"{amount:.2f}", currency=curr),
        reply_markup=get_main_keyboard(user_id, lang=lang),
        parse_mode="Markdown",
    )
    await state.clear()


# --- Пополнение депозита ---
@router.callback_query(F.data == "action_top_up")
async def callback_top_up(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = get_lang(user_id)
    curr = get_user_currency(user_id)
    await update_interface(
        state,
        callback,
        t(lang, "deposit.top_up_prompt", currency=curr),
        reply_markup=get_back_keyboard(lang=lang),
        parse_mode="Markdown",
    )
    await state.set_state(DepositState.waiting_for_top_up)


@router.message(DepositState.waiting_for_top_up)
async def process_top_up(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    amount, error = validate_deposit(message.text, lang)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    await state.update_data(top_up_amount=amount)
    keyboard = [
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.skip_note"), callback_data="skip_top_up_note"
            )
        ],
        [types.InlineKeyboardButton(text=t(lang, "deposit.cancel"), callback_data="main_menu")],
    ]
    text = t(lang, "deposit.top_up_note_prompt")
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
    lang = get_lang(message.from_user.id)
    note, error = validate_note(message.text, lang)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(lang=lang),
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
    lang = get_lang(user_id)
    account_id = get_active_account_id(user_id)
    curr = get_user_currency(user_id)

    log_balance_operation(user_id, account_id, "Пополнение", amount, note)
    await state.clear()
    new_deposit = get_user_deposit(user_id)
    note_str = t(lang, "deposit.note_line", note=note) if note else ""
    text = t(
        lang,
        "deposit.top_up_ok",
        amount=f"{amount:.2f}",
        currency=curr,
        note=note_str,
        balance=f"{new_deposit:.2f}",
    )
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_main_keyboard(user_id, lang=lang),
        parse_mode="Markdown",
    )


# --- Вывод средств ---
@router.callback_query(F.data == "action_withdraw")
async def callback_withdraw(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = get_lang(user_id)
    deposit = get_user_deposit(user_id)
    curr = get_user_currency(user_id)
    await update_interface(
        state,
        callback,
        t(lang, "deposit.withdraw_prompt", balance=f"{deposit:.2f}", currency=curr),
        reply_markup=get_back_keyboard(lang=lang),
        parse_mode="Markdown",
    )
    await state.set_state(DepositState.waiting_for_withdraw)


@router.message(DepositState.waiting_for_withdraw)
async def process_withdraw(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        await update_interface(
            state,
            message,
            t(lang, "deposit.invalid_number"),
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    user_id = message.from_user.id
    current_deposit = get_user_deposit(user_id)
    error = validate_withdrawal(amount, current_deposit, lang)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    await state.update_data(withdraw_amount=amount)
    keyboard = [
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.skip_note"), callback_data="skip_withdraw_note"
            )
        ],
        [types.InlineKeyboardButton(text=t(lang, "deposit.cancel"), callback_data="main_menu")],
    ]
    text = t(lang, "deposit.withdraw_note_prompt")
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
    lang = get_lang(message.from_user.id)
    note, error = validate_note(message.text, lang)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(lang=lang),
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
    lang = get_lang(user_id)
    account_id = get_active_account_id(user_id)
    curr = get_user_currency(user_id)

    log_balance_operation(user_id, account_id, "Вывод", -amount, note)
    await state.clear()
    new_deposit = get_user_deposit(user_id)
    note_str = t(lang, "deposit.note_line", note=note) if note else ""
    text = t(
        lang,
        "deposit.withdraw_ok",
        amount=f"{amount:.2f}",
        currency=curr,
        note=note_str,
        balance=f"{new_deposit:.2f}",
    )
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_main_keyboard(user_id, lang=lang),
        parse_mode="Markdown",
    )


# --- Сброс данных ---
@router.callback_query(F.data == "action_reset")
async def callback_reset_confirm(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    keyboard = [
        [
            types.InlineKeyboardButton(
                text=t(lang, "deposit.reset_yes"), callback_data="reset_yes"
            )
        ],
        [types.InlineKeyboardButton(text=t(lang, "deposit.cancel"), callback_data="main_menu")],
    ]
    await update_interface(
        state,
        callback,
        t(lang, "deposit.reset_confirm"),
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "reset_yes")
async def callback_reset_execute(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = get_lang(user_id)
    reset_user_data(user_id)
    acc = ensure_default_account(user_id)
    await state.update_data(account_id=acc[0])
    text = t(lang, "deposit.reset_ok")
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_currency_keyboard(lang=lang),
        parse_mode="Markdown",
    )
    await state.set_state(DepositState.waiting_for_currency)
