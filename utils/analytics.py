def calculate_advanced_stats(operations, filter_func=None):
    """Расширенная статистика по сделкам. operations — строки счётных операций
    (date, op_type, pair, lot, result, amount, balance_after, ...)."""
    rows = [r for r in operations if r[1] == "Сделка"]
    if filter_func:
        rows = [r for r in rows if filter_func(r)]
    if not rows:
        return None

    total = len(rows)
    wins = sum(1 for r in rows if r[4] == "Win")
    losses = total - wins
    winrate = (wins / total) * 100 if total > 0 else 0.0

    amounts = [r[5] for r in rows]
    total_pl = sum(amounts)
    gross_profit = sum(a for a in amounts if a > 0)
    gross_loss = abs(sum(a for a in amounts if a < 0))
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    win_amounts = [a for a in amounts if a > 0]
    loss_amounts = [abs(a) for a in amounts if a < 0]
    avg_win = sum(win_amounts) / len(win_amounts) if win_amounts else 0.0
    avg_loss = sum(loss_amounts) / len(loss_amounts) if loss_amounts else 0.0
    if avg_loss > 0:
        rr = avg_win / avg_loss
    elif avg_win > 0:
        rr = float("inf")
    else:
        rr = 0.0
    expectancy = total_pl / total if total else 0.0
    best = max(amounts)
    worst = min(amounts)

    cur_w = cur_l = max_win_streak = max_loss_streak = 0
    for r in rows:
        if r[4] == "Win":
            cur_w += 1
            cur_l = 0
            max_win_streak = max(max_win_streak, cur_w)
        else:
            cur_l += 1
            cur_w = 0
            max_loss_streak = max(max_loss_streak, cur_l)

    peak = -float("inf")
    max_dd = 0.0
    for r in rows:
        bal = r[6]
        if bal > peak:
            peak = bal
        dd = peak - bal
        if dd > max_dd:
            max_dd = dd
    max_dd_pct = (max_dd / peak * 100) if peak > 0 else 0.0

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "winrate": winrate,
        "total_pl": total_pl,
        "profit_factor": profit_factor,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "rr": rr,
        "expectancy": expectancy,
        "best": best,
        "worst": worst,
        "max_dd": max_dd,
        "max_dd_pct": max_dd_pct,
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
    }


def calculate_stats_by_pair(operations, filter_func=None):
    """Сводка по торговым парам. Возвращает список (pair, {n, wins, pl, winrate}),
    отсортированный по числу сделок (убывание), затем по имени."""
    rows = [r for r in operations if r[1] == "Сделка"]
    if filter_func:
        rows = [r for r in rows if filter_func(r)]
    pairs = {}
    for r in rows:
        pair = r[2] or "-"
        s = pairs.setdefault(pair, {"n": 0, "wins": 0, "pl": 0.0})
        s["n"] += 1
        s["pl"] += r[5] or 0.0
        if r[4] == "Win":
            s["wins"] += 1
    out = []
    for pair, s in pairs.items():
        s["winrate"] = s["wins"] / s["n"] * 100 if s["n"] else 0.0
        out.append((pair, s))
    out.sort(key=lambda kv: (-kv[1]["n"], kv[0]))
    return out


def format_stats_by_pair(pairs, currency: str, title: str) -> str:
    """Текст таблицы «статистика по парам» для Telegram."""
    if not pairs:
        return f"📊 **{title}:**\n\nСделок не найдено."
    lines = [f"📊 **{title}:**\n"]
    for pair, s in pairs:
        lines.append(
            f"🔹 `{pair}`: `{s['n']}` сделок | винрейт `{s['winrate']:.0f}%` | "
            f"итог `{s['pl']:+.2f} {currency}`"
        )
    return "\n".join(lines)


def format_stats_text(stats, currency: str, title: str) -> str:
    """Формирует текст статистики для сообщения в Telegram."""
    if not stats:
        return f"📊 **{title}:**\n\nСделок не найдено."

    rr = stats["rr"]
    rr_str = f"{rr:.2f}" if rr != float("inf") else "∞"
    pf = stats["profit_factor"]
    pf_str = f"{pf:.2f}" if pf != float("inf") else "∞"

    return (
        f"📊 **{title}:**\n\n"
        f"📁 Сделок: `{stats['total']}`\n"
        f"✅ Плюсов: `{stats['wins']}` | ❌ Минусов: `{stats['losses']}`\n"
        f"🎯 Винрейт: `{stats['winrate']:.1f}%`\n"
        f"💰 Итог: `{stats['total_pl']:+.2f} {currency}`\n"
        f"📈 Профит-фактор: `{pf_str}`\n"
        f"📉 Ср. плюс / ср. минус: `{stats['avg_win']:.2f}` / `-{stats['avg_loss']:.2f}` {currency}\n"
        f"⚖️ R:R (риск/прибыль): `{rr_str}`\n"
        f"🎯 Ожидание на сделку: `{stats['expectancy']:+.2f} {currency}`\n"
        f"🔝 Лучшая / худшая: `{stats['best']:+.2f}` / `{stats['worst']:+.2f}` {currency}\n"
        f"🏔 Макс. просадка: `{stats['max_dd']:.2f} {currency}` (`{stats['max_dd_pct']:.1f}%`)\n"
        f"⛓ Серии: `{stats['max_win_streak']}` побед / `{stats['max_loss_streak']}` поражений"
    )
