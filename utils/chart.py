import io
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator


def generate_balance_chart_bytes(
    operations, currency: str, title: str | None = None, start_date: str | None = None
) -> bytes | None:
    """Строит график баланса по операциям счёта и возвращает PNG-байты.

    operations — строки get_operations (сортировка по (date, id)); кривая
    считается кумулятивно по ВСЕМ операциям, но точки рисуются только от
    start_date («ГГГГ-ММ-ДД»), так что баланс на периоде стартует корректно.
    """
    ordered = sorted(operations, key=lambda r: (r[0], r[11]))
    dates, balance = [], []
    win_d, win_b = [], []
    loss_d, loss_b = [], []
    dep_d, dep_b = [], []
    wd_d, wd_b = [], []

    acc = 0.0
    for r in ordered:
        acc = max(0.0, acc + (r[5] or 0.0))
        if start_date and r[0][:10] < start_date:
            continue
        dt = datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S")
        dates.append(dt)
        balance.append(acc)
        if r[1] == "Сделка":
            if r[4] == "Win":
                win_d.append(dt)
                win_b.append(acc)
            else:
                loss_d.append(dt)
                loss_b.append(acc)
        elif r[1] == "Пополнение":
            dep_d.append(dt)
            dep_b.append(acc)
        elif r[1] == "Вывод":
            wd_d.append(dt)
            wd_b.append(acc)

    if not dates:
        return None

    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=110)
    if len(dates) == 1:
        ax.scatter(dates, balance, color="#2ecc71", s=40, zorder=3)
    else:
        ax.plot(dates, balance, color="#2ecc71", linewidth=1.8, zorder=3)
        ymin = min(balance)
        ax.fill_between(
            dates, balance, ymin * 0.98, alpha=0.15, color="#2ecc71", zorder=1
        )

    # Метки операций: Win ▲ / Loss ▼ / Пополнение + / Вывод ✕
    if win_d:
        ax.scatter(win_d, win_b, marker="^", s=36, color="#27ae60", zorder=4, linewidths=0, alpha=0.9)
    if loss_d:
        ax.scatter(loss_d, loss_b, marker="v", s=36, color="#e74c3c", zorder=4, linewidths=0, alpha=0.9)
    if dep_d:
        ax.scatter(dep_d, dep_b, marker="+", s=60, color="#2ecc71", zorder=4, linewidths=1.6)
    if wd_d:
        ax.scatter(wd_d, wd_b, marker="x", s=48, color="#e74c3c", zorder=4, linewidths=1.6)

    ax.set_title(title or f"График баланса ({currency})", fontsize=12, pad=10)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
    for label in ax.get_xticklabels():
        label.set_rotation(30)
        label.set_ha("center")

    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()
