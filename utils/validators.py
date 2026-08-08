"""
Модуль валидации данных для бота торговой статистики.
Содержит функции для проверки корректности введённых данных.
"""

from datetime import date, datetime
from typing import Optional, Tuple

# ==================== Числовые значения ====================


def validate_deposit(value: str) -> Tuple[float, Optional[str]]:
    """
    Валидирует сумму депозита.

    Args:
        value: Строка с суммой

    Returns:
        Кортеж (value, error_message). Если error_message=None, валидация пройдена.
    """
    try:
        # Нормализуем разделитель
        amount = float(value.replace(",", ".").strip())

        # Проверяем положительность
        if amount <= 0:
            return amount, "Депозит должен быть больше нуля."

        # Проверяем разумность суммы
        if amount > 1_000_000:
            return amount, "Депозит кажется слишком большим (>1M). Проверьте значение."

        # Максимум 2 десятичных знака
        if len(str(amount).split('.')[-1]) > 2 and amount != int(amount):
            return amount, "Используйте не более 2 десятичных знаков."

        return amount, None

    except ValueError:
        return None, "Пожалуйста, введите корректное числовое значение."


def validate_amount(
    value: str, max_allowed: Optional[float] = None
) -> Tuple[Optional[float], Optional[str]]:
    """
    Валидирует сумму операции (может быть положительной или отрицательной).

    Args:
        value: Строка с суммой
        max_allowed: Максимально допустимая абсолютная сумма

    Returns:
        Кортеж (value, error_message)
    """
    try:
        amount = float(value.replace(",", ".").strip())

        # Проверяем, что значение не равно нулю
        if amount == 0:
            return None, "Сумма не может быть равна нулю."

        # Проверяем максимальное значение
        if max_allowed is not None and abs(amount) > max_allowed:
            return None, f"Абсолютная сумма не должна превышать {max_allowed:.2f}."

        # Максимум 2 десятичных знака
        if len(str(amount).split('.')[-1]) > 2 and amount != int(amount):
            return None, "Используйте не более 2 десятичных знаков."

        return amount, None

    except ValueError:
        return (
            None,
            "Пожалуйста, введите корректное числовое значение (например, `50` или `-20`).",
        )


def validate_lot(value: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Валидирует объём лота.

    Args:
        value: Строка с объёмом

    Returns:
        Кортеж (value, error_message)
    """
    try:
        lot = float(value.replace(",", ".").strip())

        if lot <= 0:
            return None, "Объём лота должен быть больше нуля."

        if lot > 1000:
            return lot, "⚠️ Предупреждение: указан очень большой объём лота (> 1000)."

        if lot > 50:
            return lot, "⚠️ Предупреждение: указан большой объём лота (> 50)."

        return lot, None

    except ValueError:
        return (
            None,
            "Пожалуйста, введите корректный объём лота (например, `0.1` или `5`).",
        )


def validate_risk_percent(value: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Валидирует процент риска.

    Args:
        value: Строка с процентом

    Returns:
        Кортеж (value, error_message)
    """
    try:
        risk = float(value.replace(",", ".").strip())

        if risk < 0 or risk > 100:
            return None, "Риск должен быть в диапазоне от 0 до 100%."

        return risk, None

    except ValueError:
        return None, "Пожалуйста, введите корректный процент (от 0 до 100)."


# ==================== Текстовые значения ====================


def validate_trading_pair(value: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Валидирует название торговой пары.

    Args:
        value: Строка с названием пары

    Returns:
        Кортеж (normalized_value, error_message)
    """
    if not value or not value.strip():
        return (
            None,
            "Пара не может быть пустой. Введите название пары (например, `EURUSD`).",
        )

    # Нормализуем: убираем спецсимволы и переводим в верхний регистр
    pair = value.strip().upper().replace("/", "").replace("-", "").replace(" ", "")

    if len(pair) < 3:
        return (
            None,
            "Название пары слишком короткое (минимум 3 символа, например `EURUSD`).",
        )

    if len(pair) > 20:
        return None, "Название пары слишком длинное (максимум 20 символов)."

    # Проверяем, что это буквы и/или цифры
    if not pair.isalnum():
        return None, "Пара должна содержать только буквы и цифры."

    return pair, None


def validate_note(value: str) -> Tuple[str, Optional[str]]:
    """
    Валидирует заметку к сделке.

    Args:
        value: Строка с заметкой

    Returns:
        Кортеж (normalized_value, error_message)
    """
    note = value.strip()

    if len(note) > 500:
        return None, "Заметка слишком длинная (максимум 500 символов)."

    return note, None


# ==================== Даты ====================


def validate_date_range(
    start_str: str, end_str: str
) -> Tuple[Optional[Tuple[date, date]], Optional[str]]:
    """
    Валидирует диапазон дат.

    Args:
        start_str: Начальная дата в формате ДД.ММ.ГГГГ
        end_str: Конечная дата в формате ДД.ММ.ГГГГ

    Returns:
        Кортеж ((start_date, end_date), error_message)
    """
    try:
        start_date = datetime.strptime(start_str.strip(), "%d.%m.%Y").date()
        end_date = datetime.strptime(end_str.strip(), "%d.%m.%Y").date()
    except ValueError:
        return (
            None,
            "Неверный формат даты. Используйте ДД.ММ.ГГГГ (например, `01.01.2024`).",
        )

    today = datetime.now().date()

    if start_date > end_date:
        return None, "Дата начала не может быть позже даты окончания."

    if start_date > today:
        return None, "Начальная дата не может быть в будущем."

    if end_date > today:
        return None, "Конечная дата не может быть в будущем."

    # Проверяем разумность диапазона (не более 5 лет)
    days_diff = (end_date - start_date).days
    if days_diff > 1825:  # ~5 лет
        return None, "Диапазон дат слишком большой (максимум ~5 лет)."

    return (start_date, end_date), None


# ==================== Комплексные проверки ====================


def validate_trade_confirmation(current_deposit: float, profit_loss: float) -> list:
    """
    Проверяет сделку перед подтверждением и возвращает список предупреждений.

    Args:
        current_deposit: Текущий депозит
        profit_loss: Профит/убыток

    Returns:
        Список предупреждений (может быть пуст)
    """
    warnings = []

    # Проверка 1: убыток превышает баланс
    if profit_loss < 0 and abs(profit_loss) >= current_deposit:
        warnings.append(
            "⚠️ *Внимание: убыток превышает или равен вашему балансу! Счёт обнулится.*"
        )

    # Проверка 2: сумма > 5x баланса (вероятная опечатка)
    if abs(profit_loss) > current_deposit * 5:
        warnings.append(
            "⚠️ *Внимание: сумма более чем в 5 раз превышает баланс (возможна опечатка).*"
        )

    # Проверка 3: убыток равен депозиту
    if profit_loss < 0 and abs(profit_loss) == current_deposit:
        warnings.append("⚠️ *Данная сделка полностью обнулит ваш депозит.*")

    return warnings


def validate_withdrawal(amount: float, current_deposit: float) -> Optional[str]:
    """
    Валидирует операцию вывода средств.

    Args:
        amount: Сумма вывода
        current_deposit: Текущий депозит

    Returns:
        Сообщение об ошибке или None
    """
    if amount <= 0:
        return "Сумма вывода должна быть больше нуля."

    if amount > current_deposit:
        return f"Нельзя вывести больше, чем есть на балансе! Доступно: {current_deposit:.2f}."

    return None
