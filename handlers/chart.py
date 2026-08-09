from datetime import timedelta

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile

from database import (
    get_active_account,
    get_operations,
    get_user_currency,
    get_user_tz_offset,
    now_local,
)
from handlers.common import update_interface
from keyboards.inline import get_chart_keyboard
from utils.chart import generate_balance_chart_bytes
from utils.i18n import get_lang, t

router = Router()

_PERIOD_START = {
    "week": lambda now: (now - timedelta(days=6)).strftime("%Y-%m-%d"),
    "month": lambda now: now.replace(day=1).strftime("%Y-%m-%d"),
    "all": lambda now: None,
}


async def render_chart(event, state: FSMContext, period: str):
    user_id = event.from_user.id
    lang = get_lang(user_id)
    account = get_active_account(user_id)
    if not account:
        await event.answer(t(lang, "chart.need_account"), show_alert=True)
        return
    account_id, acc_name = account[0], account[1]
    operations = get_operations(account_id)
    if len(operations) < 1:
        await event.answer(t(lang, "chart.not_enough_data"), show_alert=True)
        return

    now = now_local(get_user_tz_offset(user_id))
    start = _PERIOD_START.get(period, lambda n: None)(now)
    png = generate_balance_chart_bytes(
        operations,
        get_user_currency(user_id),
        title=acc_name,
        start_date=start,
        lang=lang,
    )
    if not png:
        await event.answer(t(lang, "chart.no_data_period"), show_alert=True)
        return

    photo = BufferedInputFile(png, filename="balance_chart.png")
    text = t(lang, "chart.caption", name=acc_name)
    await update_interface(
        state,
        event,
        text,
        reply_markup=get_chart_keyboard(lang=lang),
        parse_mode="Markdown",
        photo=photo,
    )


@router.callback_query(F.data == "action_chart")
async def callback_chart(callback: types.CallbackQuery, state: FSMContext):
    await render_chart(callback, state, "all")


@router.callback_query(F.data.startswith("chart_"))
async def callback_chart_period(callback: types.CallbackQuery, state: FSMContext):
    period = callback.data.replace("chart_", "")
    await render_chart(callback, state, period)
