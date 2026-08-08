from . import admin, deposit, excel, history, start, stats, trades

routers = [
    start.router,
    deposit.router,
    trades.router,
    history.router,
    stats.router,
    admin.router,
    excel.router,
]
