"""Отрисовка графа сети (pyvis) во вкладке «Сеть» и по кластерам."""
from __future__ import annotations

import html
import json
import math
import re

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network

from . import theme
from .data import bool_value, load_data, money, neighborhood

GRAPH_BACKGROUND = "#0b1120"
GRAPH_LIMIT = 300
_EMPTY_HEADING = re.compile(r"<center>\s*<h1>\s*</h1>\s*</center>")


def _number(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _ordered_nodes(nodes: pd.DataFrame, selected: str | None = None) -> pd.DataFrame:
    """Stable priority order with string GIDs as the tie breaker."""
    ordered = nodes.copy()
    ordered["_gid_sort"] = ordered["gid"].astype("string")
    ordered["_priority_sort"] = pd.to_numeric(
        ordered.get("priority_score", pd.Series(0, index=ordered.index)), errors="coerce"
    ).fillna(float("-inf"))
    ordered["_selected_sort"] = ordered["_gid_sort"].eq(str(selected)) if selected else False
    ordered = ordered.sort_values(
        ["_selected_sort", "_priority_sort", "_gid_sort"],
        ascending=[False, False, True],
        kind="mergesort",
    )
    return ordered.drop(columns=["_gid_sort", "_priority_sort", "_selected_sort"])


def select_graph_nodes(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    selected: str | None,
    roles: list[str],
    cluster: int | None,
    depth: int,
    *,
    default_limit: int = 50,
    cap: int = GRAPH_LIMIT,
) -> tuple[pd.DataFrame, int, bool, bool]:
    """Return displayed rows, eligible count, role override, cluster override.

    A selected GID is retained even if its role (or cluster) is filtered out. Its
    neighborhood still respects an active cluster filter, so a selection does not
    silently turn a cluster view into a whole-network view.
    """
    if nodes.empty or "gid" not in nodes:
        return nodes.iloc[0:0].copy(), 0, False, False

    source = nodes.copy()
    source["gid"] = source["gid"].astype("string")
    selected = str(selected) if selected is not None else None
    all_ids = set(source["gid"].dropna().astype(str))
    cluster_ids: set[str] | None = None
    if cluster is not None:
        if "cluster_id" in source:
            cluster_ids = set(
                source.loc[source["cluster_id"] == cluster, "gid"].dropna().astype(str)
            )
        else:
            cluster_ids = set()

    if selected:
        ids = {str(value) for value in neighborhood(edges, selected, max(0, int(depth)))}
        if cluster_ids is not None:
            ids.intersection_update(cluster_ids)
        ids.add(selected)
    elif cluster_ids is not None:
        ids = cluster_ids
    else:
        ids = set(_ordered_nodes(source).head(max(0, int(default_limit)))["gid"].astype(str))

    candidates = source[source["gid"].astype(str).isin(ids)]
    if "role" in candidates:
        role_match = candidates["role"].astype(str).isin([str(role) for role in roles])
    else:
        role_match = pd.Series(False, index=candidates.index)
    shown = candidates[role_match]

    selected_exists = selected is not None and selected in all_ids
    selected_role_override = False
    selected_cluster_override = False
    if selected_exists:
        selected_row = candidates[candidates["gid"].astype(str) == selected]
        if not selected_row.empty:
            selected_role_override = not bool(role_match.loc[selected_row.index[0]])
            selected_cluster_override = cluster_ids is not None and selected not in cluster_ids
            if selected not in set(shown["gid"].astype(str)):
                shown = pd.concat([shown, selected_row], axis=0)

    eligible_count = len(shown)
    shown = _ordered_nodes(shown, selected).head(max(0, int(cap)))
    return shown, eligible_count, selected_role_override, selected_cluster_override


def visible_graph_edges(nodes: pd.DataFrame, edges: pd.DataFrame) -> pd.DataFrame:
    """Edges whose endpoints are both in the displayed node set, preserving input values."""
    if nodes.empty or edges.empty:
        return edges.iloc[0:0].copy()
    node_ids = set(nodes["gid"].dropna().astype(str))
    return edges[
        edges["src"].astype(str).isin(node_ids) & edges["dst"].astype(str).isin(node_ids)
    ].copy()


def graph_html(nodes: pd.DataFrame, edges: pd.DataFrame, selected: str | None) -> str:
    net = Network(
        height="660px", width="100%", directed=True,
        bgcolor=GRAPH_BACKGROUND, font_color="#f8fafc", cdn_resources="in_line",
    )
    net.set_options(json.dumps({
        "physics": {
            "enabled": True,
            "stabilization": {"enabled": True, "iterations": 180, "fit": True},
            "barnesHut": {"gravitationalConstant": -4800},
        },
        "layout": {"randomSeed": 37},
        "interaction": {
            "hover": True,
            "navigationButtons": True,
            "keyboard": {"enabled": True, "bindToWindow": False},
        },
        "edges": {"smooth": {"type": "dynamic"}, "arrows": {"to": {"enabled": True, "scaleFactor": 0.7}}},
    }))

    has_priority = "priority_score" in nodes.columns and not nodes.empty
    if has_priority:
        priorities = pd.to_numeric(nodes["priority_score"], errors="coerce").fillna(0)
        threshold = float(priorities.quantile(0.85))
        top15_ids = set(nodes.assign(_priority=priorities).nlargest(15, "_priority")["gid"].astype(str))
    else:
        threshold, top15_ids = 1.0, set()

    for row in _ordered_nodes(nodes, selected).itertuples(index=False):
        gid = str(row.gid)
        role = str(getattr(row, "role", ""))
        role_color = theme.ROLE_COLORS.get(role, "#94a3b8")
        is_selected = gid == str(selected) if selected is not None else False
        seed = bool_value(getattr(row, "is_seed", False))
        evidence = getattr(row, "evidence", "")
        if pd.isna(evidence):
            evidence = "Признаки не описаны"
        title = "\n".join((
            f"GID: {html.escape(gid)}",
            f"Роль: {html.escape(theme.ROLE_LABELS.get(role, role))}",
            f"Признаки: {html.escape(str(evidence))}",
            "Seed: да" if seed else "Seed: нет",
        ))
        priority = _number(getattr(row, "priority_score", 0))
        show_label = is_selected or gid in top15_ids or priority >= threshold
        net.add_node(
            gid,
            label=gid[-6:] if show_label else " ",
            title=title,
            color={
                "background": role_color,
                "border": "#ffffff" if (is_selected or seed) else role_color,
                "highlight": {"background": role_color, "border": "#ffffff"},
                "hover": {"background": role_color, "border": "#e2e8f0"},
            },
            borderWidth=5 if is_selected else (3 if seed else 2),
            size=12 + 28 * max(0.0, priority) * (1.3 if is_selected else 1.0),
            shape="diamond" if seed else "dot",
        )
        if not show_label:
            net.node_map[gid]["label"] = ""

    visible = visible_graph_edges(nodes, edges)
    amounts = pd.to_numeric(visible.get("sum_kzt", pd.Series(dtype=float)), errors="coerce")
    finite_amounts = amounts.replace([float("inf"), float("-inf")], float("nan")).dropna()
    max_sum = max(1.0, float(finite_amounts.max())) if not finite_amounts.empty else 1.0
    role_map = dict(zip(nodes["gid"].astype(str), nodes.get("role", pd.Series("peripheral", index=nodes.index)).astype(str)))
    for row in visible.itertuples(index=False):
        amount = _number(getattr(row, "sum_kzt", 0))
        count = _number(getattr(row, "n_tx", 0))
        raw_amount = getattr(row, "sum_kzt", None)
        try:
            exact_value = "—" if pd.isna(raw_amount) else str(raw_amount)
        except (TypeError, ValueError):
            exact_value = str(raw_amount)
        exact = html.escape(exact_value)
        title = f"Сумма: {money(amount)} (точное значение: {exact} ₸)\nПереводов: {int(count)}"
        net.add_edge(
            str(row.src), str(row.dst),
            value=1 + 8 * math.sqrt(max(0.0, amount) / max_sum),
            color=theme.role_rgba(role_map.get(str(row.src), "peripheral"), 0.55),
            title=title,
        )

    page = net.generate_html(notebook=False)
    page = _EMPTY_HEADING.sub("", page)
    css = (
        "<style>html,body,.card,#mynetwork{margin:0!important;padding:0!important;"
        f"background:{GRAPH_BACKGROUND}!important;border:0!important;box-shadow:none!important;}}"
        ".vis-tooltip{white-space:pre-line!important;background:#172033!important;"
        "color:#f8fafc!important;border:1px solid #475569!important;}"
        "@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;"
        "transition-duration:0s!important;animation-duration:0s!important;}}</style>"
    )
    page = page.replace("</head>", css + "</head>")
    reduced_motion = (
        "<script>(function(){if(typeof network==='undefined')return;"
        "var reduce=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;"
        "function amlFit(){window.requestAnimationFrame(function(){window.requestAnimationFrame(function(){"
        "if(!container.clientWidth||!container.clientHeight)return;network.redraw();"
        "network.fit({animation:false});network.moveTo({scale:network.getScale()*0.9});});});}"
        "if(reduce){network.setOptions({physics:{enabled:false}});amlFit();}"
        "else{network.once('stabilizationIterationsDone',function(){"
        "network.setOptions({physics:{enabled:false}});amlFit();});}"
        "if(window.ResizeObserver){var amlLast=0;new ResizeObserver(function(){"
        "if(container.clientWidth!==amlLast){amlLast=container.clientWidth;amlFit();}"
        "}).observe(container);}window.addEventListener('resize',amlFit);})();</script>"
    )
    return page.replace("</body>", reduced_motion + "</body>")


def _fallback_tables(nodes: pd.DataFrame, edges: pd.DataFrame) -> None:
    node_table = pd.DataFrame({
        "GID": nodes["gid"].astype("string"),
        "Роль": nodes.get("role", pd.Series("", index=nodes.index)).map(
            lambda value: theme.ROLE_LABELS.get(str(value), str(value))
        ),
        "Приоритет": pd.to_numeric(nodes.get("priority_score", 0), errors="coerce"),
        "Seed": nodes.get("is_seed", False).map(bool_value) if isinstance(nodes.get("is_seed", False), pd.Series) else False,
    })
    edge_table = pd.DataFrame({
        "От GID": edges["src"].astype("string"),
        "К GID": edges["dst"].astype("string"),
        "Сумма": edges.get("sum_kzt", pd.Series(index=edges.index, dtype=object)).map(money),
        "Точная сумма, ₸": edges.get("sum_kzt", pd.Series(index=edges.index, dtype=object)),
        "Переводов": edges.get("n_tx", pd.Series(index=edges.index, dtype=object)),
    })
    with st.expander("Таблица узлов и связей, доступная альтернатива графу"):
        st.markdown("Узлы и связи в таблицах совпадают с тем, что показано на графе.")
        st.dataframe(node_table, hide_index=True, width="stretch")
        st.dataframe(edge_table, hide_index=True, width="stretch")


@st.cache_data(show_spinner=False)
def _cached_graph_html(node_ids: tuple[str, ...], selected: str | None) -> str:
    """Кэш HTML графа по отображаемому набору GID."""
    nodes, _top, _clusters, edges = load_data()
    shown = nodes[nodes["gid"].astype(str).isin(node_ids)]
    return graph_html(shown, edges, selected)


def render_network(nodes: pd.DataFrame, edges: pd.DataFrame, gid: str | None, roles: list[str], cluster: int | None, depth: int) -> None:
    shown, eligible_count, role_override, cluster_override = select_graph_nodes(
        nodes, edges, gid, roles, cluster, depth,
    )
    if shown.empty:
        if not nodes.empty and not roles:
            st.info("Выберите хотя бы одну роль, чтобы показать сеть.")
        elif cluster is not None and not nodes.get("cluster_id", pd.Series(dtype=object)).eq(cluster).any():
            st.info("Для выбранного кластера узлов нет. Выберите другой кластер или сбросьте фильтр.")
        else:
            st.info("По текущему выбору узлов нет. Измените роли, глубину связей или кластер.")
        return

    shown_edges = visible_graph_edges(shown, edges)
    st.caption(f"Показано узлов: {len(shown)} из {eligible_count}; связей: {len(shown_edges)}.")
    if eligible_count > GRAPH_LIMIT:
        st.caption(f"Сеть ограничена первыми {GRAPH_LIMIT} узлами по приоритету проверки. Таблицы ниже содержат тот же показанный набор.")
    if role_override:
        st.info(f"Выбранный узел {gid} оставлен на графе, хотя его роль снята в фильтре. Остальные узлы соответствуют выбранным ролям.")
    if cluster_override:
        st.info(f"Выбранный узел {gid} оставлен на графе, хотя он находится вне кластера {cluster}. Его соседи ограничены выбранным кластером.")

    st.caption("Навигация: перетаскивайте фон для перемещения, колесо мыши для масштаба; доступны кнопки навигации и клавиатура. Белая рамка отмечает seed и выбранный узел; форма ромба также отмечает seed. Наведите указатель на узел или связь для подробностей.")
    node_ids = tuple(sorted(shown["gid"].astype(str)))
    components.html(_cached_graph_html(node_ids, gid), height=680, scrolling=False)
    _fallback_tables(shown, shown_edges)
