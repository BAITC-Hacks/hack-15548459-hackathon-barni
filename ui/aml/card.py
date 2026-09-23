"""Карточка узла: роль, признаки, потоки, связи (вкладка «Сеть» и «Топ приоритетов»)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from pipeline.cards import node_card as pipeline_node_card

from . import theme
from .data import bool_value, money


def render_node_card(gid: str, nodes: pd.DataFrame, edges: pd.DataFrame) -> None:
    match = nodes[nodes["gid"] == gid]
    if match.empty:
        st.warning(f"GID {gid} не найден в выгрузке.")
        return
    row = match.iloc[0]
    st.markdown(pipeline_node_card(gid))
    badges = []
    if float(row.get("n_cycles", 0) or 0) > 0:
        badges.append(f"🔄 Циклы: {int(row.get('n_cycles', 0))}")
    if float(row.get("n_fast_chains", 0) or 0) > 0:
        badges.append(f"⚡ Быстрые цепочки: {int(row.get('n_fast_chains', 0))}")
    if bool_value(row.get("split_flag", False)):
        badges.append("🧩 Дробление")
    if float(row.get("anomaly_z", 0) or 0) >= 3:
        badges.append(f"📈 Аномалия: {float(row.get('anomaly_z', 0)):.1f}σ")
    if badges:
        st.markdown(" &nbsp; ".join(f"`{badge}`" for badge in badges), unsafe_allow_html=True)
    if bool_value(row.get("truncated", False)):
        st.error("Обрыв выгрузки на 4-м колене: исходящие не выгружены. Нужен дополнительный запрос данных.")
    st.markdown(f"**{theme.ROLE_LABELS.get(str(row.role), row.role)}** (`{row.role}`) · правило `{row.get('rule', '—')}` · кластер `{row.get('cluster_id', '—')}`")
    st.info(f"Гипотеза для проверки: {row.get('evidence', 'Признаки не описаны')} — это не утверждение о виновности.")
    a, b, c, d = st.columns(4)
    a.metric("Role score", f"{float(row.get('role_score', 0)):.3f}")
    b.metric("Приоритет", f"{float(row.get('priority_score', 0)):.3f}")
    c.metric("Получено", money(row.get("in_kzt")))
    d.metric("Отправлено", money(row.get("out_kzt")))
    a, b, c, d = st.columns(4)
    a.metric("Плательщиков", int(row.get("in_deg", 0)))
    b.metric("Получателей", int(row.get("out_deg", 0)))
    c.metric("Быстрый транзит", f"{float(row.get('fast_share', 0)):.0%}")
    d.metric("Seed в 2 шагах", int(row.get("seeds_2hop", 0)))
    incoming = edges[edges["dst"] == gid][["src", "sum_kzt", "n_tx"]].rename(columns={"src": "gid", "sum_kzt": "сумма, ₸", "n_tx": "переводов"})
    outgoing = edges[edges["src"] == gid][["dst", "sum_kzt", "n_tx"]].rename(columns={"dst": "gid", "sum_kzt": "сумма, ₸", "n_tx": "переводов"})
    left, right = st.columns(2)
    left.markdown("#### От кого получил")
    left.dataframe(incoming.sort_values("сумма, ₸", ascending=False), hide_index=True, width="stretch")
    right.markdown("#### Кому отправил")
    right.dataframe(outgoing.sort_values("сумма, ₸", ascending=False), hide_index=True, width="stretch")
