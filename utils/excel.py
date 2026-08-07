import io
import pandas as pd
from datetime import datetime
from openpyxl.styles import PatternFill, Font
from openpyxl.utils import get_column_letter
from database import get_user_deposit

def generate_excel_bytes(operations, user_id) -> bytes:
    from collections import defaultdict
    sheets_data = defaultdict(list)
    months_ru = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
        5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
        9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
    }

    trades = [r for r in operations if r[1] == "Сделка"]
    total_trades = len(trades)
    wins = sum(1 for r in trades if r[4] == "Win")
    losses = sum(1 for r in trades if r[4] == "Loss")
    winrate = (wins / total_trades) if total_trades > 0 else 0.0
    total_pl = sum(r[5] for r in trades)

    gross_profit = sum(r[5] for r in trades if r[5] > 0)
    gross_loss = abs(sum(r[5] for r in trades if r[5] < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)

    max_win_streak, max_loss_streak = 0, 0
    curr_win, curr_loss = 0, 0
    for r in trades:
        if r[4] == "Win":
            curr_win += 1
            curr_loss = 0
            if curr_win > max_win_streak: max_win_streak = curr_win
        else:
            curr_loss += 1
            curr_win = 0
            if curr_loss > max_loss_streak: max_loss_streak = curr_loss

    peak, max_dd = -float('inf'), 0.0
    for r in operations:
        bal = r[6]
        if bal > peak: peak = bal
        dd = peak - bal
        if dd > max_dd: max_dd = dd

    current_deposit = get_user_deposit(user_id)

    summary_rows = [
        {"Показатель": "Текущий баланс", "Значение": current_deposit},
        {"Показатель": "Всего сделок", "Значение": total_trades},
        {"Показатель": "Прибыльных сделок", "Значение": wins},
        {"Показатель": "Убыточных сделок", "Значение": losses},
        {"Показатель": "Винрейт", "Значение": winrate},
        {"Показатель": "Общий результат ($)", "Значение": total_pl},
        {"Показатель": "Профит-фактор", "Значение": profit_factor},
        {"Показатель": "Максимальная просадка ($)", "Значение": max_dd},
        {"Показатель": "Макс. серия побед", "Значение": max_win_streak},
        {"Показатель": "Макс. серия поражений", "Значение": max_loss_streak}
    ]

    monthly_stats = defaultdict(lambda: {"total": 0, "wins": 0, "losses": 0, "pl": 0.0})
    pair_stats = defaultdict(lambda: {"total": 0, "wins": 0, "losses": 0, "pl": 0.0})

    for row in operations:
        date_time_str, op_type, pair, lot, result, amount, balance_after, note, risk_pct = row
        dt_obj = datetime.strptime(date_time_str, "%Y-%m-%d %H:%M:%S")
        sheet_name = f"{months_ru[dt_obj.month]} {dt_obj.year}"

        # Четкое разделение типа операции для Excel (чтобы убыток не путался с выводом)
        if op_type == "Сделка":
            display_op_type = "Сделка (Плюс)" if result == "Win" else "Сделка (Минус)"
        else:
            display_op_type = op_type  # "Пополнение", "Вывод", "Старт"

        sheets_data[sheet_name].append({
            "Дата": dt_obj.strftime("%d.%m.%Y"),
            "Время": dt_obj.strftime("%H:%M:%S"),
            "Тип операции": display_op_type,
            "Торговая пара": pair if pair != "-" else "",
            "Лот": lot if lot > 0 else "",
            "Исход": ("Плюс" if result == "Win" else "Минус") if op_type == "Сделка" else "-",
            "Риск (%)": risk_pct if risk_pct > 0 else "",
            "Сумма операции ($)": amount,
            "Конечный депозит ($)": balance_after,
            "Заметка": note if note else ""
        })

        if op_type == "Сделка":
            m_key = f"{months_ru[dt_obj.month]} {dt_obj.year}"
            monthly_stats[m_key]["total"] += 1
            pair_stats[pair]["total"] += 1
            if result == "Win":
                monthly_stats[m_key]["wins"] += 1
                pair_stats[pair]["wins"] += 1
            else:
                monthly_stats[m_key]["losses"] += 1
                pair_stats[pair]["losses"] += 1
            monthly_stats[m_key]["pl"] += amount
            pair_stats[pair]["pl"] += amount

    monthly_rows = []
    for m, s in monthly_stats.items():
        wr = (s["wins"] / s["total"]) if s["total"] > 0 else 0.0
        monthly_rows.append({"Месяц": m, "Сделок": s["total"], "Плюсы": s["wins"], "Минусы": s["losses"], "Винрейт": wr, "Итог ($)": s["pl"]})

    pair_rows = []
    for p, s in pair_stats.items():
        wr = (s["wins"] / s["total"]) if s["total"] > 0 else 0.0
        pair_rows.append({"Пара": p, "Сделок": s["total"], "Плюсы": s["wins"], "Минусы": s["losses"], "Винрейт": wr, "Итог ($)": s["pl"]})

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        ws_summary = writer.book.create_sheet(title="Сводка", index=0)

        ws_summary.append(["ОБЩИЕ ПОКАЗАТЕЛИ"])
        ws_summary.append(["Показатель", "Значение"])
        for item in summary_rows:
            ws_summary.append([item["Показатель"], item["Значение"]])

        ws_summary.append([])
        ws_summary.append(["СТАТИСТИКА ПО МЕСЯЦАМ"])
        ws_summary.append(["Месяц", "Сделок", "Плюсы", "Минусы", "Винрейт", "Итог ($)"])
        for item in monthly_rows:
            ws_summary.append([item["Месяц"], item["Сделок"], item["Плюсы"], item["Минусы"], item["Винрейт"], item["Итог ($)"]])

        ws_summary.append([])
        ws_summary.append(["СТАТИСТИКА ПО ТОРГОВЫМ ПАРАМ"])
        ws_summary.append(["Пара", "Сделок", "Плюсы", "Минусы", "Винрейт", "Итог ($)"])
        for item in pair_rows:
            ws_summary.append([item["Пара"], item["Сделок"], item["Плюсы"], item["Минусы"], item["Винрейт"], item["Итог ($)"]])

        for row in ws_summary.iter_rows(min_row=1, max_row=ws_summary.max_row, min_col=1, max_col=6):
            for cell in row:
                if cell.value in ["ОБЩИЕ ПОКАЗАТЕЛИ", "СТАТИСТИКА ПО МЕСЯЦАХ", "СТАТИСТИКА ПО ТОРГОВЫМ ПАРАМ"]:
                    cell.font = Font(bold=True, size=11)
                elif cell.row in [2, len(summary_rows)+4, len(summary_rows)+len(monthly_rows)+7]:
                    cell.font = Font(bold=True)
                    cell.fill = PatternFill(start_color="E9ECEF", end_color="E9ECEF", fill_type="solid")

        for r in range(3, len(summary_rows) + 3):
            val_name = ws_summary.cell(row=r, column=1).value
            val_cell = ws_summary.cell(row=r, column=2)
            if "($)" in str(val_name) or val_name == "Текущий баланс":
                val_cell.number_format = '"$"#,##0.00'
            elif val_name == "Винрейт":
                val_cell.number_format = '0.0%'
            elif val_name in ["Профит-фактор", "Максимальная просадка ($)"]:
                val_cell.number_format = '0.00' if "Профит" in str(val_name) else '"$"#,##0.00'
            else:
                val_cell.number_format = '#,##0'

        for col in ws_summary.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws_summary.column_dimensions[col_letter].width = max(max_len + 4, 15)

        green_fill = PatternFill(start_color="D4EDDA", end_color="D4EDDA", fill_type="solid")
        red_fill = PatternFill(start_color="F8D7DA", end_color="F8D7DA", fill_type="solid")

        for sheet_name, rows in sheets_data.items():
            df = pd.DataFrame(rows)
            df.to_excel(writer, index=False, sheet_name=sheet_name)
            worksheet = writer.sheets[sheet_name]
            worksheet.auto_filter.ref = worksheet.dimensions

            for col_idx in range(1, worksheet.max_column + 1):
                col_name = worksheet.cell(row=1, column=col_idx).value
                if col_name in ["Сумма операции ($)", "Конечный депозит ($)"]:
                    for r_idx in range(2, worksheet.max_row + 1):
                        worksheet.cell(row=r_idx, column=col_idx).number_format = '"$"#,##0.00'
                elif col_name == "Риск (%)":
                    for r_idx in range(2, worksheet.max_row + 1):
                        if worksheet.cell(row=r_idx, column=col_idx).value:
                            worksheet.cell(row=r_idx, column=col_idx).number_format = '0.0"%"'

            for row_idx in range(2, worksheet.max_row + 1):
                val = None
                for c_idx in range(1, worksheet.max_column + 1):
                    if worksheet.cell(row=1, column=c_idx).value == "Исход":
                        val = worksheet.cell(row=row_idx, column=c_idx).value
                        break
                if val == "Плюс":
                    for c in range(1, worksheet.max_column + 1): worksheet.cell(row=row_idx, column=c).fill = green_fill
                elif val == "Минус":
                    for c in range(1, worksheet.max_column + 1): worksheet.cell(row=row_idx, column=c).fill = red_fill

            for col in worksheet.columns:
                max_len = max(len(str(cell.value or '')) for cell in col)
                worksheet.column_dimensions[get_column_letter(col[0].column)].width = max(max_len + 4, 12)

    return output.getvalue()
