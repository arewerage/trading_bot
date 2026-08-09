from datetime import timedelta

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile

from database import (
    get_user_operations,
    get_user_tz_offset,
    now_local,
)
from handlers.common import update_interface
from keyboards.inline import (
    get_analytics_keyboard,
    get_back_keyboard,
    get_excel_keyboard,
)
from states.fsm import ExcelState
from utils.excel import generate_excel_bytes
from utils.i18n import get_lang, t
from utils.validators import validate_date_range

router = Router()


async def _export_excel(event, state: FSMContext, operations, label: str, lang: str):
    user_id = event.from_user.id
    if not operations:
        await update_interface(
            state,
            event,
            t(lang, "excel.no_data", label=label),
            reply_markup=get_excel_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    excel_bytes = generate_excel_bytes(operations, user_id, lang=lang)
    document = BufferedInputFile(excel_bytes, filename=t(lang, "excel.filename"))
    await update_interface(
        state,
        event,
        t(lang, "excel.ready", label=label),
        reply_markup=get_analytics_keyboard(lang=lang),
        parse_mode="Markdown",
        document=document,
    )


# --- Меню выбора периода ---
@router.callback_query(F.data == "action_excel")
async def callback_excel(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    await update_interface(
        state,
        callback,
        t(lang, "excel.title"),
        reply_markup=get_excel_keyboard(lang=lang),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "excel_all")
async def callback_excel_all(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = get_lang(user_id)
    await _export_excel(
        callback,
        state,
        get_user_operations(user_id),
        t(lang, "excel.label_all"),
        lang,
    )


@router.callback_query(F.data.in_({"excel_today", "excel_week", "excel_month"}))
async def callback_excel_period(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = get_lang(user_id)
    now = now_local(get_user_tz_offset(user_id))
    if callback.data == "excel_today":
        start = end = now.strftime("%Y-%m-%d")
        label = t(lang, "excel.label_today")
    elif callback.data == "excel_week":
        start = (now - timedelta(days=6)).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")
        label = t(lang, "excel.label_week")
    else:
        start = now.replace(day=1).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")
        label = t(lang, "excel.label_month")
    operations = [
        r for r in get_user_operations(user_id) if start <= r[0][:10] <= end
    ]
    await _export_excel(callback, state, operations, label, lang)


@router.callback_query(F.data == "excel_custom")
async def callback_excel_custom(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    await update_interface(
        state,
        callback,
        t(lang, "excel.custom_prompt"),
        reply_markup=get_back_keyboard(lang=lang),
        parse_mode="Markdown",
    )
    await state.set_state(ExcelState.waiting_for_custom_period)


@router.message(ExcelState.waiting_for_custom_period)
async def process_excel_custom(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    parts = message.text.strip().split("-")
    if len(parts) != 2:
        await update_interface(
            state,
            message,
            t(lang, "excel.format_error"),
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    result, error = validate_date_range(parts[0].strip(), parts[1].strip(), lang=lang)
    if error:
        await update_interface(
            state,
            message,
            f"⚠️ {error}",
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return
    start_date, end_date = result
    start = start_date.strftime("%Y-%m-%d")
    end = end_date.strftime("%Y-%m-%d")
    user_id = message.from_user.id
    operations = [r for r in get_user_operations(user_id) if start <= r[0][:10] <= end]
    label = f"{start_date.strftime('%d.%m.%Y')} — {end_date.strftime('%d.%m.%Y')}"
    await _export_excel(message, state, operations, label, lang)
    await state.clear()
