import asyncio
import logging
from datetime import datetime, timedelta

from database import (
    get_account,
    get_operations,
    get_report_users,
    now_local,
)
from utils.analytics import calculate_advanced_stats, format_stats_text

logger = logging.getLogger(__name__)

REPORT_HOUR = 9


def _yesterday_ops_filter(dt_str: str, yesterday) -> bool:
    return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").date() == yesterday


async def send_daily_reports(bot):
    for user_id, tz_offset, account_id in get_report_users():
        try:
            yesterday = (now_local(tz_offset) - timedelta(days=1)).date()
            account = get_account(account_id)
            if not account:
                continue
            _, _, name, _, currency = account
            ops = get_operations(account_id)
            stats = calculate_advanced_stats(
                ops, lambda r, _d=yesterday: _yesterday_ops_filter(r[0], _d)
            )
            date_label = yesterday.strftime("%d.%m.%Y")
            if stats:
                text = format_stats_text(
                    stats, currency, f"Отчёт за {date_label} · {name}"
                )
            else:
                text = (
                    f"📊 **Отчёт за {date_label} · {name}:**\n\n"
                    "Сделок вчера не было."
                )
            await bot.send_message(user_id, text)
        except Exception as exc:
            logger.exception("Ошибка при отправке отчёта пользователю %s: %s", user_id, exc)


async def daily_reports_loop(bot):
    """Раз в сутки в REPORT_HOUR (по серверному времени) шлёт отчёты."""
    while True:
        now = datetime.now()
        target = now.replace(hour=REPORT_HOUR, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        await send_daily_reports(bot)
