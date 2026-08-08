from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from database import (
    change_account_currency,
    get_active_account_id,
    get_daily_report,
    get_user_tz_offset,
    set_daily_report,
    set_user_tz_offset,
)
from handlers.common import update_interface
from keyboards.inline import (
    get_back_keyboard,
    get_currency_keyboard,
    get_main_keyboard,
    get_settings_keyboard,
)
from states.fsm import SettingsState
from utils.validators import validate_tz_offset

router = Router()


async def render_settings(event, state: FSMContext):
    user_id = event.from_user.id
    tz = get_user_tz_offset(user_id)
    report = get_daily_report(user_id)
    text = "⚙️ **Настройки**\n\nЧасовой пояс используется для статистики «за день», дат сделок и отчётов."
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_settings_keyboard(tz, report),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "action_settings")
async def callback_settings(callback: types.CallbackQuery, state: FSMContext):
    await render_settings(callback, state)


# --- Часовой пояс ---
@router.callback_query(F.data == "action_tz")
async def callback_tz(callback: types.CallbackQuery, state: FSMContext):
    tz = get_user_tz_offset(callback.from_user.id)
    hours = tz / 60
    label = f"UTC{'+' if hours >= 0 else '-'}{abs(hours):g}"
    text = (
        f"🌍 Текущий часовой пояс: **{label}**\n\n"
        "Введите смещение от UTC в часах (например, `+3` для Москвы, `-5` для Нью-Йорка, `5.5` для Индии):"
    )
    await update_interface(
        state, callback, text, reply_markup=get_back_keyboard(), parse_mode="Markdown"
    )
    await state.set_state(SettingsState.waiting_for_tz)


@router.message(SettingsState.waiting_for_tz)
async def process_tz(message: types.Message, state: FSMContext):
    minutes, error = validate_tz_offset(message.text)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )
        return
    set_user_tz_offset(message.from_user.id, minutes)
    hours = minutes / 60
    label = f"UTC{'+' if hours >= 0 else '-'}{abs(hours):g}"
    await update_interface(
        state,
        message,
        f"✅ Часовой пояс установлен: **{label}**",
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown",
    )
    await render_settings(message, state)


# --- Ежедневный отчёт ---
@router.callback_query(F.data == "action_toggle_report")
async def callback_toggle_report(callback: types.CallbackQuery, state: FSMContext):
    enabled = not get_daily_report(callback.from_user.id)
    set_daily_report(callback.from_user.id, enabled)
    await render_settings(callback, state)


# --- Смена валюты счёта (без сброса) ---
@router.callback_query(F.data == "action_change_currency")
async def callback_change_currency(callback: types.CallbackQuery, state: FSMContext):
    text = "💱 Выберите **новую валюту счёта**:\n\n*(сумма депозита не пересчитывается, меняется только обозначение)*"
    await update_interface(
        state, callback, text, reply_markup=get_currency_keyboard(), parse_mode="Markdown"
    )
    await state.set_state(SettingsState.waiting_for_currency)


@router.callback_query(F.data.startswith("curr_"), SettingsState.waiting_for_currency)
async def process_change_currency(callback: types.CallbackQuery, state: FSMContext):
    curr = callback.data.replace("curr_", "")
    user_id = callback.from_user.id
    account_id = get_active_account_id(user_id)
    change_account_currency(account_id, curr)
    await state.clear()
    text = f"✅ Валюта счёта изменена на **{curr}**."
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_main_keyboard(user_id),
        parse_mode="Markdown",
    )
