from aiogram.fsm.state import State, StatesGroup

class DepositState(StatesGroup):
    waiting_for_currency = State()
    waiting_for_deposit = State()
    waiting_for_top_up = State()
    waiting_for_withdraw = State()

class TradeState(StatesGroup):
    waiting_for_pair = State()
    waiting_for_lot = State()
    waiting_for_profit = State()
    waiting_for_risk = State()
    waiting_for_note = State()
    waiting_for_confirmation = State()

class StatsState(StatesGroup):
    waiting_for_custom_period = State()
