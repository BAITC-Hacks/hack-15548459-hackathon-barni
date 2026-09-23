"""Отрисовка графа сети (pyvis) во вкладке «Сеть» и по кластерам."""
from __future__ import annotations

import json
import re

import pandas as pd
import streamlit as st
from pyvis.network import Network

from . import theme
from .data import bool_value, load_data, money, neighborhood

_STABILIZE_MARKER = "network = new vis.Network(container, data, options);"
_STABILIZE_SCRIPT = (
    _STABILIZE_MARKER + "\n"
    # Граф может рисоваться в скрытой вкладке (ширина 0) — тогда fit() считает неверный масштаб.
    # Поэтому: fit после стабилизации + заново при каждом изменении размера контейнера
    # (показ вкладки, ресайз окна). Ручной зум пользователя это не сбивает.
    "                  function amlFit() {\n"
    "                      if (!container.clientWidth || !container.clientHeight) { return; }\n"
    "                      network.redraw();\n"
    "                      network.fit({ animation: false });\n"
    "                      network.moveTo({ scale: network.getScale() * 0.9 });\n"
    "                  }\n"
    '                  network.once("stabilizationIterationsDone", function () {\n'
    "                      network.setOptions({ physics: false });\n"
    "                      amlFit();\n"
    "                  });\n"
    "                  if (window.ResizeObserver) {\n"
    "                      var amlLast = 0;\n"
    "                      new ResizeObserver(function () {\n"
    "                          if (container.clientWidth !== amlLast) { amlLast = container.clientWidth; amlFit(); }\n"
    "                      }).observe(container);\n"
    "                  }\n"
)
_HEADING_RE = re.compile(r"<center>\s*<h1>\s*</h1>\s*</center>")
_DARK_CSS = (
    "<style>"
    "html,body,#mynetwork{margin:0!important;padding:0!important;"
    "background:#0b1120!important;border:0!important;}"
    "#mynetwork{border:0!important;}"
    ".card{border:0!important;background:#0b1120!important;}"
    "#loadingBar{display:none!important;}"
    "</style></head>"
)


def graph_html(nodes: pd.DataFrame, edges: pd.DataFrame, selected: str | None) -> str:
    net = Network(height="640px", width="100%", directed=True, bgcolor="#0b1120", font_color="#f8fafc")
    net.set_options(json.dumps({
        "physics": {
            "enabled": True,
            # сильнее тянем к центру: одиночные узлы топа не разлетаются, ядро сети крупнее
            "barnesHut": {"gravitationalConstant": -3500, "centralGravity": 1.2,
                          "springLength": 110, "avoidOverlap": 0.3},
            "stabilization": {"enabled": True, "iterations": 250, "fit": True},
        },
        "interaction": {"hover": True, "navigationButtons": True},
        "nodes": {"font": {"size": 16, "color": "#f8fafc", "strokeWidth": 4, "strokeColor": "#0b1120"}},
        "edges": {"smooth": {"type": "dynamic"}, "arrows": {"to": {"enabled": True, "scaleFactor": 0.7}}},
    }))

    node_ids = set(nodes["gid"])
    has_priority = "priority_score" in nodes.columns and not nodes.empty
    if has_priority:
        priorities = nodes["priority_score"].astype(float)
        threshold = float(priorities.quantile(0.85))
        top15_ids = set(nodes.nlargest(15, "priority_score")["gid"])
    else:
        threshold, top15_ids = 1.0, set()

    for row in nodes.itertuples(index=False):
        gid, role = str(row.gid), str(row.role)
        priority = float(getattr(row, "priority_score", 0) or 0)
        seed = bool_value(getattr(row, "is_seed", False))
        is_selected = gid == selected
        base_color = theme.ROLE_COLORS.get(role, "#94a3b8")
        title = (f"gid: {gid}\n"
                 f"Роль: {theme.ROLE_LABELS.get(role, role)}\n"
                 f"Признаки: {getattr(row, 'evidence', '—')}")
        show_label = is_selected or gid in top15_ids or priority >= threshold
        size = 12 + 28 * max(0.0, priority)
        if is_selected:
            border_color, border_width, size = "#FACC15", 5, size * 1.3
        elif seed:
            border_color, border_width = "#ffffff", 3
        else:
            border_color, border_width = base_color, 2
        net.add_node(
            gid,
            label=gid[-6:] if show_label else " ",
            title=title,
            color={
                "background": base_color,
                "border": border_color,
                "highlight": {"background": base_color, "border": "#FACC15"},
            },
            borderWidth=border_width,
            size=size,
            shape="diamond" if seed else "dot",
        )
        if not show_label:
            # pyvis.add_node() treats a falsy ``label`` as "not provided" and
            # falls back to the full node id — force it empty after the fact.
            net.node_map[gid]["label"] = ""

    visible = edges[edges["src"].isin(node_ids) & edges["dst"].isin(node_ids)].copy()
    max_sum = max(float(visible["sum_kzt"].max() or 1), 1) if not visible.empty else 1
    role_map = dict(zip(nodes["gid"], nodes["role"]))
    for row in visible.itertuples(index=False):
        amount = float(row.sum_kzt)
        src_role = str(role_map.get(str(row.src), "peripheral"))
        net.add_edge(
            str(row.src), str(row.dst),
            value=1 + 8 * (amount / max_sum) ** 0.5,
            color=theme.role_rgba(src_role, 0.55),
            title=f"{money(amount)} · переводов: {int(row.n_tx)}",
        )

    page = net.generate_html(notebook=False)
    page = _HEADING_RE.sub("", page)
    page = page.replace("</head>", _DARK_CSS)
    if _STABILIZE_MARKER in page:
        page = page.replace(_STABILIZE_MARKER, _STABILIZE_SCRIPT, 1)
    return page


@st.cache_data(show_spinner=False)
def _cached_graph_html(node_ids: tuple[str, ...], selected: str | None) -> str:
    """Кэш HTML графа по набору узлов и выбранному gid; датафреймы берутся из уже закэшированного load_data()."""
    nodes, _top, _clusters, edges = load_data()
    shown = nodes[nodes["gid"].isin(node_ids)]
    return graph_html(shown, edges, selected)


def render_network(nodes: pd.DataFrame, edges: pd.DataFrame, gid: str | None, roles: list[str], cluster: int | None, depth: int) -> None:
    if gid:
        ids = neighborhood(edges, gid, depth)
    elif cluster is not None:
        ids = set(nodes.loc[nodes["cluster_id"] == cluster, "gid"])
    else:
        ids = set(nodes.nlargest(50, "priority_score")["gid"])
    shown = nodes[nodes["gid"].isin(ids) & nodes["role"].isin(roles)]
    if len(shown) > 300:
        limited = shown.nlargest(300, "priority_score")
        if gid and gid in set(shown["gid"]) and gid not in set(limited["gid"]):
            limited = pd.concat([limited.iloc[:-1], shown[shown["gid"] == gid]])
        shown = limited
    if shown.empty:
        st.warning("После фильтрации не осталось узлов.")
        return
    node_ids = tuple(sorted(shown["gid"]))
    html = _cached_graph_html(node_ids, gid)
    st.iframe(html, height=640, width="stretch")
