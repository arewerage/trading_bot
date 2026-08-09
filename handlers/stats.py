from datetime import datetime, timedelta

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from database import (
    get_active_account_id,
    get_operations,
    get_user_currency,
    get_user_tz_offset,
    now_local,
)
from handlers.common import update_interface
from keyboards.inline import get_back_keyboard, get_stats_keyboard
from states.fsm import StatsState
from utils.analytics import (
    calculate_advanced_stats,
    calculate_stats_by_pair,
    format_stats_by_pair,
    format_stats_text,
)
from utils.i18n import get_lang, t
from utils.validators import validate_date_range

router = Router()


def _parse_dt(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")


def _day_filter(dt: datetime, now: datetime):
    return dt.date() == now.date()


def _month_filter(dt: datetime, now: datetime):
    return dt.year == now.year and dt.month == now.month


@router.callback_query(F.data == "action_stats")
async def callback_stats_menu(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = get_lang(user_id)
    account_id = get_active_account_id(user_id)
    await update_interface(
        state,
        callback,
        t(lang, "stats.menu"),
        reply_markup=get_stats_keyboard(account_id, lang=lang),
        parse_mode="Markdown",
    )


@router.callback_query(
    F.data.in_({"stats_day", "stats_week", "stats_month", "stats_all"})
)
async def callback_stats_period(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = get_lang(user_id)
    account_id = get_active_account_id(user_id)
    curr = get_user_currency(user_id)
    now = now_local(get_user_tz_offset(user_id))

    if callback.data == "stats_day":
        label = t(lang, "period.label_day")
        f_func = lambda r, _now=now: _day_filter(_parse_dt(r[0]), _now)
        date_str = now.strftime("%d.%m.%Y")
    elif callback.data == "stats_week":
        label = t(lang, "period.label_week")
        start_date = now.date() - timedelta(days=6)
        f_func = lambda r, _start=start_date: _parse_dt(r[0]).date() >= _start
        date_str = f"{start_date.strftime('%d.%m.%Y')} — {now.strftime('%d.%m.%Y')}"
    elif callback.data == "stats_month":
        label = t(lang, "period.label_month")
        f_func = lambda r, _now=now: _month_filter(_parse_dt(r[0]), _now)
        first_day = now.replace(day=1)
        last_day = first_day + timedelta(days=31)
        last_day = last_day.replace(day=1) - timedelta(days=1)
        date_str = (
            f"{first_day.strftime('%d.%m.%Y')} — {last_day.strftime('%d.%m.%Y')}"
        )
    else:
        label = t(lang, "period.label_all")
        f_func = None
        date_str = ""

    stats = calculate_advanced_stats(get_operations(account_id), f_func)
    title = (
        t(lang, "stats.title_period", period=label, date=date_str)
        if date_str
        else t(lang, "stats.title_all")
    )
    text = format_stats_text(stats, curr, title, lang=lang)
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_stats_keyboard(account_id, lang=lang),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("stats_pair_"))
async def callback_stats_pair(callback: types.CallbackQuery, state: FSMContext):
    pair = callback.data.replace("stats_pair_", "")
    user_id = callback.from_user.id
    lang = get_lang(user_id)
    account_id = get_active_account_id(user_id)
    curr = get_user_currency(user_id)
    stats = calculate_advanced_stats(
        get_operations(account_id), lambda r: r[2] == pair
    )
    text = format_stats_text(
        stats, curr, t(lang, "stats.title_pair", pair=pair), lang=lang
    )
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_stats_keyboard(account_id, lang=lang),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "stats_pairs")
async def callback_stats_pairs(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = get_lang(user_id)
    account_id = get_active_account_id(user_id)
    curr = get_user_currency(user_id)
    rows = calculate_stats_by_pair(get_operations(account_id))
    text = format_stats_by_pair(rows, curr, t(lang, "stats.title_by_pair"), lang=lang)
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_stats_keyboard(account_id, lang=lang),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "stats_custom")
async def callback_stats_custom(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = get_lang(user_id)
    await update_interface(
        state,
        callback,
        t(lang, "stats.custom_prompt"),
        reply_markup=get_back_keyboard(lang=lang),
        parse_mode="Markdown",
    )
    await state.set_state(StatsState.waiting_for_custom_period)


@router.message(StatsState.waiting_for_custom_period)
async def process_custom_period(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    parts = message.text.strip().split("-")
    if len(parts) != 2:
        await update_interface(
            state,
            message,
            t(lang, "stats.format_error"),
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    start_str, end_str = parts[0].strip(), parts[1].strip()
    result, error = validate_date_range(start_str, end_str, lang=lang)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    start_date, end_date = result
    user_id = message.from_user.id
    account_id = get_active_account_id(user_id)
    curr = get_user_currency(user_id)

    def custom_filter(r, _start=start_date, _end=end_date):
        return _start <= _parse_dt(r[0]).date() <= _end

    stats = calculate_advanced_stats(get_operations(account_id), custom_filter)
    text = format_stats_text(
        stats,
        curr,
        f"{start_date.strftime('%d.%m.%Y')} — {end_date.strftime('%d.%m.%Y')}",
        lang=lang,
    )
    await update_interface(
        state,
        message,
        text,
        reply_markup=get_stats_keyboard(account_id, lang=lang),
        parse_mode="Markdown",
    )
    await state.clear()
