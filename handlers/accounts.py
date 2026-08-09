from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from database import (
    create_account,
    delete_account,
    ensure_default_account,
    get_account,
    get_accounts,
    get_active_account,
    rename_account,
    set_active_account,
)
from handlers.common import update_interface
from keyboards.inline import (
    get_account_select_keyboard,
    get_accounts_keyboard,
    get_back_keyboard,
    get_currency_keyboard,
    get_main_keyboard,
)
from states.fsm import AccountState
from utils.i18n import get_lang, t
from utils.validators import validate_account_name, validate_deposit

router = Router()


async def render_accounts(event, state: FSMContext):
    user_id = event.from_user.id
    lang = get_lang(user_id)
    ensure_default_account(user_id)
    active = get_active_account(user_id)
    active_id = active[0] if active else 0
    text = t(lang, "accounts.title")
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_accounts_keyboard(user_id, active_id, lang=lang),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "action_accounts")
async def callback_accounts(callback: types.CallbackQuery, state: FSMContext):
    await render_accounts(callback, state)


@router.callback_query(F.data.startswith("switch_acc_"))
async def callback_switch_account(callback: types.CallbackQuery, state: FSMContext):
    acc_id = int(callback.data.replace("switch_acc_", ""))
    set_active_account(callback.from_user.id, acc_id)
    await render_accounts(callback, state)


# --- Создание счёта ---
@router.callback_query(F.data == "acc_create")
async def callback_acc_create(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    text = t(lang, "accounts.create_prompt")
    await update_interface(
        state, callback, text, reply_markup=get_back_keyboard(lang=lang), parse_mode="Markdown"
    )
    await state.set_state(AccountState.waiting_for_new_name)


@router.message(AccountState.waiting_for_new_name)
async def process_acc_new_name(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    name, error = validate_account_name(message.text, lang)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    await state.update_data(new_account_name=name)
    text = t(lang, "accounts.name_set", name=name)
    await update_interface(
        state, message, text, reply_markup=get_currency_keyboard(lang=lang), parse_mode="Markdown"
    )
    await state.set_state(AccountState.waiting_for_currency)


@router.callback_query(F.data.startswith("curr_"), AccountState.waiting_for_currency)
async def process_acc_currency(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    curr = callback.data.replace("curr_", "")
    await state.update_data(new_account_currency=curr)
    text = t(lang, "accounts.currency_set", currency=curr)
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_back_keyboard(lang=lang),
        parse_mode="Markdown",
    )
    await state.set_state(AccountState.waiting_for_deposit)


@router.message(AccountState.waiting_for_deposit)
async def process_acc_deposit(message: types.Message, state: FSMContext):
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
    name = data["new_account_name"]
    curr = data["new_account_currency"]
    create_account(user_id, name, curr, amount)
    await state.clear()
    text = t(lang, "accounts.created", name=name, amount=f"{amount:.2f}", currency=curr)
    await update_interface(
        state,
        message,
        text,
        reply_markup=get_main_keyboard(user_id, lang=lang),
        parse_mode="Markdown",
    )


# --- Переименование счёта ---
@router.callback_query(F.data == "acc_rename_menu")
async def callback_acc_rename_menu(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    text = t(lang, "accounts.rename_select")
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_account_select_keyboard(callback.from_user.id, "acc_ren", lang=lang),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("acc_ren_"))
async def callback_acc_rename(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    acc_id = int(callback.data.replace("acc_ren_", ""))
    await state.update_data(rename_account_id=acc_id)
    text = t(lang, "accounts.rename_prompt")
    await update_interface(
        state, callback, text, reply_markup=get_back_keyboard(lang=lang), parse_mode="Markdown"
    )
    await state.set_state(AccountState.waiting_for_rename)


@router.message(AccountState.waiting_for_rename)
async def process_acc_rename(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    name, error = validate_account_name(message.text, lang)
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
    acc_id = data.get("rename_account_id")
    rename_account(acc_id, name)
    await state.clear()
    await render_accounts(message, state)


# --- Удаление счёта ---
@router.callback_query(F.data == "acc_delete_menu")
async def callback_acc_delete_menu(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    if len(get_accounts(callback.from_user.id)) <= 1:
        await callback.answer(t(lang, "accounts.cannot_delete_only"), show_alert=True)
        return
    text = t(lang, "accounts.delete_select")
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_account_select_keyboard(callback.from_user.id, "acc_del", lang=lang),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("acc_del_"))
async def callback_acc_delete(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    acc_id = int(callback.data.replace("acc_del_", ""))
    acc = get_account(acc_id)
    if not acc:
        await callback.answer(t(lang, "accounts.not_found"), show_alert=True)
        return
    await state.update_data(delete_account_id=acc_id)
    _, _, name, deposit, currency = acc
    text = t(
        lang,
        "accounts.delete_confirm",
        name=name,
        deposit=f"{deposit:.2f}",
        currency=currency,
    )
    keyboard = [
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.yes_delete"), callback_data="confirm_del_acc"
            )
        ],
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.back_accounts_list"), callback_data="acc_delete_menu"
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


@router.callback_query(F.data == "confirm_del_acc")
async def callback_confirm_del_acc(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    data = await state.get_data()
    acc_id = data.get("delete_account_id")
    if not acc_id:
        await callback.answer(t(lang, "accounts.already_deleted"), show_alert=True)
        return
    success = delete_account(callback.from_user.id, acc_id)
    await state.clear()
    if success:
        await render_accounts(callback, state)
    else:
        await callback.answer(t(lang, "accounts.delete_failed"), show_alert=True)
