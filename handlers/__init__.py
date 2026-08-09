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
    # settings.router идёт ДО start.router: обработчик выбора языка из настроек
    # (action_lang / lang_*) перехватывает callback'и раньше, чем обработчик
    # первого входа в start.py (тоже F.data.startswith("lang_")), и пропускает
    # их через SkipHandler, когда выбор языка сделан при первом входе.
    settings.router,
    start.router,
    deposit.router,
    trades.router,
    history.router,
    stats.router,
    accounts.router,
    chart.router,
    imports.router,
    admin.router,
    excel.router,
    reports.router,
]
