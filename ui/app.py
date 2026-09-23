"""Русский интерфейс AML-графа: ``streamlit run ui/app.py``."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Граф денег", page_icon="🔎", layout="wide")

from ui.aml import assistant, card, data, explain, graph, theme  # noqa: E402

TAB_HOME = "🏠 Кого проверять первым"
TAB_NETWORK = "🕸️ Сеть"
TAB_TOP = "📋 Топ приоритетов"
TAB_CLUSTERS = "🧩 Кластеры"
TAB_AI = "🤖 AI-ассистент"
TAB_HOWTO = "📘 Как это работает"
TAB_LABELS = [TAB_HOME, TAB_NETWORK, TAB_TOP, TAB_CLUSTERS, TAB_AI, TAB_HOWTO]
KEY_ROLES = {"coordinator", "consolidator", "distributor"}

try:
    nodes, top, clusters, edges = data.load_data()
except Exception as exc:
    st.error(f"Не удалось загрузить данные графа: {exc}")
    st.stop()

st.markdown(theme.GLOBAL_CSS, unsafe_allow_html=True)
st.title("🔎 Граф денег")
st.caption("Роли и связи — аналитические признаки для проверки, а не утверждение о виновности.")

if "gid_search" not in st.session_state:
    st.session_state.gid_search = ""
if "top_gid" not in st.session_state:
    st.session_state.top_gid = ""


def reset_selection() -> None:
    st.session_state.gid_search = ""
    st.session_state.top_gid = ""


def go_network() -> None:
    """Ввели gid в поиске → сразу показать вкладку с карточкой и графом."""
    if st.session_state.gid_search.strip():
        st.session_state.main_tab = TAB_NETWORK


def select_top_gid() -> None:
    if st.session_state.top_gid:
        st.session_state.gid_search = st.session_state.top_gid


with st.sidebar:
    st.header("Поиск узла")
    st.text_input("Найти по GID", key="gid_search", placeholder="100000…", on_change=go_network)
    st.button("Сбросить выбор", on_click=reset_selection, width="stretch")
    st.header("Фильтры сети")
    roles = st.multiselect("Роли", list(theme.ROLE_LABELS), default=list(theme.ROLE_LABELS), format_func=lambda x: theme.ROLE_LABELS[x])
    cluster_values = sorted(int(x) for x in nodes["cluster_id"].dropna().unique())
    cluster_choice = st.selectbox("Кластер", ["Все"] + cluster_values)
    depth = st.radio("Глубина окрестности", [1, 2], horizontal=True)

role_counts_all = nodes["role"].value_counts()

try:
    tab_home, tab_network, tab_top, tab_clusters, tab_ai, tab_howto = st.tabs(
        TAB_LABELS, key="main_tab", default=TAB_HOME, on_change="rerun",
    )
    tabs_switchable = True
except TypeError:
    tab_home, tab_network, tab_top, tab_clusters, tab_ai, tab_howto = st.tabs(TAB_LABELS)
    tabs_switchable = False


def open_node(gid: str) -> None:
    st.session_state.gid_search = gid
    if tabs_switchable:
        st.session_state.main_tab = TAB_NETWORK
    else:
        st.session_state._open_node_fallback = True


with tab_home:
    seed_count = int(nodes["is_seed"].map(data.bool_value).sum())
    node_count = len(nodes)
    key_role_count = int(nodes["role"].isin(KEY_ROLES).sum())

    st.markdown(
        f"Сеть — переводы клиентов банка от **{seed_count}** известных seed-клиентов "
        f"до 4-го колена, **{node_count:,}**".replace(",", " ") + " узлов.  \n"
        "Инструмент по правилам определяет роли узлов и порядок проверки — "
        "это гипотезы для проверки, а не обвинения."
    )

    report = data.load_report()
    resilience_20 = next((r for r in report["resilience"] if r["removed_top"] == 20), None)
    if resilience_20 and report["base_component"]:
        removal_value = f"{resilience_20['components']} частей"
        removal_help = f"крупнейшая компонента {report['base_component']} → {resilience_20['largest_component']} узлов"
    else:
        removal_value = "—"
        removal_help = "Отчёт пайплайна недоступен (outputs/report.md)"

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Узлов в сети", f"{node_count:,}".replace(",", " "))
    m2.metric("Известных seed", seed_count)
    m3.metric(
        "Ключевых узлов", key_role_count,
        help="Координаторы, консолидаторы и распределители — узлы с наибольшим влиянием на потоки",
    )
    m4.metric("Изъятие топ-20", removal_value, help=removal_help)

    if st.session_state.pop("_open_node_fallback", False):
        st.success("Карточка открыта во вкладке «Сеть»")

    st.subheader("Топ-10 по приоритету проверки")
    for _, trow in top.head(10).iterrows():
        gid = str(trow["gid"])
        with st.container(border=True):
            c_rank, c_gid, c_role, c_prio, c_why, c_btn = st.columns([0.6, 2.3, 1.6, 1.3, 3.6, 1.1])
            c_rank.markdown(f"**#{int(trow['rank'])}**")
            c_gid.markdown(f"`{gid}`")
            c_role.markdown(theme.role_badge(str(trow["role"])), unsafe_allow_html=True)
            priority = float(trow["priority_score"])
            c_prio.progress(min(max(priority, 0.0), 1.0), text=f"{priority:.2f}")
            c_why.caption(data.short_why(trow["why"]))
            c_btn.button("Открыть", key=f"open_{gid}", on_click=open_node, args=(gid,), width="stretch")

with tab_network:
    cols = st.columns(5)
    cols[0].metric("Узлов", f"{len(nodes):,}".replace(",", " "))
    cols[1].metric("Seed", int(nodes["is_seed"].map(data.bool_value).sum()))
    cols[2].metric("Оборот", data.money(edges["sum_kzt"].sum()))
    cols[3].metric("Ключевых узлов", int(nodes["role"].isin(KEY_ROLES).sum()))
    cols[4].metric("Координаторов", int(role_counts_all.get("coordinator", 0)))
    selected = st.session_state.gid_search.strip() or None
    if selected:
        step_word = "шаг" if depth == 1 else "шага"
        st.subheader(f"Окружение узла {selected} ({depth} {step_word})")
    else:
        st.subheader("Схема сети: топ-50 узлов по приоритету")
    if selected and selected not in set(nodes["gid"]):
        st.warning(f"GID {selected} не найден. Проверьте число без пробелов.")
    elif selected:
        col_card, col_graph = st.columns([5, 6])
        with col_card:
            card.render_node_card(selected, nodes, edges, where="network")
        with col_graph:
            st.markdown(theme.legend_html(role_counts_all), unsafe_allow_html=True)
            graph.render_network(nodes, edges, selected, roles, None if cluster_choice == "Все" else int(cluster_choice), depth)
    else:
        st.markdown(theme.legend_html(role_counts_all), unsafe_allow_html=True)
        graph.render_network(nodes, edges, selected, roles, None if cluster_choice == "Все" else int(cluster_choice), depth)

with tab_top:
    st.subheader("Узлы с наивысшим приоритетом проверки")
    st.dataframe(top, hide_index=True, width="stretch")
    chosen_top = st.selectbox(
        "Открыть карточку", [""] + top["gid"].astype(str).tolist(),
        key="top_gid", on_change=select_top_gid,
    )
    if chosen_top:
        card.render_node_card(chosen_top, nodes, edges, where="top")

def select_cluster_row(table: pd.DataFrame, key: str):
    """Колбэк для клика по строке таблицы кластеров: переводит cluster_gid на выбранный кластер."""
    def _navigate() -> None:
        state = st.session_state.get(key)
        rows = getattr(getattr(state, "selection", None), "rows", None) if state is not None else None
        if rows:
            idx = rows[0]
            if 0 <= idx < len(table):
                st.session_state["cluster_gid"] = int(table.iloc[idx]["№ кластера"])
    return _navigate


with tab_clusters:
    st.subheader("Кластеры и рабочие гипотезы")
    st.caption(
        "Кластер — группа узлов, которые переводят деньги в основном друг другу "
        "(алгоритм Louvain по суммам переводов). Гипотеза — что в группе видно по ролям."
    )
    clusters_table = data.format_clusters_table(clusters)
    st.dataframe(
        clusters_table, hide_index=True, width="stretch", key="clusters_table",
        on_select=select_cluster_row(clusters_table, "clusters_table"), selection_mode="single-row",
        column_config={"гипотеза": st.column_config.TextColumn("гипотеза", width="large")},
    )

    cluster_info = clusters.set_index("cluster_id")

    def _cluster_option_label(cid: int) -> str:
        if cid not in cluster_info.index:
            return f"#{cid}"
        crow = cluster_info.loc[cid]
        return f"#{cid} — {int(crow['n_nodes'])} узлов, {int(crow['n_seed'])} seed"

    chosen_cluster = st.selectbox(
        "Показать кластер", cluster_values, key="cluster_gid", format_func=_cluster_option_label,
    )
    cid = int(chosen_cluster)
    cluster_nodes = nodes[nodes["cluster_id"] == cid]
    crow = cluster_info.loc[cid] if cid in cluster_info.index else None

    m1, m2, m3 = st.columns(3)
    m1.metric("Узлов", len(cluster_nodes))
    m2.metric("Seed", int(cluster_nodes["is_seed"].map(data.bool_value).sum()))
    m3.metric("Оборот внутри", data.money(crow["sum_kzt_internal"]) if crow is not None else "—")

    st.markdown(
        f"<div class='aml-legend'>{theme.role_chips_html(cluster_nodes['role'].value_counts())}</div>",
        unsafe_allow_html=True,
    )
    st.info(crow["hypothesis"] if crow is not None else "Гипотеза недоступна")

    graph.render_network(nodes, edges, None, roles, cid, depth)

    st.markdown("##### Топ-узлы кластера")
    top_in_cluster = cluster_nodes.nlargest(5, "priority_score")
    if top_in_cluster.empty:
        st.caption("Нет узлов в кластере")
    else:
        for _, ctrow in top_in_cluster.iterrows():
            cgid = str(ctrow["gid"])
            with st.container(border=True):
                c_gid, c_role, c_prio, c_btn = st.columns([2.5, 1.8, 1.5, 1.2])
                c_gid.markdown(f"`{cgid}`")
                c_role.markdown(theme.role_badge(str(ctrow["role"])), unsafe_allow_html=True)
                cpriority = float(ctrow["priority_score"])
                c_prio.progress(min(max(cpriority, 0.0), 1.0), text=f"{cpriority:.2f}")
                c_btn.button("Открыть", key=f"cl_open_{cgid}", on_click=open_node, args=(cgid,), width="stretch")

with tab_ai:
    assistant.render(nodes, top, open_node)

with tab_howto:
    explain.render_how_it_works(nodes)
