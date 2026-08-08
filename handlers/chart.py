from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile

from database import get_active_account_id, get_operations, get_user_currency
from handlers.common import update_interface
from keyboards.inline import get_main_keyboard
from utils.chart import generate_balance_chart_bytes

router = Router()


@router.callback_query(F.data == "action_chart")
async def callback_chart(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    account_id = get_active_account_id(user_id)
    operations = get_operations(account_id)
    if len(operations) < 1:
        await callback.answer("Недостаточно данных для графика.", show_alert=True)
        return
    curr = get_user_currency(user_id)
    png = generate_balance_chart_bytes(operations, curr)
    photo = BufferedInputFile(png, filename="balance_chart.png")
    text = "📈 **График баланса счета**"
    await update_interface(
        state,
        callback,
        text,
        reply_markup=get_main_keyboard(user_id),
        parse_mode="Markdown",
        photo=photo,
    )
