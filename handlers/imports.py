from io import BytesIO

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from database import get_active_account_id, import_operations
from handlers.common import update_interface
from keyboards.inline import get_back_keyboard, get_main_keyboard
from states.fsm import ImportState
from utils.i18n import get_lang, t
from utils.importer import parse_import_data

router = Router()


@router.callback_query(F.data == "action_import")
async def callback_import(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    text = t(lang, "imp.instruction")
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_back_keyboard(lang=lang),
        parse_mode="Markdown",
    )
    await state.set_state(ImportState.waiting_for_file)


@router.message(ImportState.waiting_for_file)
async def process_import_file(message: types.Message, state: FSMContext):
    if not message.document:
        lang = get_lang(message.from_user.id)
        await update_interface(
            state,
            message,
            t(lang, "imp.send_file"),
            reply_markup=get_back_keyboard(lang=lang),
            parse_mode="Markdown",
        )
        return

    document = message.document
    user_id = message.from_user.id
    lang = get_lang(user_id)
    account_id = get_active_account_id(user_id)

    buf = BytesIO()
    await message.bot.download(document, buf)
    buf.seek(0)
    ops, errors = parse_import_data(buf.read(), document.file_name, lang=lang)

    if not ops:
        if errors:
            err_text = "\n".join(f"`{e}`" for e in errors[:15])
            text = t(lang, "imp.failed", errors=err_text)
        else:
            text = t(lang, "imp.empty_file")
        await update_interface(
            state,
            message,
            text,
            reply_markup=get_main_keyboard(user_id, lang=lang),
            parse_mode="Markdown",
        )
        return

    import_operations(user_id, account_id, ops)
    await state.clear()

    extra = t(lang, "imp.skipped_lines", count=len(errors)) if errors else ""
    text = t(lang, "imp.imported", count=len(ops), extra=extra)
    await update_interface(
        state,
        message,
        text,
        reply_markup=get_main_keyboard(user_id, lang=lang),
        parse_mode="Markdown",
    )
