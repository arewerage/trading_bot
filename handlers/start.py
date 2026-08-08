from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from database import get_user_currency, get_user_deposit
from handlers.common import update_interface
from keyboards.inline import get_currency_keyboard, get_main_keyboard
from states.fsm import DepositState

router = Router()


# --- Главное меню ---
@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    deposit = get_user_deposit(user_id)
    curr = get_user_currency(user_id)

    if deposit <= 0:
        text = "🤖 **Бот для торговой статистики**\n\nДобро пожаловать! Сначала выберите **валюту счета**:"
        await update_interface(
            state,
            message,
            text,
            reply_markup=get_currency_keyboard(),
            parse_mode="Markdown",
        )
        await state.set_state(DepositState.waiting_for_currency)
    else:
        text = f"🤖 **Главное меню**\n\nТекущий депозит: **{deposit:.2f} {curr}**\nВыберите действие:"
        await update_interface(
            state,
            message,
            text,
            reply_markup=get_main_keyboard(user_id),
            parse_mode="Markdown",
        )


@router.callback_query(F.data == "main_menu")
async def process_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    deposit = get_user_deposit(user_id)
    curr = get_user_currency(user_id)

    if deposit <= 0:
        text = "🤖 **Бот для торговой статистики**\n\nВыберите **валюту счета**:"
        await update_interface(
            state,
            callback,
            text,
            reply_markup=get_currency_keyboard(),
            parse_mode="Markdown",
        )
        await state.set_state(DepositState.waiting_for_currency)
    else:
        text = f"🤖 **Главное меню**\n\nТекущий депозит: **{deposit:.2f} {curr}**\nВыберите действие:"
        await update_interface(
            state,
            callback,
            text,
            reply_markup=get_main_keyboard(user_id),
            parse_mode="Markdown",
        )
