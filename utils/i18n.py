"""
Модуль интернационализации (i18n) для бота торговой статистики.

Содержит функции для получения текстов на выбранном языке,
определения языка пользователя и преобразования значений БД
в отображаемые подписи.
"""

from locales.en import EN_STRINGS
from locales.ru import RU_STRINGS

# ==================== Константы ====================

# Поддерживаемые языки и язык по умолчанию
LANGUAGES = ("ru", "en")
DEFAULT_LANG = "ru"

# Таблицы строк по языкам (ключи — точечные, например 'lang.name.ru')
_TABLES = {
    "ru": RU_STRINGS,
    "en": EN_STRINGS,
}

# Русские названия месяцев (запасной вариант, если ключи month.N отсутствуют)
_DEFAULT_MONTHS = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}

# Соответствие значений БД (хранятся на русском) → ключи локализации
_OP_TYPE_KEYS = {
    "Сделка": "op_type.trade",
    "Пополнение": "op_type.deposit",
    "Вывод": "op_type.withdrawal",
    "Старт": "op_type.start",
}

_RESULT_KEYS = {
    "Win": "result.win",
    "Loss": "result.loss",
}


# ==================== Вспомогательные функции ====================


def _lookup(table: dict, key: str):
    """
    Поиск значения по точечному ключу (например, 'lang.name.ru').

    Поддерживает как плоские таблицы (ключ хранится целиком),
    так и вложенные словари. Возвращает None, если ключ не найден.
    """
    # Плоская таблица: ключ хранится целиком
    if key in table:
        return table[key]

    # Вложенная таблица: проходим по сегментам ключа
    node = table
    for part in key.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
        if node is None:
            return None
    return node


# ==================== Основные функции ====================


def t(lang: str, key: str, **kwargs) -> str:
    """
    Возвращает строку по ключу локализации.

    Цепочка поиска: таблица нужного языка → русская таблица → сам ключ.
    Затем к результату применяется .format(**kwargs).
    Функция никогда не бросает исключений при отсутствии ключа.
    """
    table = _TABLES.get(lang)
    text = _lookup(table, key) if table is not None else None

    if text is None:
        # Fallback на русский язык
        text = _lookup(_TABLES[DEFAULT_LANG], key)

    if text is None:
        # Последний вариант — вернуть сам ключ
        text = key

    # Подставляем параметры; при ошибке форматирования возвращаем текст как есть
    try:
        return str(text).format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return text


def get_lang(user_id: int) -> str:
    """
    Возвращает язык пользователя (см. LANGUAGES).

    При отсутствии пользователя, ошибке БД или некорректном значении
    возвращает DEFAULT_LANG.
    """
    # Импортируем лениво, чтобы избежать циклических импортов при загрузке модуля
    import database

    try:
        value = database.get_user_language(user_id)
    except Exception:
        return DEFAULT_LANG

    if value not in LANGUAGES:
        return DEFAULT_LANG
    return value


def months(lang: str) -> dict:
    """
    Возвращает словарь {1..12: название месяца} для указанного языка.
    """
    table = _TABLES.get(lang)
    result = {}
    for i in range(1, 13):
        key = f"month.{i}"
        value = _lookup(table, key) if table is not None else None
        if value is not None:
            result[i] = value
        else:
            # Запасной вариант — русские названия месяцев
            result[i] = _DEFAULT_MONTHS[i]
    return result


def op_type_label(lang: str, op_type: str) -> str:
    """
    Возвращает отображаемую подпись типа операции.

    Значения БД хранятся на русском ('Сделка', 'Пополнение', 'Вывод', 'Старт').
    Неизвестный тип возвращается без изменений.
    """
    key = _OP_TYPE_KEYS.get(op_type)
    if key is None:
        return op_type
    return t(lang, key)


def result_label(lang: str, result: str) -> str:
    """
    Возвращает отображаемую подпись результата сделки.

    Принимает значения БД 'Win'/'Loss'. Неизвестное значение
    возвращается без изменений.
    """
    key = _RESULT_KEYS.get(result)
    if key is None:
        return result
    return t(lang, key)


def lang_name(lang: str) -> str:
    """
    Возвращает название языка на самом языке (например, 'ru' → 'Русский').
    """
    return t(lang, f"lang.name.{lang}")
