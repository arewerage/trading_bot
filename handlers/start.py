from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from database import ensure_default_account, get_active_account
from handlers.common import update_interface
from keyboards.inline import (
    get_analytics_keyboard,
    get_currency_keyboard,
    get_data_keyboard,
    get_main_keyboard,
)
from states.fsm import DepositState

router = Router()


async def show_home(event, state: FSMContext):
    user_id = event.from_user.id
    account = ensure_default_account(user_id)
    account_id, name, deposit, curr = account

    if deposit <= 0:
        await state.update_data(account_id=account_id)
        text = "🤖 **Бот для торговой статистики**\n\nДобро пожаловать! Сначала выберите **валюту счета**:"
        await update_interface(
            state,
            event,
            text,
            reply_markup=get_currency_keyboard(),
            parse_mode="Markdown",
        )
        await state.set_state(DepositState.waiting_for_currency)
    else:
        text = (
            f"🤖 **Главное меню**\n\n"
            f"💼 Счёт: **{name}**\n"
            f"Текущий депозит: **{deposit:.2f} {curr}**\n"
            f"Выберите действие:"
        )
        await update_interface(
            state,
            event,
            text,
            reply_markup=get_main_keyboard(user_id),
            parse_mode="Markdown",
        )


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await show_home(message, state)


@router.callback_query(F.data == "main_menu")
async def process_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await show_home(callback, state)


@router.callback_query(F.data == "action_analytics")
async def process_analytics(callback: types.CallbackQuery, state: FSMContext):
    await update_interface(
        state,
        callback,
        "📊 **Аналитика**\n\nСтатистика, график и выгрузка по текущему счёту:",
        reply_markup=get_analytics_keyboard(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "action_data")
async def process_data(callback: types.CallbackQuery, state: FSMContext):
    await update_interface(
        state,
        callback,
        "🗂 **Данные**\n\nИмпорт, резервная копия и обслуживание:",
        reply_markup=get_data_keyboard(callback.from_user.id),
        parse_mode="Markdown",
    )
