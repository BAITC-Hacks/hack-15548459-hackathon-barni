"""Компактная карточка узла с деталями потоков и полной сводкой по запросу."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from pipeline.cards import node_card as pipeline_node_card

from . import theme
from .data import bool_value, load_data, money


def _int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default


def _float(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if pd.notna(number) and abs(number) != float("inf") else default
    except (TypeError, ValueError, OverflowError):
        return default


def _text(value: object, default: str = "—") -> str:
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    return str(value)


def _prep_flow_table(edges: pd.DataFrame, gid: str, id_col: str, other_col: str, role_map: dict) -> pd.DataFrame:
    flow = edges.loc[edges[id_col].astype(str) == gid, [other_col, "sum_kzt", "n_tx"]].copy()
    if flow.empty:
        return pd.DataFrame(columns=["gid", "роль", "сумма", "точная сумма, ₸", "переводов"])
    flow["_amount_sort"] = pd.to_numeric(flow["sum_kzt"], errors="coerce")
    flow = flow.sort_values(["_amount_sort", other_col], ascending=[False, True], kind="mergesort").reset_index(drop=True)
    flow["роль"] = flow[other_col].astype(str).map(
        lambda other_gid: theme.ROLE_LABELS.get(role_map.get(other_gid, ""), role_map.get(other_gid, "—"))
    )
    flow["сумма"] = flow["sum_kzt"].map(money)
    flow["sum_kzt"] = flow["sum_kzt"].map(_text)
    flow["n_tx"] = flow["n_tx"].map(_int)
    flow = flow.rename(columns={other_col: "gid", "sum_kzt": "точная сумма, ₸", "n_tx": "переводов"})
    return flow[["gid", "роль", "сумма", "точная сумма, ₸", "переводов"]]


def _make_navigate(table: pd.DataFrame, key: str):
    def _navigate() -> None:
        state = st.session_state.get(key)
        rows = getattr(getattr(state, "selection", None), "rows", None) if state is not None else None
        if rows:
            idx = rows[0]
            if 0 <= idx < len(table):
                gid = str(table.iloc[idx]["gid"])
                if "legacy_" in key:
                    st.session_state["gid"] = int(gid)
                    st.session_state["search"] = gid
                else:
                    top_gids = set(load_data()[1]["gid"].astype(str))
                    st.session_state["gid_search"] = gid
                    st.session_state["top_gid"] = gid if gid in top_gids else ""
                    st.session_state["main_tab"] = "Сеть"
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
    """Отрисовывает роль, потоки и признаки узла. ``where`` задаёт уникальные ключи виджетов."""
    gid = str(gid)
    match = nodes[nodes["gid"].astype(str) == gid]
    if match.empty:
        st.warning(f"Узел {gid} не найден в выгрузке. Проверьте 18 цифр без пробелов.")
        return
    row = match.iloc[0]
    role = _text(row.get("role"), "unknown")
    rule_code = _text(row.get("rule"))
    cluster = _text(row.get("cluster_id"))
    is_seed = bool_value(row.get("is_seed", False))

    col_gid, col_role = st.columns([2, 3])
    with col_gid:
        st.code(gid, language=None)
    with col_role:
        seed_mark = " &nbsp; <b>Seed-клиент</b>" if is_seed else ""
        st.markdown(
            theme.role_badge(role)
            + f" &nbsp; правило `{html.escape(rule_code)}` · кластер `{html.escape(cluster)}`"
            + seed_mark,
            unsafe_allow_html=True,
        )

    priority = _float(row.get("priority_score"))
    st.progress(min(max(priority, 0.0), 1.0), text=f"Приоритет проверки {priority:.2f} из 1")
    st.markdown("#### Почему такая роль")
    st.info(theme.RULE_TEXT.get(rule_code, "Описание правила не найдено."))
    st.markdown(_text(row.get("evidence"), "Признаки не описаны"))
    st.caption("Это гипотеза для проверки, а не утверждение о виновности.")

    # Денежные потоки остаются первыми и самыми заметными показателями.
    a, b = st.columns(2)
    a.metric("Получено", money(row.get("in_kzt")))
    b.metric("Отправлено", money(row.get("out_kzt")))
    c, d = st.columns(2)
    c.metric("Плательщиков", _int(row.get("in_deg")))
    d.metric("Получателей", _int(row.get("out_deg")))
    c, d = st.columns(2)
    fast_share = row.get("fast_share")
    fast_display = "—" if pd.isna(fast_share) else f"{_float(fast_share):.0%}"
    c.metric("Быстрый транзит", fast_display)
    d.metric("Seed в 2 шагах", _int(row.get("seeds_2hop")))

    badges: list[tuple[str, str]] = []
    n_cycles = _int(row.get("n_cycles"))
    if n_cycles > 0:
        badges.append((f"Циклы: {n_cycles} ({money(row.get('cycle_kzt'))})", "Деньги возвращаются по кругу длиной до 6 шагов"))
    n_fast_chains = _int(row.get("n_fast_chains"))
    if n_fast_chains > 0:
        badges.append((f"Быстрые цепочки: {n_fast_chains}", "Деньги прошли через узел не более чем за 2 дня"))
    if bool_value(row.get("split_flag", False)):
        badges.append(("Дробление", "Несколько переводов одному получателю в день"))
    anomaly_z = _float(row.get("anomaly_z"))
    if anomaly_z >= 3:
        badges.append((f"Аномалия: {anomaly_z:.1f}σ", "Оборот или число связей выше типичного для своего колена"))
    if badges:
        spans = "".join(
            f"<span title='{html.escape(tip, quote=True)}'>{html.escape(label)}</span>"
            for label, tip in badges
        )
        st.markdown(f"<div class='feature-badges'>{spans}</div>", unsafe_allow_html=True)
    else:
        st.caption("Дополнительных признаков нет")

    role_map = dict(zip(nodes["gid"].astype(str), nodes["role"].astype(str)))
    outgoing = edges.loc[edges["src"].astype(str) == gid]
    if bool_value(row.get("truncated", False)):
        st.warning(
            "Данных не хватает: узел на 4-м колене, исходящие переводы не выгружались. "
            "Не считайте его конечным получателем без данных об исходящих связях. Нужна дополнительная выгрузка."
        )
    elif role == "terminal" and outgoing.empty:
        st.info("Исходящие связи не найдены в выгрузке. Одного этого факта недостаточно, чтобы считать узел конечным получателем.")

    incoming_table = _prep_flow_table(edges, gid, "dst", "src", role_map)
    outgoing_table = _prep_flow_table(edges, gid, "src", "dst", role_map)
    left, right = st.columns(2)
    with left:
        _render_flow_table("От кого получил", incoming_table, key=f"in_{gid}_{where}")
    with right:
        _render_flow_table("Кому отправил", outgoing_table, key=f"out_{gid}_{where}")

    with st.expander("Полная текстовая карточка пайплайна", key=f"card_expander_{gid}_{where}"):
        try:
            st.markdown(pipeline_node_card(gid))
        except Exception as exc:
            st.warning(f"Полный отчёт пайплайна недоступен: {exc}")
