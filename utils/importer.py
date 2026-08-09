"""Парсинг файлов с историей операций (CSV/Excel) для импорта в счёт."""
import csv
import io
from datetime import datetime

from utils.i18n import t

_HEADER_ALIASES = {
    "date": {"date", "дата"},
    "op_type": {"op_type", "optype", "тип операции", "тип", "type", "операция", "типоперации"},
    "pair": {"pair", "пара", "торговая пара", "инструмент"},
    "lot": {"lot", "лот", "объём", "объем"},
    "side": {"side", "сторона", "направление"},
    "result": {"result", "исход", "результат"},
    "amount": {"amount", "сумма", "сумма операции", "суммаоперации"},
    "commission": {"commission", "комиссия", "комиссия ($)", "комиссия(usd)"},
    "risk_pct": {"risk_pct", "risk", "риск", "риск (%)", "риск(%)", "risk (%)"},
    "note": {"note", "заметка", "примечание", "комментарий"},
}

_OP_TYPE_ALIASES = {
    "сделка": "Сделка",
    "сделка,": "Сделка",
    "trade": "Сделка",
    "пополнение": "Пополнение",
    "пополнение,": "Пополнение",
    "deposit": "Пополнение",
    "top up": "Пополнение",
    "topup": "Пополнение",
    "вывод": "Вывод",
    "вывод,": "Вывод",
    "withdraw": "Вывод",
    "withdrawal": "Вывод",
}

_REQUIRED = {"date", "op_type", "amount"}


def _normalize_key(key: str) -> str | None:
    k = key.strip().lower().replace(" ", "").replace("_", "")
    for canonical, aliases in _HEADER_ALIASES.items():
        norm_aliases = {a.replace(" ", "").replace("_", "").lower() for a in aliases}
        if k in norm_aliases or k.replace("у", "у") in norm_aliases:
            return canonical
    return None


def _parse_date(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return None


def _parse_float(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _normalize_op_type(value) -> str | None:
    if value is None:
        return None
    key = str(value).strip().lower().replace("сделка,", "сделка")
    return _OP_TYPE_ALIASES.get(key)


def _row_to_op(row: dict, line_no: int, lang: str = "ru"):
    """Валидирует строку и возвращает словарь операции или строку ошибки."""
    date_str = _parse_date(row.get("date"))
    if not date_str:
        return t(lang, "imp.row_bad_date", line=line_no)
    op_type = _normalize_op_type(row.get("op_type"))
    if not op_type:
        return t(
            lang, "imp.row_unknown_type", line=line_no, value=row.get("op_type")
        )
    amount = _parse_float(row.get("amount"))
    if amount is None or amount == 0:
        return t(lang, "imp.row_bad_amount", line=line_no)

    pair = str(row.get("pair") or "-").strip().upper() or "-"
    lot = _parse_float(row.get("lot")) or 0.0
    side = str(row.get("side") or "").strip().capitalize()
    if side and side not in ("Buy", "Sell"):
        side = ""
    commission = _parse_float(row.get("commission")) or 0.0
    risk_pct = _parse_float(row.get("risk_pct")) or 0.0
    note = str(row.get("note") or "").strip()

    if op_type == "Сделка":
        result = str(row.get("result") or "").strip().capitalize()
        if result not in ("Win", "Loss"):
            result = "Win" if amount >= 0 else "Loss"
        if pair == "-":
            return t(lang, "imp.row_need_pair", line=line_no)
        return {
            "date": date_str,
            "op_type": op_type,
            "pair": pair,
            "lot": lot,
            "side": side,
            "result": result,
            "amount": amount,
            "commission": commission,
            "note": note,
            "risk_pct": risk_pct,
        }
    if op_type == "Пополнение":
        if amount < 0:
            amount = abs(amount)
    elif op_type == "Вывод":
        if amount > 0:
            amount = -amount
    return {
        "date": date_str,
        "op_type": op_type,
        "pair": "-",
        "lot": 0.0,
        "side": "",
        "result": "-",
        "amount": amount,
        "commission": 0.0,
        "note": note,
        "risk_pct": 0.0,
    }


def parse_import_data(data: bytes, filename: str, lang: str = "ru"):
    """Разбирает CSV/Excel и возвращает (ops, errors).
    ops — список словарей операций, отсортированный по дате.
    lang — язык текстов ошибок разбора строк (см. utils.i18n)."""
    name = (filename or "").lower()
    raw_rows = []
    if name.endswith(".xlsx") or name.endswith(".xls"):
        import pandas as pd

        df = pd.read_excel(io.BytesIO(data))
        raw_rows = [
            {str(k).strip(): (v if not isinstance(v, float) or not pd.isna(v) else "")
             for k, v in record.items()}
            for record in df.to_dict(orient="records")
        ]
    else:
        text = data.decode("utf-8-sig", errors="replace")
        for delimiter in (",", ";", "\t"):
            try:
                raw_rows = list(csv.DictReader(io.StringIO(text), delimiter=delimiter))
                if raw_rows:
                    break
            except Exception:
                continue

    ops = []
    errors = []
    for line_no, record in enumerate(raw_rows, start=2):
        mapped = {}
        for key, value in record.items():
            if key is None:
                continue
            canonical = _normalize_key(key)
            if canonical is not None and canonical not in mapped:
                mapped[canonical] = value
        missing = _REQUIRED - set(mapped.keys())
        if missing:
            errors.append(
                t(lang, "imp.row_missing_cols", line=line_no, cols=sorted(missing))
            )
            continue
        parsed = _row_to_op(mapped, line_no, lang)
        if isinstance(parsed, str):
            errors.append(parsed)
        else:
            ops.append(parsed)

    ops.sort(key=lambda o: o["date"])
    return ops, errors
