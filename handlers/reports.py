import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from database import (
    get_account,
    get_active_account_id,
    get_operations,
    get_report_users,
    get_user_tz_offset,
    now_local,
)
from keyboards.inline import get_report_keyboard
from utils.analytics import calculate_advanced_stats, format_stats_text

logger = logging.getLogger(__name__)

router = Router()

REPORT_HOUR = 9


def _yesterday_ops_filter(dt_str: str, yesterday) -> bool:
    return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").date() == yesterday


async def _build_report_text(user_id: int, tz_offset: int, account_id: int) -> str | None:
    yesterday = (now_local(tz_offset) - timedelta(days=1)).date()
    account = get_account(account_id)
    if not account:
        return None
    _, _, name, _, currency = account
    ops = get_operations(account_id)
    stats = calculate_advanced_stats(
        ops, lambda r, _d=yesterday: _yesterday_ops_filter(r[0], _d)
    )
    date_label = yesterday.strftime("%d.%m.%Y")
    if stats:
        return format_stats_text(stats, currency, f"Отчёт за {date_label} · {name}")
    return (
        f"📊 **Отчёт за {date_label} · {name}:**\n\n"
        "Сделок вчера не было."
    )


async def _send_report(bot, user_id: int, tz_offset: int, account_id: int):
    text = await _build_report_text(user_id, tz_offset, account_id)
    if text is None:
        return
    await bot.send_message(
        user_id, text, reply_markup=get_report_keyboard(), parse_mode="Markdown"
    )


async def send_daily_reports(bot):
    for user_id, tz_offset, account_id in get_report_users():
        try:
            await _send_report(bot, user_id, tz_offset, account_id)
        except Exception as exc:
            logger.exception("Ошибка при отправке отчёта пользователю %s: %s", user_id, exc)


@router.callback_query(F.data == "report_again")
async def callback_report_again(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    account_id = get_active_account_id(user_id)
    if not account_id:
        await callback.answer("Счёт не найден.", show_alert=True)
        return
    try:
        await _send_report(
            callback.bot, user_id, get_user_tz_offset(user_id), account_id
        )
        await callback.answer("Отчёт отправлен ✅")
    except Exception as exc:
        logger.exception("Ошибка при повторной отправке отчёта: %s", exc)
        await callback.answer("Не удалось отправить отчёт.", show_alert=True)


async def daily_reports_loop(bot):
    """Раз в сутки в REPORT_HOUR (по серверному времени) шлёт отчёты."""
    while True:
        now = datetime.now()
        target = now.replace(hour=REPORT_HOUR, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        await send_daily_reports(bot)
