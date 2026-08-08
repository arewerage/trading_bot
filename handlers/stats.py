from datetime import datetime, timedelta

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from database import get_user_currency, get_user_operations
from handlers.common import update_interface
from keyboards.inline import get_back_keyboard, get_main_keyboard, get_stats_keyboard
from states.fsm import StatsState
from utils.analytics import calculate_advanced_stats
from utils.validators import validate_date_range

router = Router()


# --- Статистика ---
@router.callback_query(F.data == "action_stats")
async def callback_stats_menu(callback: types.CallbackQuery, state: FSMContext):
    await update_interface(
        state,
        callback,
        "📊 **Меню статистики**\n\nВыберите период или пару:",
        reply_markup=get_stats_keyboard(callback.from_user.id),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.in_({"stats_day", "stats_week", "stats_month"}))
async def callback_stats_period(callback: types.CallbackQuery, state: FSMContext):
    now = datetime.now()
    user_id = callback.from_user.id
    curr = get_user_currency(user_id)

    if callback.data == "stats_day":
        label, start_date, end_date = "день", now.date(), now.date()
        f_func = lambda r: (
            datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S").date() == now.date()
        )
    elif callback.data == "stats_week":
        label, end_date = "неделю", now.date()
        start_date = (now - timedelta(days=7)).date()
        f_func = lambda r: (
            datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S") >= now - timedelta(days=7)
        )
    else:
        label, start_date = "месяц", now.replace(day=1).date()
        next_m = (
            now.replace(year=now.year + 1, month=1, day=1)
            if now.month == 12
            else now.replace(month=now.month + 1, day=1)
        )
        end_date = (next_m - timedelta(days=1)).date()
        f_func = lambda r: (
            (dt := datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S")).year == now.year
            and dt.month == now.month
        )

    date_str = (
        f"{start_date.strftime('%d.%m.%Y')}"
        if label == "день"
        else f"{start_date.strftime('%d.%m.%Y')} — {end_date.strftime('%d.%m.%Y')}"
    )
    stats = calculate_advanced_stats(get_user_operations(user_id), f_func)

    text = (
        f"📊 **Статистика за {label} ({date_str}):**\n\nСделок не найдено."
        if not stats
        else f"📊 **Статистика за {label} ({date_str}):**\n\n📁 Сделок: `{stats['total']}`\n✅ Плюсов: `{stats['wins']}` | ❌ Минусов: `{stats['losses']}`\n🎯 Винрейт: `{stats['winrate']:.1f}%`\n💰 Итог: `{stats['total_pl']:+.2f} {curr}`\n📈 Профит-фактор: `{stats['profit_factor']:.2f}`"
    )
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_stats_keyboard(user_id),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("stats_pair_"))
async def callback_stats_pair(callback: types.CallbackQuery, state: FSMContext):
    pair = callback.data.replace("stats_pair_", "")
    user_id = callback.from_user.id
    curr = get_user_currency(user_id)
    stats = calculate_advanced_stats(
        get_user_operations(user_id), lambda r: r[2] == pair
    )
    text = (
        f"📊 **Пара `{pair}`:**\n\nСделок не найдено."
        if not stats
        else f"📊 **Пара `{pair}`:**\n\n📁 Сделок: `{stats['total']}`\n💰 Итог: `{stats['total_pl']:+.2f} {curr}`\n📈 Профит-фактор: `{stats['profit_factor']:.2f}`"
    )
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_stats_keyboard(user_id),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "stats_custom")
async def callback_stats_custom(callback: types.CallbackQuery, state: FSMContext):
    await update_interface(
        state,
        callback,
        "⏱ **Произвольный период**\n\nВведите диапазон дат в формате `ДД.ММ.ГГГГ - ДД.ММ.ГГГГ`",
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(StatsState.waiting_for_custom_period)


@router.message(StatsState.waiting_for_custom_period)
async def process_custom_period(message: types.Message, state: FSMContext):
    parts = message.text.strip().split("-")
    if len(parts) != 2:
        await update_interface(
            state,
            message,
            "⚠️ Ошибка формата. Введите в формате `ДД.ММ.ГГГГ - ДД.ММ.ГГГГ`",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )
        return
    start_str, end_str = parts[0].strip(), parts[1].strip()
    result, error = validate_date_range(start_str, end_str)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )
        return
    start_date, end_date = result
    user_id = message.from_user.id
    curr = get_user_currency(user_id)
    stats = calculate_advanced_stats(
        get_user_operations(user_id),
        lambda r: (
            start_date
            <= datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S").date()
            <= end_date
        ),
    )
    text = (
        f"📊 **Период:**\n\n📁 Сделок: `{stats['total']}`\n💰 Итог: `{stats['total_pl']:+.2f} {curr}`"
        if stats
        else "📊 Сделок не найдено."
    )
    await update_interface(
        state,
        message,
        text,
        reply_markup=get_main_keyboard(user_id),
        parse_mode="Markdown",
    )
    await state.clear()
