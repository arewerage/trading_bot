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
from utils.validators import validate_account_name, validate_deposit

router = Router()


async def render_accounts(event, state: FSMContext):
    user_id = event.from_user.id
    ensure_default_account(user_id)
    active = get_active_account(user_id)
    active_id = active[0] if active else 0
    text = "💼 **Счета**\n\nАктивный счёт отмечен ▶️. Нажмите на счёт, чтобы переключиться:"
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_accounts_keyboard(user_id, active_id),
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
    text = "➕ Введите **название нового счёта** (например, `Демо`):"
    await update_interface(
        state, callback, text, reply_markup=get_back_keyboard(), parse_mode="Markdown"
    )
    await state.set_state(AccountState.waiting_for_new_name)


@router.message(AccountState.waiting_for_new_name)
async def process_acc_new_name(message: types.Message, state: FSMContext):
    name, error = validate_account_name(message.text)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )
        return
    await state.update_data(new_account_name=name)
    text = f"Название: **{name}**\n\nВыберите **валюту счёта**:"
    await update_interface(
        state, message, text, reply_markup=get_currency_keyboard(), parse_mode="Markdown"
    )
    await state.set_state(AccountState.waiting_for_currency)


@router.callback_query(F.data.startswith("curr_"), AccountState.waiting_for_currency)
async def process_acc_currency(callback: types.CallbackQuery, state: FSMContext):
    curr = callback.data.replace("curr_", "")
    await state.update_data(new_account_currency=curr)
    text = f"Валюта: **{curr}**\n\nВведите **стартовый депозит** счёта (например, `1000`):"
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(AccountState.waiting_for_deposit)


@router.message(AccountState.waiting_for_deposit)
async def process_acc_deposit(message: types.Message, state: FSMContext):
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
    name = data["new_account_name"]
    curr = data["new_account_currency"]
    user_id = message.from_user.id
    create_account(user_id, name, curr, amount)
    await state.clear()
    text = f"✅ **Счёт «{name}» создан!**\n💰 Стартовый депозит: **{amount:.2f} {curr}**"
    await update_interface(
        state,
        message,
        text,
        reply_markup=get_main_keyboard(user_id),
        parse_mode="Markdown",
    )


# --- Переименование счёта ---
@router.callback_query(F.data == "acc_rename_menu")
async def callback_acc_rename_menu(callback: types.CallbackQuery, state: FSMContext):
    text = "✏️ Выберите счёт для переименования:"
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_account_select_keyboard(callback.from_user.id, "acc_ren"),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("acc_ren_"))
async def callback_acc_rename(callback: types.CallbackQuery, state: FSMContext):
    acc_id = int(callback.data.replace("acc_ren_", ""))
    await state.update_data(rename_account_id=acc_id)
    text = "Введите **новое название** счёта:"
    await update_interface(
        state, callback, text, reply_markup=get_back_keyboard(), parse_mode="Markdown"
    )
    await state.set_state(AccountState.waiting_for_rename)


@router.message(AccountState.waiting_for_rename)
async def process_acc_rename(message: types.Message, state: FSMContext):
    name, error = validate_account_name(message.text)
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
    acc_id = data.get("rename_account_id")
    rename_account(acc_id, name)
    await state.clear()
    await render_accounts(message, state)


# --- Удаление счёта ---
@router.callback_query(F.data == "acc_delete_menu")
async def callback_acc_delete_menu(callback: types.CallbackQuery, state: FSMContext):
    if len(get_accounts(callback.from_user.id)) <= 1:
        await callback.answer("Нельзя удалить единственный счёт.", show_alert=True)
        return
    text = "🗑 Выберите счёт для удаления:"
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_account_select_keyboard(callback.from_user.id, "acc_del"),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("acc_del_"))
async def callback_acc_delete(callback: types.CallbackQuery, state: FSMContext):
    acc_id = int(callback.data.replace("acc_del_", ""))
    acc = get_account(acc_id)
    if not acc:
        await callback.answer("Счёт не найден.", show_alert=True)
        return
    await state.update_data(delete_account_id=acc_id)
    _, _, name, deposit, currency = acc
    text = (
        f"⚠️ **Удалить счёт «{name}»?**\n\n"
        f"💰 Депозит: **{deposit:.2f} {currency}**\n"
        "*Все операции счёта будут удалены безвозвратно.*"
    )
    keyboard = [
        [
            types.InlineKeyboardButton(
                text="🗑 Да, удалить", callback_data="confirm_del_acc"
            )
        ],
        [
            types.InlineKeyboardButton(
                text="◀️ К списку счетов", callback_data="acc_delete_menu"
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
    data = await state.get_data()
    acc_id = data.get("delete_account_id")
    if not acc_id:
        await callback.answer("Счёт уже удалён.", show_alert=True)
        return
    success = delete_account(callback.from_user.id, acc_id)
    await state.clear()
    if success:
        await render_accounts(callback, state)
    else:
        await callback.answer("Не удалось удалить счёт.", show_alert=True)
