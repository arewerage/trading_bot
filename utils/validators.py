"""
Модуль валидации данных для бота торговой статистики.
Содержит функции для проверки корректности введённых данных.
"""

from datetime import date, datetime
from typing import Optional, Tuple

from utils.i18n import t

# ==================== Числовые значения ====================


def validate_deposit(
    value: str, lang: str = "ru"
) -> Tuple[float, Optional[str]]:
    """
    Валидирует сумму депозита.

    Args:
        value: Строка с суммой
        lang: Язык сообщений (по умолчанию "ru")

    Returns:
        Кортеж (value, error_message). Если error_message=None, валидация пройдена.
    """
    try:
        # Нормализуем разделитель
        amount = float(value.replace(",", ".").strip())

        # Проверяем положительность
        if amount <= 0:
            return amount, t(lang, "valid.deposit_positive")

        # Проверяем разумность суммы
        if amount > 1_000_000:
            return amount, t(lang, "valid.deposit_too_big")

        # Максимум 2 десятичных знака
        if len(str(amount).split('.')[-1]) > 2 and amount != int(amount):
            return amount, t(lang, "valid.decimals")

        return amount, None

    except ValueError:
        return None, t(lang, "valid.number")


def validate_amount(
    value: str, max_allowed: Optional[float] = None, lang: str = "ru"
) -> Tuple[Optional[float], Optional[str]]:
    """
    Валидирует сумму операции (может быть положительной или отрицательной).

    Args:
        value: Строка с суммой
        max_allowed: Максимально допустимая абсолютная сумма
        lang: Язык сообщений (по умолчанию "ru")

    Returns:
        Кортеж (value, error_message)
    """
    try:
        amount = float(value.replace(",", ".").strip())

        # Проверяем, что значение не равно нулю
        if amount == 0:
            return None, t(lang, "valid.amount_not_zero")

        # Проверяем максимальное значение
        if max_allowed is not None and abs(amount) > max_allowed:
            return None, t(
                lang, "valid.amount_max", max_allowed=f"{max_allowed:.2f}"
            )

        # Максимум 2 десятичных знака
        if len(str(amount).split('.')[-1]) > 2 and amount != int(amount):
            return None, t(lang, "valid.decimals")

        return amount, None

    except ValueError:
        return None, t(lang, "valid.number_signed")


def validate_lot(
    value: str, lang: str = "ru"
) -> Tuple[Optional[float], Optional[str], bool]:
    """
    Валидирует объём лота.

    Args:
        value: Строка с объёмом
        lang: Язык сообщений (по умолчанию "ru")

    Returns:
        Кортеж (value, error_message, is_warning). is_warning=True,
        если лот превышает разумный предел, а error_message — это
        локализованное предупреждение (ключи valid.lot_warn_huge
        или valid.lot_warn_big), иначе False.
    """
    try:
        lot = float(value.replace(",", ".").strip())

        if lot <= 0:
            return None, t(lang, "valid.lot_positive"), False

        if lot > 1000:
            return lot, t(lang, "valid.lot_warn_huge"), True

        if lot > 50:
            return lot, t(lang, "valid.lot_warn_big"), True

        return lot, None, False

    except ValueError:
        return None, t(lang, "valid.lot_number"), False


def validate_risk_percent(
    value: str, lang: str = "ru"
) -> Tuple[Optional[float], Optional[str]]:
    """
    Валидирует процент риска.

    Args:
        value: Строка с процентом
        lang: Язык сообщений (по умолчанию "ru")

    Returns:
        Кортеж (value, error_message)
    """
    try:
        risk = float(value.replace(",", ".").strip())

        if risk < 0 or risk > 100:
            return None, t(lang, "valid.risk_range")

        return risk, None

    except ValueError:
        return None, t(lang, "valid.risk_number")


# ==================== Текстовые значения ====================


def validate_trading_pair(
    value: str, lang: str = "ru"
) -> Tuple[Optional[str], Optional[str]]:
    """
    Валидирует название торговой пары.

    Args:
        value: Строка с названием пары
        lang: Язык сообщений (по умолчанию "ru")

    Returns:
        Кортеж (normalized_value, error_message)
    """
    if not value or not value.strip():
        return None, t(lang, "valid.pair_empty")

    # Нормализуем: убираем спецсимволы и переводим в верхний регистр
    pair = value.strip().upper().replace("/", "").replace("-", "").replace(" ", "")

    if len(pair) < 3:
        return None, t(lang, "valid.pair_short")

    if len(pair) > 20:
        return None, t(lang, "valid.pair_long")

    # Проверяем, что это буквы и/или цифры
    if not pair.isalnum():
        return None, t(lang, "valid.pair_alnum")

    return pair, None


def validate_note(value: str, lang: str = "ru") -> Tuple[str, Optional[str]]:
    """
    Валидирует заметку к сделке.

    Args:
        value: Строка с заметкой
        lang: Язык сообщений (по умолчанию "ru")

    Returns:
        Кортеж (normalized_value, error_message)
    """
    note = value.strip()

    if len(note) > 500:
        return None, t(lang, "valid.note_long")

    return note, None


# ==================== Даты ====================


def validate_single_date(
    value: str, lang: str = "ru"
) -> Tuple[Optional[date], Optional[str]]:
    """
    Валидирует одиночную дату в формате ДД.ММ.ГГГГ (не в будущем).

    Args:
        value: Строка с датой
        lang: Язык сообщений (по умолчанию "ru")

    Returns:
        Кортеж (date, error_message)
    """
    try:
        d = datetime.strptime(value.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None, t(lang, "valid.date_format")
    today = datetime.now().date()
    if d > today:
        return None, t(lang, "valid.date_future")
    return d, None


def validate_date_range(
    start_str: str, end_str: str, lang: str = "ru"
) -> Tuple[Optional[Tuple[date, date]], Optional[str]]:
    """
    Валидирует диапазон дат.

    Args:
        start_str: Начальная дата в формате ДД.ММ.ГГГГ
        end_str: Конечная дата в формате ДД.ММ.ГГГГ
        lang: Язык сообщений (по умолчанию "ru")

    Returns:
        Кортеж ((start_date, end_date), error_message)
    """
    try:
        start_date = datetime.strptime(start_str.strip(), "%d.%m.%Y").date()
        end_date = datetime.strptime(end_str.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None, t(lang, "valid.date_format")

    today = datetime.now().date()

    if start_date > end_date:
        return None, t(lang, "valid.range_order")

    if start_date > today:
        return None, t(lang, "valid.start_future")

    if end_date > today:
        return None, t(lang, "valid.end_future")

    # Проверяем разумность диапазона (не более 5 лет)
    days_diff = (end_date - start_date).days
    if days_diff > 1825:  # ~5 лет
        return None, t(lang, "valid.range_too_big")

    return (start_date, end_date), None


# ==================== Комплексные проверки ====================


def validate_trade_confirmation(
    current_deposit: float, profit_loss: float, lang: str = "ru"
) -> list:
    """
    Проверяет сделку перед подтверждением и возвращает список предупреждений.

    Args:
        current_deposit: Текущий депозит
        profit_loss: Профит/убыток
        lang: Язык сообщений (по умолчанию "ru")

    Returns:
        Список предупреждений (может быть пуст)
    """
    warnings = []

    # Проверка 1: убыток превышает баланс
    if profit_loss < 0 and abs(profit_loss) >= current_deposit:
        warnings.append(t(lang, "valid.warn_loss_exceeds"))

    # Проверка 2: сумма > 5x баланса (вероятная опечатка)
    if abs(profit_loss) > current_deposit * 5:
        warnings.append(t(lang, "valid.warn_amount_5x"))

    # Проверка 3: убыток равен депозиту
    if profit_loss < 0 and abs(profit_loss) == current_deposit:
        warnings.append(t(lang, "valid.warn_zero_deposit"))

    return warnings


def validate_commission(
    value: str, lang: str = "ru"
) -> Tuple[Optional[float], Optional[str]]:
    """
    Валидирует комиссию по сделке (опционально, неотрицательная).

    Пустое значение или "0" трактуется как отсутствие комиссии.

    Args:
        value: Строка с комиссией
        lang: Язык сообщений (по умолчанию "ru")

    Returns:
        Кортеж (commission, error_message)
    """
    text = value.strip().replace(",", ".")
    if text in ("", "0", "-", "skip", "нет"):
        return 0.0, None
    try:
        commission = float(text)
    except ValueError:
        return None, t(lang, "valid.commission_number")

    if commission < 0:
        return None, t(lang, "valid.commission_negative")
    if commission > 1_000_000:
        return None, t(lang, "valid.commission_too_big")
    if len(str(commission).split(".")[-1]) > 2 and commission != int(commission):
        return None, t(lang, "valid.decimals")
    return commission, None


def validate_tz_offset(
    value: str, lang: str = "ru"
) -> Tuple[Optional[int], Optional[str]]:
    """
    Валидирует смещение часового пояса в часах (например, "+3", "-5", "5.5").

    Args:
        value: Строка со смещением
        lang: Язык сообщений (по умолчанию "ru")

    Returns:
        Кортеж (minutes, error_message)
    """
    text = value.strip().lower().replace("utc", "").strip()
    if not text:
        return None, t(lang, "valid.tz_empty")
    try:
        hours = float(text.replace(",", "."))
    except ValueError:
        return None, t(lang, "valid.tz_number")
    if not (-12 <= hours <= 14):
        return None, t(lang, "valid.tz_range")
    minutes = int(round(hours * 60))
    return minutes, None


def validate_account_name(
    value: str, lang: str = "ru"
) -> Tuple[Optional[str], Optional[str]]:
    """
    Валидирует название счёта.

    Args:
        value: Строка с названием
        lang: Язык сообщений (по умолчанию "ru")

    Returns:
        Кортеж (name, error_message)
    """
    name = value.strip()
    if not name:
        return None, t(lang, "valid.account_name_empty")
    if len(name) > 30:
        return None, t(lang, "valid.account_name_long")
    return name, None


def validate_withdrawal(
    amount: float, current_deposit: float, lang: str = "ru"
) -> Optional[str]:
    """
    Валидирует операцию вывода средств.

    Args:
        amount: Сумма вывода
        current_deposit: Текущий депозит
        lang: Язык сообщений (по умолчанию "ru")

    Returns:
        Сообщение об ошибке или None
    """
    if amount <= 0:
        return t(lang, "valid.withdraw_positive")

    if amount > current_deposit:
        return t(
            lang, "valid.withdraw_insufficient", available=f"{current_deposit:.2f}"
        )

    return None
