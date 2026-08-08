from aiogram.fsm.state import State, StatesGroup


class DepositState(StatesGroup):
    waiting_for_currency = State()
    waiting_for_deposit = State()
    waiting_for_top_up = State()
    waiting_for_top_up_note = State()
    waiting_for_withdraw = State()
    waiting_for_withdraw_note = State()


class TradeState(StatesGroup):
    waiting_for_pair = State()
    waiting_for_lot = State()
    waiting_for_side = State()
    waiting_for_profit = State()
    waiting_for_commission = State()
    waiting_for_risk = State()
    waiting_for_note = State()
    waiting_for_date = State()
    waiting_for_custom_date = State()
    waiting_for_confirmation = State()

    edit_amount = State()
    edit_note = State()
    edit_risk = State()


class StatsState(StatesGroup):
    waiting_for_custom_period = State()


class AccountState(StatesGroup):
    waiting_for_new_name = State()
    waiting_for_currency = State()
    waiting_for_deposit = State()
    waiting_for_rename = State()


class ImportState(StatesGroup):
    waiting_for_file = State()


class SettingsState(StatesGroup):
    waiting_for_tz = State()
    waiting_for_currency = State()
