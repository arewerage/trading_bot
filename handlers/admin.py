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
from utils.i18n import get_lang, t

logger = logging.getLogger(__name__)

router = Router()


# --- Резервная копия базы данных (Только для администратора) ---
@router.callback_query(F.data == "action_backup")
async def callback_backup(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(t(lang, "admin.no_access"), show_alert=True)
        return

    db_path = os.path.join("data", "trading_bot.db")
    if os.path.exists(db_path):
        document = BufferedInputFile.from_file(
            db_path, filename="trading_bot_backup.db"
        )
        await update_interface(
            state,
            callback,
            t(lang, "admin.backup_ok"),
            reply_markup=get_main_keyboard(callback.from_user.id, lang=lang),
            parse_mode="Markdown",
            document=document,
        )
    else:
        await callback.answer(t(lang, "admin.backup_missing"), show_alert=True)


# --- Ручной запуск ежедневных отчётов (Только для администратора) ---
@router.callback_query(F.data == "action_report_now")
async def callback_report_now(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(t(lang, "admin.no_access"), show_alert=True)
        return
    asyncio.create_task(send_daily_reports(callback.bot))
    await update_interface(
        state,
        callback,
        t(lang, "admin.reports_sending"),
        reply_markup=get_main_keyboard(callback.from_user.id, lang=lang),
        parse_mode="Markdown",
    )


# --- Рассылка сообщения всем пользователям (Только для администратора) ---
async def _show_broadcast_confirm(event, state: FSMContext, text: str):
    lang = get_lang(event.from_user.id)
    count = len(get_all_user_ids())
    keyboard = [
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.send_all"), callback_data="broadcast_confirm"
            )
        ],
        [
            types.InlineKeyboardButton(
                text=t(lang, "kb.change_text"), callback_data="action_broadcast"
            )
        ],
        [
            types.InlineKeyboardButton(text=t(lang, "kb.cancel"), callback_data="main_menu"),
        ],
    ]
    await update_interface(
        state,
        event,
        t(lang, "admin.broadcast_preview", text=text, count=count),
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown",
    )
    await state.set_state(AdminState.waiting_for_broadcast_confirm)


@router.callback_query(F.data == "action_broadcast")
async def callback_broadcast(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(t(lang, "admin.no_access"), show_alert=True)
        return
    await update_interface(
        state,
        callback,
        t(lang, "admin.broadcast_prompt"),
        reply_markup=get_back_keyboard(lang=lang),
        parse_mode="Markdown",
    )
    await state.set_state(AdminState.waiting_for_broadcast)


@router.message(AdminState.waiting_for_broadcast)
async def process_broadcast_text(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    if message.from_user.id != ADMIN_ID:
        await message.answer(t(lang, "admin.no_access_plain"))
        return
    text = message.text.strip()
    if not text:
        await update_interface(
            state,
            message,
            t(lang, "admin.broadcast_empty"),
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    if len(text) > 4000:
        await update_interface(
            state,
            message,
            t(lang, "admin.broadcast_too_long"),
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    await state.update_data(broadcast_text=text)
    await _show_broadcast_confirm(message, state, text)


@router.callback_query(F.data == "broadcast_confirm", AdminState.waiting_for_broadcast_confirm)
async def process_broadcast_confirm(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    data = await state.get_data()
    text = data.get("broadcast_text")
    if not text:
        await callback.answer(t(lang, "admin.broadcast_no_text"), show_alert=True)
        return
    user_ids = get_all_user_ids()
    ok = fail = 0
    for uid in user_ids:
        try:
            # Текст рассылки отправляется дословно, без перевода,
            # — содержимое сообщения принадлежит автору (администратору).
            await callback.bot.send_message(uid, text)
            ok += 1
        except Exception as exc:
            fail += 1
            logger.warning("Не удалось отправить пользователю %s: %s", uid, exc)
    await state.clear()
    await update_interface(
        state,
        callback,
        t(lang, "admin.broadcast_done", ok=ok, fail=fail),
        reply_markup=get_main_keyboard(callback.from_user.id, lang=lang),
        parse_mode="Markdown",
    )
