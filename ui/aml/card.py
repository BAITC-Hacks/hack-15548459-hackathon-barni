"""Карточка узла: роль, признаки, потоки, связи (вкладка «Сеть» и «Топ приоритетов»)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from pipeline.cards import node_card as pipeline_node_card

from . import theme
from .data import bool_value, money


def _int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _prep_flow_table(edges: pd.DataFrame, gid: str, id_col: str, other_col: str, role_map: dict) -> pd.DataFrame:
    """Готовит таблицу переводов (в/из gid): сортирует по сумме, добавляет роль и форматирует деньги."""
    flow = edges.loc[edges[id_col] == gid, [other_col, "sum_kzt", "n_tx"]]
    if flow.empty:
        return flow.rename(columns={other_col: "gid", "n_tx": "переводов"})
    flow = flow.sort_values("sum_kzt", ascending=False).reset_index(drop=True)
    flow["роль"] = flow[other_col].map(lambda g: theme.ROLE_LABELS.get(role_map.get(g, ""), role_map.get(g, "—")))
    flow["сумма"] = flow["sum_kzt"].map(money)
    flow = flow.rename(columns={other_col: "gid", "n_tx": "переводов"})
    return flow[["gid", "роль", "сумма", "переводов"]]


def _make_navigate(table: pd.DataFrame, key: str):
    """Колбэк для клика по строке: переводит gid_search на выбранный узел."""
    def _navigate() -> None:
        state = st.session_state.get(key)
        rows = getattr(getattr(state, "selection", None), "rows", None) if state is not None else None
        if rows:
            idx = rows[0]
            if 0 <= idx < len(table):
                st.session_state["gid_search"] = str(table.iloc[idx]["gid"])
    return _navigate


def _render_flow_table(title: str, table: pd.DataFrame, key: str) -> None:
    st.markdown(f"##### {title}")
    if table.empty:
        st.caption("Переводов в выгрузке нет")
        return
    st.caption("Нажмите на строку, чтобы перейти к узлу")
    st.dataframe(
        table, hide_index=True, width="stretch",
        on_select=_make_navigate(table, key), selection_mode="single-row", key=key,
    )


def render_node_card(gid: str, nodes: pd.DataFrame, edges: pd.DataFrame, where: str = "main") -> None:
    """Отрисовывает карточку узла gid. ``where`` делает ключи виджетов уникальными между вкладками."""
    match = nodes[nodes["gid"] == gid]
    if match.empty:
        st.warning(f"Узел {gid} не найден в выгрузке. Проверьте 18 цифр без пробелов.")
        return
    row = match.iloc[0]
    role = str(row.role)
    rule_code = str(row.get("rule", "—"))
    is_seed = bool_value(row.get("is_seed", False))

    # --- 1. Заголовок ---
    col_gid, col_role = st.columns([2, 3])
    with col_gid:
        st.code(gid, language=None)
    with col_role:
        seed_mark = " &nbsp; 🌱 <b>seed-клиент</b>" if is_seed else ""
        st.markdown(theme.role_badge(role) + f" &nbsp; `{rule_code}`" + seed_mark, unsafe_allow_html=True)
    priority = float(row.get("priority_score", 0) or 0)
    st.progress(min(max(priority, 0.0), 1.0), text=f"приоритет {priority:.2f} из 1")

    # --- 2. Почему такая роль ---
    st.markdown("#### Почему такая роль")
    st.info(theme.RULE_TEXT.get(rule_code, "Описание правила не найдено."))
    st.markdown(str(row.get("evidence", "Признаки не описаны")))
    st.caption("Это гипотеза для проверки, а не утверждение о виновности.")

    # --- 3. Числа ---
    a, b = st.columns(2)  # 2×2: в узкой колонке рядом с графом суммы не обрезаются
    c, d = st.columns(2)
    a.metric("Получил", money(row.get("in_kzt")))
    b.metric("Отдал", money(row.get("out_kzt")))
    c.metric("Плательщиков", _int(row.get("in_deg")))
    d.metric("Получателей", _int(row.get("out_deg")))

    a, b = st.columns(2)
    c, d = st.columns(2)
    fast_share = row.get("fast_share")
    fast_display = "—" if pd.isna(fast_share) else f"{float(fast_share):.0%}"
    a.metric("Быстрый проброс", fast_display, help="доля суммы, ушедшая в течение 2 дней после поступления")
    b.metric("Seed в 2 шагах выше", _int(row.get("seeds_2hop")))
    c.metric("Колено", _int(row.get("depth")))
    d.metric("Кластер", str(row.get("cluster_id", "—")))

    # --- 4. Значки признаков ---
    badges: list[tuple[str, str]] = []
    n_cycles = _int(row.get("n_cycles"))
    if n_cycles > 0:
        badges.append((
            f"🔄 Циклы: {n_cycles} ({money(row.get('cycle_kzt'))})",
            "деньги возвращаются по кругу длиной до 6 шагов",
        ))
    n_fast_chains = _int(row.get("n_fast_chains"))
    if n_fast_chains > 0:
        badges.append((f"⚡ Быстрый проброс: {n_fast_chains}", "деньги прошли A→узел→C за ≤2 дня"))
    if bool_value(row.get("split_flag", False)):
        badges.append(("✂️ Дробление", "несколько переводов одному получателю в день по 5–10 тыс ₸"))
    anomaly_z = float(row.get("anomaly_z", 0) or 0)
    if anomaly_z >= 3:
        badges.append((
            f"📈 Аномалия: {anomaly_z:.1f}σ",
            "оборот или число связей сильно выше типичного для своего колена (z-score)",
        ))
    if badges:
        spans = "".join(f"<span title='{tip}'>{label}</span>" for label, tip in badges)
        st.markdown(f"<div class='feature-badges'>{spans}</div>", unsafe_allow_html=True)
    else:
        st.caption("Дополнительных признаков нет")

    # --- 5. Обрыв выгрузки ---
    if bool_value(row.get("truncated", False)):
        st.warning(
            "Данных не хватает: узел на 4-м колене, его исходящие переводы не выгружались. "
            "Это не «конечный получатель» — нужна дополнительная выгрузка."
        )

    # --- 6. Таблицы связей ---
    role_map = dict(zip(nodes["gid"], nodes["role"]))
    incoming = _prep_flow_table(edges, gid, "dst", "src", role_map)
    outgoing = _prep_flow_table(edges, gid, "src", "dst", role_map)
    left, right = st.columns(2)
    with left:
        _render_flow_table("От кого получил", incoming, key=f"in_{gid}_{where}")
    with right:
        _render_flow_table("Кому отправил", outgoing, key=f"out_{gid}_{where}")

    # --- Полная текстовая карточка пайплайна ---
    with st.expander("Полная текстовая карточка", key=f"card_expander_{gid}_{where}"):
        st.markdown(pipeline_node_card(gid))
