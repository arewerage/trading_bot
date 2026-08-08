# MEMORY.md

Накопленные факты и решения проекта; индексируется автоматически (FTS5).

## Discovered Knowledge

### Refactor wave: handlers group B (stats/admin/excel) — сделано 2026-08-08
- handlers/stats.py, handlers/admin.py, handlers/excel.py созданы из секций bot.py; тела скопированы ВЕРБАТИМНО (в декораторах только @dp. → @router.).
- Паттерн: каждый новый handlers/<name>.py начинается с `router = Router()`; UI управляется ТОЛЬКО через update_interface из handlers.common (она сама отвечает на callbacks — НЕ добавлять явный callback.answer() в хендлерах, использующих её).
- FIX 1: старый backup-хендлер в bot.py имел голый `await callback.answer()` перед update_interface → удалён (двойной answer = BadRequest). В admin.py теперь ровно 2 вызова answer(), оба в guard-ветках (проверка ADMIN_ID, проверка file-not-found).
- FIX 2: старый excel-хендлер в bot.py имел голый `await callback.answer()` (bot.py:635) → удалён. В excel.py 0 вызовов answer().
- ADMIN_ID берётся из config.py (не перечитывать env).
- Верификация: python -m py_compile handlers\<name>.py + python -c "import handlers.<name>" (оба exit 0). Линтера/CI в проекте нет.
- Gotcha: lsp_diagnostics (pyright) в этом окружении недоступен — pyright-langserver нет в PATH; на Windows он также дублирует filePath поверх cwd. Использовать py_compile/import smoke.
- Групповая проверка: py_compile всех 3 файлов + общий import smoke exit 0; bot.py по-прежнему компилируется и не тронут.

### Formatting gate 2.1b (ruff format + isort + EOL→LF) — PASS 2026-08-08
- `python .bob\format\precise_compare.py` (новый, читает .bob/format/ast_before.json из шага 0.1, сам регенерирует ast_after.json тем же методом ast_dump.py) разбивает дампы на: IMPORT_SET (top-level `Import(`/`ImportFrom(` на отступе ровно 4 пробела; lazy-импорт в utils/excel.py на 8 пробелах НЕ считается), CODE (дамп минус импорты, посимвольно) и DOCSTRINGS (residual-diff только в строках `Constant(value='...')`, decoded через ast.literal_eval — в дампе `\n` это 2-символьный escape, split по реальным newline работает только после декодирования).
- Результат: PRECISE-GATE PASS — 20/20 IMPORT_SET EQUAL, 19/20 CODE IDENTICAL, utils/validators.py = docstring-whitespace-only (9 констант, только trailing-space на пустых строках: `'    '`→`''`). Грубые 12 DIFF полностью объяснены: 11 = порядок импортов, 1 (validators.py) = импорты + пробелы докстрок.
- Контрольный гейт: compileall exit 0; smoke.py OK routers=7 handlers=10+20=30; eol_check.py OK no CRLF; `ruff format --check .` и `ruff check --select I .` exit 0 (идемпотентно).
- git diff --numstat финал: 484 add / 857 del (1341) << 2940 (churn до EOL-нормализации). bot.py add=6/del=639 (сжат рефакторингом, ~98% — единственный ~100% файл, это НЕ EOL-флип). Прочие <90%: keyboards/inline.py 96/23 (рефакторинг-сигнатура get_main_keyboard(user_id) + переносы строк; AST байт-в-байт одинаков), validators.py 94/107, excel.py 137/40, database.py 137/35. utils/analytics.py 11/13 — реальная правка рефакторинга (удалены avg_win/avg_loss/max_dd), не формат.
