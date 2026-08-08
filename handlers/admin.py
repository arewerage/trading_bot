import asyncio
import logging
import os

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile

from config import ADMIN_ID
from database import get_all_user_ids
from handlers.common import update_interface
from handlers.reports import send_daily_reports
from keyboards.inline import get_back_keyboard, get_main_keyboard
from states.fsm import AdminState

logger = logging.getLogger(__name__)

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


# --- Ручной запуск ежедневных отчётов (Только для администратора) ---
@router.callback_query(F.data == "action_report_now")
async def callback_report_now(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⚠️ У вас нет доступа к этой функции.", show_alert=True)
        return
    asyncio.create_task(send_daily_reports(callback.bot))
    await update_interface(
        state,
        callback,
        "📊 **Отчёты отправляются** пользователям с включённым ежедневным отчётом…",
        reply_markup=get_main_keyboard(callback.from_user.id),
        parse_mode="Markdown",
    )


# --- Рассылка сообщения всем пользователям (Только для администратора) ---
async def _show_broadcast_confirm(event, state: FSMContext, text: str):
    count = len(get_all_user_ids())
    keyboard = [
        [
            types.InlineKeyboardButton(
                text="✅ Отправить всем", callback_data="broadcast_confirm"
            )
        ],
        [
            types.InlineKeyboardButton(
                text="✏️ Изменить текст", callback_data="action_broadcast"
            )
        ],
        [
            types.InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu"),
        ],
    ]
    await update_interface(
        state,
        event,
        f"📢 **Предпросмотр сообщения:**\n\n```\n{text}\n```\n\n"
        f"Отправить **{count}** пользователям?",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown",
    )
    await state.set_state(AdminState.waiting_for_broadcast_confirm)


@router.callback_query(F.data == "action_broadcast")
async def callback_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⚠️ У вас нет доступа к этой функции.", show_alert=True)
        return
    await update_interface(
        state,
        callback,
        "📢 **Рассылка всем пользователям**\n\nВведите текст сообщения:",
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(AdminState.waiting_for_broadcast)


@router.message(AdminState.waiting_for_broadcast)
async def process_broadcast_text(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Нет доступа.")
        return
    text = message.text.strip()
    if not text:
        await update_interface(
            state,
            message,
            "⚠️ Сообщение не может быть пустым.",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )
        return
    if len(text) > 4000:
        await update_interface(
            state,
            message,
            "⚠️ Сообщение слишком длинное (максимум 4000 символов).",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )
        return
    await state.update_data(broadcast_text=text)
    await _show_broadcast_confirm(message, state, text)


@router.callback_query(F.data == "broadcast_confirm", AdminState.waiting_for_broadcast_confirm)
async def process_broadcast_confirm(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data.get("broadcast_text")
    if not text:
        await callback.answer("Нет текста для отправки.", show_alert=True)
        return
    user_ids = get_all_user_ids()
    ok = fail = 0
    for uid in user_ids:
        try:
            await callback.bot.send_message(uid, text)
            ok += 1
        except Exception as exc:
            fail += 1
            logger.warning("Не удалось отправить пользователю %s: %s", uid, exc)
    await state.clear()
    await update_interface(
        state,
        callback,
        f"📢 **Рассылка завершена:**\n\n✅ Отправлено: `{ok}`\n❌ Ошибок: `{fail}`",
        reply_markup=get_main_keyboard(callback.from_user.id),
        parse_mode="Markdown",
    )
