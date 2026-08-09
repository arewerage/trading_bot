"""Тесты для модуля интернационализации (utils/i18n.py).

Чистые unit-тесты: реальная база данных не затрагивается —
database.get_user_language подменяется через monkeypatch везде,
где вызывается get_lang(), а отсутствие ключей имитируется
через подмену i18n._TABLES.
"""

from locales.en import EN_STRINGS
from locales.ru import RU_STRINGS
from utils.i18n import (
    DEFAULT_LANG,
    get_lang,
    lang_name,
    months,
    op_type_label,
    result_label,
    t,
)

# Контрактные ключи, которые обязаны присутствовать в обеих таблицах
CONTRACT_KEYS = [
    "op_type.trade",
    "op_type.deposit",
    "op_type.withdrawal",
    "op_type.start",
    "result.win",
    "result.loss",
    "lang.name.ru",
    "lang.name.en",
] + [f"month.{i}" for i in range(1, 13)]


# ==================== t() ====================


def test_t_exact_ru():
    assert t("ru", "op_type.trade") == "Сделка"
    assert t("ru", "start.main_menu") == RU_STRINGS["start.main_menu"]


def test_t_exact_en():
    assert t("en", "op_type.trade") == "Trade"
    assert t("en", "start.main_menu") == EN_STRINGS["start.main_menu"]


def test_t_fallback_en_to_ru_when_key_missing(monkeypatch):
    # Имитируем отсутствие ключа в английской таблице
    en_without_key = dict(EN_STRINGS)
    del en_without_key["op_type.deposit"]
    monkeypatch.setattr(
        "utils.i18n._TABLES",
        {"ru": RU_STRINGS, "en": en_without_key},
    )
    assert t("en", "op_type.deposit") == "Пополнение"


def test_t_unknown_lang_falls_back_to_ru():
    assert t("fr", "op_type.trade") == "Сделка"


def test_t_missing_everywhere_returns_key():
    assert t("ru", "no.such.key") == "no.such.key"
    assert t("en", "no.such.key") == "no.such.key"
    assert t("fr", "no.such.key") == "no.such.key"


def test_t_format_substitution():
    assert t("ru", "kb.tz", tz="+3") == "🌍 Часовой пояс (+3)"
    assert t("en", "kb.tz", tz="UTC+0") == "🌍 Time zone (UTC+0)"


def test_t_never_raises_on_missing_kwargs():
    raw_ru = RU_STRINGS["kb.tz"]
    raw_en = EN_STRINGS["kb.tz"]
    assert t("ru", "kb.tz") == raw_ru
    assert t("ru", "kb.tz", wrong="x") == raw_ru
    assert t("en", "kb.tz") == raw_en


# ==================== months() ====================


def test_months_ru_has_12_entries():
    result = months("ru")
    assert len(result) == 12
    assert list(result) == list(range(1, 13))
    assert result[1] == "Январь"
    assert result[12] == "Декабрь"


def test_months_en_has_12_entries():
    result = months("en")
    assert len(result) == 12
    assert list(result) == list(range(1, 13))
    assert result[1] == "January"
    assert result[12] == "December"


def test_months_unknown_lang_falls_back_to_ru():
    assert months("fr") == months("ru")
    assert months("fr")[1] == "Январь"


# ==================== op_type_label() ====================


def test_op_type_label_en():
    assert op_type_label("en", "Сделка") == "Trade"
    assert op_type_label("en", "Пополнение") == "Deposit"
    assert op_type_label("en", "Вывод") == "Withdrawal"
    assert op_type_label("en", "Старт") == "Start"


def test_op_type_label_ru_returns_db_value():
    assert op_type_label("ru", "Сделка") == "Сделка"
    assert op_type_label("ru", "Пополнение") == "Пополнение"


def test_op_type_label_unknown_returns_as_is():
    assert op_type_label("en", "Неизвестный тип") == "Неизвестный тип"


# ==================== result_label() ====================


def test_result_label_en():
    assert result_label("en", "Win") == "Win"
    assert result_label("en", "Loss") == "Loss"


def test_result_label_ru():
    assert result_label("ru", "Win") == "Плюс"
    assert result_label("ru", "Loss") == "Минус"


def test_result_label_unknown_returns_as_is():
    assert result_label("ru", "Draw") == "Draw"


# ==================== lang_name() ====================


def test_lang_name():
    assert lang_name("ru") == "Русский"
    assert lang_name("en") == "English"


# ==================== Целостность таблиц ====================


def test_key_set_parity():
    assert set(RU_STRINGS) == set(EN_STRINGS)


def test_contract_keys_present_in_both_tables():
    for key in CONTRACT_KEYS:
        assert key in RU_STRINGS, f"Отсутствует в RU_STRINGS: {key}"
        assert key in EN_STRINGS, f"Отсутствует в EN_STRINGS: {key}"


# ==================== get_lang() ====================


def test_get_lang_unknown_user_returns_default(monkeypatch):
    monkeypatch.setattr("database.get_user_language", lambda user_id: "ru")
    assert get_lang(0) == "ru"
    assert get_lang(0) == DEFAULT_LANG


def test_get_lang_returns_supported_language(monkeypatch):
    monkeypatch.setattr("database.get_user_language", lambda user_id: "en")
    assert get_lang(42) == "en"


def test_get_lang_invalid_value_returns_default(monkeypatch):
    monkeypatch.setattr("database.get_user_language", lambda user_id: "fr")
    assert get_lang(42) == DEFAULT_LANG


def test_get_lang_db_error_returns_default(monkeypatch):
    def boom(user_id):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr("database.get_user_language", boom)
    assert get_lang(999) == DEFAULT_LANG
