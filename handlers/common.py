from aiogram import types
from aiogram.fsm.context import FSMContext


# --- Универсальное управление интерфейсом (строго 1 активное сообщение) ---
async def update_interface(
    state: FSMContext,
    event: types.Message | types.CallbackQuery,
    text: str,
    reply_markup=None,
    parse_mode="Markdown",
    document=None,
    photo=None,
):
    if isinstance(event, types.CallbackQuery):
        await event.answer()
        bot_instance = event.bot
        chat_id = event.message.chat.id
    else:
        bot_instance = event.bot
        chat_id = event.chat.id
        try:
            await event.delete()
        except Exception:
            pass

    data = await state.get_data()
    old_msg_id = data.get("bot_msg_id")

    if isinstance(event, types.CallbackQuery) and not document and not photo:
        try:
            await event.message.edit_text(
                text, reply_markup=reply_markup, parse_mode=parse_mode
            )
            await state.update_data(bot_msg_id=event.message.message_id)
            return
        except Exception:
            pass

    if old_msg_id:
        try:
            await bot_instance.delete_message(chat_id=chat_id, message_id=old_msg_id)
        except Exception:
            pass

    if document:
        msg = await bot_instance.send_document(
            chat_id=chat_id,
            document=document,
            caption=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    elif photo:
        msg = await bot_instance.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    else:
        msg = await bot_instance.send_message(
            chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode
        )

    await state.update_data(bot_msg_id=msg.message_id)
