from aiogram import F, Router, types
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.fsm.context import FSMContext

from database import (
    change_account_currency,
    get_active_account_id,
    get_daily_report,
    get_user_tz_offset,
    set_daily_report,
    set_user_language,
    set_user_tz_offset,
    user_exists,
)
from handlers.common import update_interface
from keyboards.inline import (
    get_back_keyboard,
    get_currency_keyboard,
    get_language_keyboard,
    get_main_keyboard,
    get_settings_keyboard,
)
from states.fsm import LanguageState, SettingsState
from utils.i18n import LANGUAGES, get_lang, lang_name, t
from utils.validators import validate_tz_offset

router = Router()

# Флаг в FSM-данных: экран выбора языка открыт из настроек,
# а не при первом входе (тогда выбор обрабатывает handlers/start.py).
_LANG_PICKER_FLAG = "settings_lang_picker"


async def _redirect_to_language_picker(event, state: FSMContext) -> bool:
    """Защита шлюза первого входа.

    Если у пользователя ещё нет строки в users (язык не выбран) —
    перенаправляет на двуязычный выбор языка вместо настроек.
    Иначе set_user_tz_offset() / set_daily_report() создали бы строку
    в users БЕЗ языка, и /start перестал бы показывать шлюз.

    Возвращает True, если перенаправление выполнено (обработчик должен вернуться).
    """
    if user_exists(event.from_user.id):
        return False
    await state.update_data({_LANG_PICKER_FLAG: False})
    await state.set_state(LanguageState.waiting_for_language)
    await update_interface(
        state,
        event,
        t("ru", "start.choose_language"),
        reply_markup=get_language_keyboard(hide_back=True),
        parse_mode="Markdown",
    )
    return True


async def render_settings(event, state: FSMContext):
    user_id = event.from_user.id
    lang = get_lang(user_id)
    tz = get_user_tz_offset(user_id)
    report = get_daily_report(user_id)
    text = t(lang, "settings.title")
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_settings_keyboard(tz, report, lang=lang),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "action_settings")
async def callback_settings(callback: types.CallbackQuery, state: FSMContext):
    if await _redirect_to_language_picker(callback, state):
        return
    await render_settings(callback, state)


# --- Язык интерфейса ---
@router.callback_query(F.data == "action_lang")
async def callback_lang(callback: types.CallbackQuery, state: FSMContext):
    if await _redirect_to_language_picker(callback, state):
        return
    lang = get_lang(callback.from_user.id)
    # Помечаем, что выбор языка открыт из настроек: обработчик lang_*
    # вернёт пользователя в настройки, а не в онбординг (как при первом входе).
    await state.update_data({_LANG_PICKER_FLAG: True})
    await update_interface(
        state,
        callback,
        t(lang, "settings.choose_language"),
        reply_markup=get_language_keyboard(lang=lang),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("lang_"))
async def process_lang_choice(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = callback.data.split("_", 1)[1]
    if lang not in LANGUAGES:
        await callback.answer()
        return
    if not await state.get_value(_LANG_PICKER_FLAG, False):
        # Выбор языка при первом входе — обрабатывается в handlers/start.py.
        raise SkipHandler()
    set_user_language(user_id, lang)
    await render_settings(callback, state)
    await state.update_data({_LANG_PICKER_FLAG: False})
    await callback.answer(t(lang, "settings.language_saved", language=lang_name(lang)))


@router.callback_query(F.data == "back_settings")
async def callback_back_settings(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data({_LANG_PICKER_FLAG: False})
    if await _redirect_to_language_picker(callback, state):
        return
    await render_settings(callback, state)


# --- Часовой пояс ---
@router.callback_query(F.data == "action_tz")
async def callback_tz(callback: types.CallbackQuery, state: FSMContext):
    if await _redirect_to_language_picker(callback, state):
        return
    lang = get_lang(callback.from_user.id)
    tz = get_user_tz_offset(callback.from_user.id)
    hours = tz / 60
    label = f"UTC{'+' if hours >= 0 else '-'}{abs(hours):g}"
    text = t(lang, "settings.tz_prompt", tz=label)
    await update_interface(
        state, callback, text, reply_markup=get_back_keyboard(lang=lang), parse_mode="Markdown"
    )
    await state.set_state(SettingsState.waiting_for_tz)


@router.message(SettingsState.waiting_for_tz)
async def process_tz(message: types.Message, state: FSMContext):
    # Защита от записи tz без выбранного языка (создала бы строку users без языка).
    if await _redirect_to_language_picker(message, state):
        return
    lang = get_lang(message.from_user.id)
    minutes, error = validate_tz_offset(message.text)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    set_user_tz_offset(message.from_user.id, minutes)
    hours = minutes / 60
    label = f"UTC{'+' if hours >= 0 else '-'}{abs(hours):g}"
    await update_interface(
        state,
        message,
        t(lang, "settings.tz_set", tz=label),
        reply_markup=get_back_keyboard(lang=lang),
        parse_mode="Markdown",
    )
    await render_settings(message, state)


# --- Ежедневный отчёт ---
@router.callback_query(F.data == "action_toggle_report")
async def callback_toggle_report(callback: types.CallbackQuery, state: FSMContext):
    # Защита от включения отчёта без выбранного языка
    # (set_daily_report создала бы строку users без языка).
    if await _redirect_to_language_picker(callback, state):
        return
    enabled = not get_daily_report(callback.from_user.id)
    set_daily_report(callback.from_user.id, enabled)
    await render_settings(callback, state)


# --- Смена валюты счёта (без сброса) ---
@router.callback_query(F.data == "action_change_currency")
async def callback_change_currency(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    text = t(lang, "settings.change_currency_prompt")
    await update_interface(
        state, callback, text, reply_markup=get_currency_keyboard(lang=lang), parse_mode="Markdown"
    )
    await state.set_state(SettingsState.waiting_for_currency)


@router.callback_query(F.data.startswith("curr_"), SettingsState.waiting_for_currency)
async def process_change_currency(callback: types.CallbackQuery, state: FSMContext):
    curr = callback.data.replace("curr_", "")
    user_id = callback.from_user.id
    lang = get_lang(user_id)
    account_id = get_active_account_id(user_id)
    change_account_currency(account_id, curr)
    await state.clear()
    text = t(lang, "settings.currency_changed", currency=curr)
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_main_keyboard(user_id, lang=lang),
        parse_mode="Markdown",
    )
