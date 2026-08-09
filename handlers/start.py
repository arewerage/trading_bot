from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from database import ensure_default_account, set_user_language, user_exists
from handlers.common import update_interface
from keyboards.inline import (
    get_analytics_keyboard,
    get_currency_keyboard,
    get_data_keyboard,
    get_language_keyboard,
    get_main_keyboard,
)
from states.fsm import DepositState, LanguageState
from utils.i18n import LANGUAGES, get_lang, t

router = Router()


async def _start_onboarding(event, state: FSMContext, user_id: int, lang: str):
    """Общая часть онбординга после выбора языка.

    Вызывается и show_home() для существующих пользователей,
    и обработчиком выбора языка при первом входе.
    """
    account = ensure_default_account(user_id)
    account_id, name, deposit, curr = account

    if deposit <= 0:
        await state.update_data(account_id=account_id)
        text = t(lang, "start.welcome_currency")
        await update_interface(
            state,
            event,
            text,
            reply_markup=get_currency_keyboard(lang),
            parse_mode="Markdown",
        )
        await state.set_state(DepositState.waiting_for_currency)
    else:
        # Сбрасываем FSM: состояние waiting_for_language (шлюз первого входа)
        # не должно оставаться висеть после отрисовки главного меню.
        # Очистка до update_interface, чтобы bot_msg_id сохранился.
        await state.clear()
        text = t(
            lang,
            "start.main_menu",
            name=name,
            deposit=f"{deposit:.2f}",
            currency=curr,
        )
        await update_interface(
            state,
            event,
            text,
            reply_markup=get_main_keyboard(user_id, lang),
            parse_mode="Markdown",
        )


async def show_home(event, state: FSMContext):
    user_id = event.from_user.id

    # Первый вход: язык ещё не выбран — показываем двуязычное приглашение.
    # hide_back=True: новый пользователь не может выйти из выбора языка
    # через «Назад в настройки» (иначе строка users создалась бы без языка).
    if not user_exists(user_id):
        await state.set_state(LanguageState.waiting_for_language)
        await update_interface(
            state,
            event,
            t("ru", "start.choose_language"),
            reply_markup=get_language_keyboard(hide_back=True),
            parse_mode="Markdown",
        )
        return

    lang = get_lang(user_id)
    await _start_onboarding(event, state, user_id, lang)


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await show_home(message, state)


@router.callback_query(F.data.startswith("lang_"))
async def process_language_choice(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = callback.data.split("_", 1)[1]
    if lang not in LANGUAGES:
        await callback.answer()
        return
    set_user_language(user_id, lang)
    await _start_onboarding(callback, state, user_id, lang)


@router.callback_query(F.data == "main_menu")
async def process_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await show_home(callback, state)


@router.callback_query(F.data == "action_analytics")
async def process_analytics(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    await update_interface(
        state,
        callback,
        t(lang, "start.analytics"),
        reply_markup=get_analytics_keyboard(lang),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "action_data")
async def process_data(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    await update_interface(
        state,
        callback,
        t(lang, "start.data"),
        reply_markup=get_data_keyboard(callback.from_user.id, lang),
        parse_mode="Markdown",
    )
