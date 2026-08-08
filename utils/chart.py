import io
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator


def generate_balance_chart_bytes(operations, currency: str) -> bytes:
    """Строит график баланса по операциям счёта и возвращает PNG-байты."""
    dates = [datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S") for r in operations]
    balance = [r[6] for r in operations]

    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=110)
    if len(dates) == 1:
        ax.scatter(dates, balance, color="#2ecc71", s=40, zorder=3)
    else:
        ax.plot(dates, balance, color="#2ecc71", linewidth=1.8, zorder=3)
        ymin = min(balance)
        ax.fill_between(
            dates, balance, ymin * 0.98, alpha=0.15, color="#2ecc71", zorder=1
        )

    ax.set_title(f"График баланса ({currency})", fontsize=12, pad=10)
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
