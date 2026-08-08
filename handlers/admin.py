import os

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile

from config import ADMIN_ID
from handlers.common import update_interface
from keyboards.inline import get_main_keyboard

router = Router()


# --- Резервная копия базы данных (Только для администратора) ---
@router.callback_query(F.data == "action_backup")
async def callback_backup(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⚠️ У вас нет доступа к этой функции.", show_alert=True)
        return

    db_path = os.path.join("data", "trading_bot.db")
    if os.path.exists(db_path):
        document = BufferedInputFile.from_file(
            db_path, filename="trading_bot_backup.db"
        )
        await update_interface(
            state,
            callback,
            "💾 **Резервная копия базы данных:**\n\nФайл актуальной базы данных успешно выгружен.",
            reply_markup=get_main_keyboard(callback.from_user.id),
            parse_mode="Markdown",
            document=document,
        )
    else:
        await callback.answer("⚠️ Файл базы данных не найден!", show_alert=True)
