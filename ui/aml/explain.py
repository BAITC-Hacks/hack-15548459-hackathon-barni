"""Вкладка «Как это работает»: пайплайн, роли, ловушки данных, формула приоритета, белые пятна.

Для жюри — умещается примерно на один экран, поэтому весь рендеринг вынесен сюда отдельно от app.py.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from . import theme
from .data import bool_value, load_report, transactions_count

PRIORITY_LABELS = {
    "role": "роль", "flow": "оборот", "seeds": "близость к seed",
    "pagerank": "PageRank", "betweenness": "посредничество", "patterns": "паттерны",
}


def _priority_weights() -> dict:
    try:
        from pipeline.config import THRESHOLDS
        return dict(THRESHOLDS.get("priority_weights", {}))
    except Exception:
        return {}


def _pipeline_scheme_html(tx_count: int | None, node_count: int, seed_count: int) -> str:
    tx_label = f"{tx_count:,}".replace(",", " ") if tx_count is not None else "—"
    node_label = f"{node_count:,}".replace(",", " ")
    steps = [
        f"<b>Данные</b><br>{tx_label} переводов, {node_label} клиентов, {seed_count} seed",
        "<b>Метрики</b><br>сколько получил/отдал, от скольких людей, как быстро ушли деньги, место в сети",
        "<b>Роли</b><br>правила по порядку, у каждого узла код правила",
        "<b>Приоритет</b><br>роль + оборот + близость к seed + центральность + паттерны",
    ]
    parts = []
    for i, step in enumerate(steps):
        parts.append(f"<div class='aml-flow-box'>{step}</div>")
        if i < len(steps) - 1:
            parts.append("<div class='aml-flow-arrow'>→</div>")
    return f"<div class='aml-flow'>{''.join(parts)}</div>"


def _roles_table_html(nodes: pd.DataFrame) -> str:
    counts = nodes["role"].value_counts()
    rows = []
    for role in theme.ROLE_LABELS:
        codes = sorted(nodes.loc[nodes["role"] == role, "rule"].dropna().unique().tolist())
        words = "; ".join(theme.RULE_TEXT.get(code, code) for code in codes)
        rows.append(
            "<tr>"
            f"<td>{theme.role_badge(role)}</td>"
            f"<td class='aml-mono'>{', '.join(codes) or '—'}</td>"
            f"<td>{words or '—'}</td>"
            f"<td>{int(counts.get(role, 0))}</td>"
            "</tr>"
        )
    return (
        "<table class='aml-roles-table'><thead><tr>"
        "<th>роль</th><th>правило</th><th>простыми словами</th><th>узлов</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def render_how_it_works(nodes: pd.DataFrame) -> None:
    """Рисует всю вкладку «Как это работает»."""
    seed_count = int(nodes["is_seed"].map(bool_value).sum())

    st.markdown("#### Пайплайн")
    st.markdown(_pipeline_scheme_html(transactions_count(), len(nodes), seed_count), unsafe_allow_html=True)

    st.markdown("##### Роли")
    st.markdown(_roles_table_html(nodes), unsafe_allow_html=True)

    st.markdown("##### Как учтены ловушки данных")
    trunc_count = int((nodes["rule"] == "P-trunc").sum())
    st.markdown(
        f"- **Обрыв на 4-м колене.** {trunc_count} узлов помечены `P-trunc` — обход дошёл до них, "
        "но их исходящие переводы не выгружались, поэтому роль «конечный» им не присваивается.\n"
        "- **Seed: входящие не выгружены.** Для seed-клиентов доля пропуска (`pass_through`) не "
        "считается — их входящие переводы в этой выборке занижены.\n"
        "- **Направленный граф.** Центральность (PageRank, посредничество) считается по направлению "
        "движения денег.\n"
        "- **Суммы и количество — разные сигналы.** Используются оба: число уникальных "
        "плательщиков/получателей (структура) и суммы переводов (масштаб)."
    )

    st.markdown("##### Приоритет проверки")
    weights = _priority_weights()
    for key, label in PRIORITY_LABELS.items():
        value = float(weights.get(key, 0.0))
        st.progress(min(max(value, 0.0), 1.0), text=f"{label} — {value:.2f}")

    report = load_report()
    blind_spots = report.get("blind_spots_md", "")
    with st.expander("Белые пятна и следующий запрос", expanded=False):
        if blind_spots:
            st.markdown(blind_spots)
        else:
            st.caption("Раздел отчёта недоступен — запустите python run_pipeline.py")

    st.caption(
        "Все выводы — гипотезы для проверки аналитиком, а не утверждения о виновности. "
        "Атрибуты клиентов не используются: только структура сети, суммы и даты."
    )
