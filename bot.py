import asyncio

from config import bot, dp
from database import init_db
from handlers import routers

for router in routers:
    dp.include_router(router)


async def main():
    init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
