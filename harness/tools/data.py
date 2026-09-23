"""Таблицы (CSV/Excel) через pandas. Для сложного анализа есть run_python."""
import pandas as pd

from . import tool
from .files import safe_path


def load_table(path, sheet=""):
    p = safe_path(path)
    if p.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(p, sheet_name=sheet or 0)
    return pd.read_csv(p, sep=None, engine="python")


@tool
def table_info(path: str, sheet: str = "") -> str:
    """Структура таблицы: размер, колонки, типы, пропуски, первые строки, статистика.
    Вызывай перед любыми запросами к таблице.

    Args:
        path: CSV или Excel в рабочей папке.
        sheet: Лист Excel (пусто — первый).
    """
    df = load_table(path, sheet)
    cols = "\n".join(f"- {c} ({df[c].dtype}, пропусков: {df[c].isna().sum()}, уникальных: {df[c].nunique()})"
                     for c in df.columns)
    return (f"Строк: {len(df)}, колонок: {len(df.columns)}\n\nКолонки:\n{cols}\n\n"
            f"Первые строки:\n{df.head(5).to_string()}\n\nСтатистика:\n{df.describe(include='all').to_string()[:4000]}")


@tool
def query_table(path: str, filter: str = "", group_by: str = "", agg_column: str = "", agg: str = "sum",
                sort_by: str = "", descending: bool = True, limit: int = 30, sheet: str = "") -> str:
    """Фильтрует, группирует, сортирует таблицу. Все параметры кроме path необязательны.

    Args:
        path: CSV или Excel в рабочей папке.
        filter: Условие pandas.query, например "amount > 1000 and city == 'Астана'". Колонки с пробелами — в `обратных кавычках`.
        group_by: Колонка (или несколько через запятую) для группировки.
        agg_column: Что агрегировать при группировке.
        agg: sum, mean, count, min, max, median, nunique.
        sort_by: Колонка для сортировки.
        descending: По убыванию.
        limit: Сколько строк вернуть.
        sheet: Лист Excel.
    """
    df = load_table(path, sheet)
    if filter:
        df = df.query(filter)
    if group_by:
        keys = [g.strip() for g in group_by.split(",")]
        df = (df.groupby(keys)[agg_column].agg(agg).reset_index() if agg_column
              else df.groupby(keys).size().reset_index(name="count"))
    if sort_by:
        df = df.sort_values(sort_by, ascending=not descending)
    return f"Строк в результате: {len(df)}\n\n{df.head(limit).to_string()}"
