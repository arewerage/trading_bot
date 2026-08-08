import asyncio

from config import bot, dp
from database import init_db
from handlers import routers
from handlers.reports import daily_reports_loop

for router in routers:
    dp.include_router(router)


async def main():
    init_db()
    reports_task = asyncio.create_task(daily_reports_loop(bot))
    try:
        await dp.start_polling(bot)
    finally:
        reports_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
