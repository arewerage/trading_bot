from io import BytesIO

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from database import get_active_account_id, import_operations
from handlers.common import update_interface
from keyboards.inline import get_back_keyboard, get_main_keyboard
from states.fsm import ImportState
from utils.importer import parse_import_data

router = Router()


@router.callback_query(F.data == "action_import")
async def callback_import(callback: types.CallbackQuery, state: FSMContext):
    text = (
        "📥 **Импорт истории операций**\n\n"
        "Пришлите файл **CSV** или **Excel (.xlsx)** с колонками:\n"
        "`date, op_type, pair, lot, result, amount` (также: `note, side, commission, risk_pct`)\n\n"
        "Пример CSV:\n"
        "```\n"
        "date,op_type,pair,lot,result,amount\n"
        "05.01.2026,Сделка,EURUSD,0.1,Win,50\n"
        "06.01.2026,Сделка,GBPUSD,0.2,Loss,-20\n"
        "07.01.2026,Пополнение,-,-,-,200\n"
        "```\n"
        "Типы: `Сделка`, `Пополнение`, `Вывод`. Сумма сделки — со знаком (убыток `-20`).\n"
        "Дата в формате `ДД.ММ.ГГГГ` или `ГГГГ-ММ-ДД`."
    )
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(ImportState.waiting_for_file)


@router.message(ImportState.waiting_for_file)
async def process_import_file(message: types.Message, state: FSMContext):
    if not message.document:
        await update_interface(
            state,
            message,
            "⚠️ Пришлите файл (CSV или Excel).",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown",
        )
        return

    document = message.document
    user_id = message.from_user.id
    account_id = get_active_account_id(user_id)

    buf = BytesIO()
    await message.bot.download(document, buf)
    buf.seek(0)
    ops, errors = parse_import_data(buf.read(), document.file_name)

    if not ops:
        if errors:
            err_text = "\n".join(f"`{e}`" for e in errors[:15])
            text = f"⚠️ **Не удалось импортировать.**\n\n{err_text}"
        else:
            text = "⚠️ Файл пуст или не распознан. Проверьте формат."
        await update_interface(
            state,
            message,
            text,
            reply_markup=get_main_keyboard(user_id),
            parse_mode="Markdown",
        )
        return

    import_operations(user_id, account_id, ops)
    await state.clear()

    extra = (
        f"\n\n⚠️ Пропущено строк с ошибками: `{len(errors)}`" if errors else ""
    )
    text = f"✅ **Импортировано операций: `{len(ops)}`**{extra}"
    await update_interface(
        state,
        message,
        text,
        reply_markup=get_main_keyboard(user_id),
        parse_mode="Markdown",
    )
