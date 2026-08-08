from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile

from database import get_user_operations
from handlers.common import update_interface
from keyboards.inline import get_main_keyboard
from utils.excel import generate_excel_bytes

router = Router()


# --- Генерация Excel ---
@router.callback_query(F.data == "action_excel")
async def callback_excel(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    operations = get_user_operations(user_id)
    if not operations:
        await update_interface(
            state,
            callback,
            "⚠️ Нет данных для выгрузки.",
            reply_markup=get_main_keyboard(user_id),
            parse_mode="Markdown",
        )
        return
    excel_bytes = generate_excel_bytes(operations, user_id)
    document = BufferedInputFile(excel_bytes, filename="trading_history.xlsx")
    await update_interface(
        state,
        callback,
        "📁 **Ваш Excel-файл готов!**",
        reply_markup=get_main_keyboard(user_id),
        parse_mode="Markdown",
        document=document,
    )
