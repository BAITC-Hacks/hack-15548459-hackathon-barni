"""Отрисовка графа сети (pyvis) во вкладке «Сеть» и по кластерам."""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network

from . import theme
from .data import bool_value, money, neighborhood


def graph_html(nodes: pd.DataFrame, edges: pd.DataFrame, selected: str | None) -> str:
    net = Network(height="660px", width="100%", directed=True, bgcolor="#0b1120", font_color="#f8fafc")
    net.set_options(json.dumps({
        "physics": {"stabilization": {"iterations": 180}, "barnesHut": {"gravitationalConstant": -4800}},
        "interaction": {"hover": True, "navigationButtons": True},
        "edges": {"smooth": {"type": "dynamic"}, "arrows": {"to": {"enabled": True, "scaleFactor": 0.7}}},
    }))
    node_ids = set(nodes["gid"])
    for row in nodes.itertuples(index=False):
        gid, role = str(row.gid), str(row.role)
        priority = float(getattr(row, "priority_score", 0) or 0)
        seed = bool_value(getattr(row, "is_seed", False))
        title = (f"gid: {gid}\n"
                 f"Роль: {theme.ROLE_LABELS.get(role, role)}\n"
                 f"Признаки: {getattr(row, 'evidence', '—')}")
        net.add_node(gid, label=gid[-6:], title=title, color={
            "background": "#ffffff" if gid == selected else theme.ROLE_COLORS.get(role, "#94a3b8"),
            "border": "#ffffff" if seed else theme.ROLE_COLORS.get(role, "#94a3b8"),
            "highlight": {"background": "#ffffff", "border": "#f8fafc"},
        }, borderWidth=5 if seed or gid == selected else 2, size=12 + 28 * max(0, priority), shape="diamond" if seed else "dot")
    visible = edges[edges["src"].isin(node_ids) & edges["dst"].isin(node_ids)].copy()
    max_sum = max(float(visible["sum_kzt"].max() or 1), 1) if not visible.empty else 1
    for row in visible.itertuples(index=False):
        amount = float(row.sum_kzt)
        net.add_edge(str(row.src), str(row.dst), value=1 + 8 * (amount / max_sum) ** 0.5,
                     title=f"{money(amount)} · переводов: {int(row.n_tx)}")
    page = net.generate_html(notebook=False)
    return page.replace(
        "</head>",
        "<style>html,body,#mynetwork{margin:0!important;padding:0!important;"
        "background:#0b1120!important;border:0!important;}</style></head>",
    )


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
    components.html(graph_html(shown, edges, gid), height=680, scrolling=False)
