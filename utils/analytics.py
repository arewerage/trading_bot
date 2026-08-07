def calculate_advanced_stats(operations, filter_func):
    filtered = [r for r in operations if r[1] == "Сделка" and filter_func(r)]
    if not filtered:
        return None
    total = len(filtered)
    wins = sum(1 for r in filtered if r[4] == "Win")
    losses = sum(1 for r in filtered if r[4] == "Loss")
    winrate = (wins / total) * 100 if total > 0 else 0
    total_pl = sum(r[5] for r in filtered)
    gross_profit = sum(r[5] for r in filtered if r[5] > 0)
    gross_loss = abs(sum(r[5] for r in filtered if r[5] < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
    avg_win = (gross_profit / wins) if wins > 0 else 0.0
    avg_loss = (gross_loss / losses) if losses > 0 else 0.0

    peak, max_dd = -float('inf'), 0.0
    for r in operations:
        bal = r[6]
        if bal > peak: peak = bal
        dd = peak - bal
        if dd > max_dd: max_dd = dd

    return {
        "total": total, "wins": wins, "losses": losses, "winrate": winrate,
        "total_pl": total_pl, "profit_factor": profit_factor,
        "avg_win": avg_win, "avg_loss": avg_loss, "max_dd": max_dd
    }
