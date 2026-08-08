import logging
import os

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from database import SQLiteFSMStorage

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

if not API_TOKEN:
    raise ValueError("Не найден API_TOKEN в переменных окружения или файле .env!")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
storage = SQLiteFSMStorage()
dp = Dispatcher(storage=storage)
