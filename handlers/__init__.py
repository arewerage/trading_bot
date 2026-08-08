from . import (
    accounts,
    admin,
    chart,
    deposit,
    excel,
    history,
    imports,
    reports,
    settings,
    start,
    stats,
    trades,
)

routers = [
    start.router,
    deposit.router,
    trades.router,
    history.router,
    stats.router,
    accounts.router,
    settings.router,
    chart.router,
    imports.router,
    admin.router,
    excel.router,
    reports.router,
]
