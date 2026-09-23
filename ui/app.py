"""Русский интерфейс AML-графа: ``streamlit run ui/app.py``."""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Граф денег", page_icon="🔎", layout="wide")

from ui.aml import card, data, graph, theme  # noqa: E402

TAB_HOME = "🏠 Кого проверять первым"
TAB_NETWORK = "🕸️ Сеть"
TAB_TOP = "📋 Топ приоритетов"
TAB_CLUSTERS = "🧩 Кластеры"
TAB_AI = "🤖 AI-ассистент"
TAB_LABELS = [TAB_HOME, TAB_NETWORK, TAB_TOP, TAB_CLUSTERS, TAB_AI]
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


def select_top_gid() -> None:
    if st.session_state.top_gid:
        st.session_state.gid_search = st.session_state.top_gid


with st.sidebar:
    st.header("Фильтры сети")
    roles = st.multiselect("Роли", list(theme.ROLE_LABELS), default=list(theme.ROLE_LABELS), format_func=lambda x: theme.ROLE_LABELS[x])
    cluster_values = sorted(int(x) for x in nodes["cluster_id"].dropna().unique())
    cluster_choice = st.selectbox("Кластер", ["Все"] + cluster_values)
    depth = st.radio("Глубина окрестности", [1, 2], horizontal=True)
    st.text_input("Найти по GID", key="gid_search", placeholder="100000…")
    st.button("Сбросить выбор", on_click=reset_selection, width="stretch")

legend = " ".join(f"<span style='color:{color}'>●</span> {theme.ROLE_LABELS[role]}" for role, color in theme.ROLE_COLORS.items())
st.markdown(legend + " &nbsp; ◇ seed", unsafe_allow_html=True)

try:
    tab_home, tab_network, tab_top, tab_clusters, tab_ai = st.tabs(
        TAB_LABELS, key="main_tab", default=TAB_HOME, on_change="rerun",
    )
    tabs_switchable = True
except TypeError:
    tab_home, tab_network, tab_top, tab_clusters, tab_ai = st.tabs(TAB_LABELS)
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
    role_counts = nodes["role"].value_counts()
    cols[3].metric("Ключевых узлов", int(nodes["role"].isin(KEY_ROLES).sum()))
    cols[4].metric("Координаторов", int(role_counts.get("coordinator", 0)))
    selected = st.session_state.gid_search.strip() or None
    if selected and selected not in set(nodes["gid"]):
        st.warning(f"GID {selected} не найден. Проверьте число без пробелов.")
    else:
        graph.render_network(nodes, edges, selected, roles, None if cluster_choice == "Все" else int(cluster_choice), depth)
        if selected:
            card.render_node_card(selected, nodes, edges)

with tab_top:
    st.subheader("Узлы с наивысшим приоритетом проверки")
    st.dataframe(top, hide_index=True, width="stretch")
    chosen_top = st.selectbox(
        "Открыть карточку", [""] + top["gid"].astype(str).tolist(),
        key="top_gid", on_change=select_top_gid,
    )
    if chosen_top:
        card.render_node_card(chosen_top, nodes, edges)

with tab_clusters:
    st.subheader("Кластеры и рабочие гипотезы")
    st.dataframe(clusters, hide_index=True, width="stretch")
    chosen_cluster = st.selectbox("Показать кластер", cluster_values, key="cluster_gid")
    graph.render_network(nodes, edges, None, roles, int(chosen_cluster), depth)

with tab_ai:
    st.subheader("AI-ассистент по графу")
    if not (os.getenv("OPENAI_API_KEY") or os.getenv("NVIDIA_API_KEY")):
        st.info("AI-ассистент выключен: добавьте OPENAI_API_KEY или NVIDIA_API_KEY в .env. Остальные вкладки работают без ключа.")
    else:
        from harness.agent import Agent
        if "graph_agent" not in st.session_state:
            st.session_state.graph_agent = Agent(session_id=uuid.uuid4().hex[:12], on_event=None)
            st.session_state.graph_chat = []
        for message in st.session_state.graph_chat:
            with st.chat_message(message["role"]):
                if message.get("steps"):
                    with st.expander("Шаги агента"):
                        for step in message["steps"]:
                            st.code(json.dumps(step, ensure_ascii=False, indent=2)[:4000])
                st.markdown(message["content"])
        question = st.chat_input("Например: кто главный консолидатор?")
        if question:
            st.session_state.graph_chat.append({"role": "user", "content": question})
            steps = []
            def on_event(event):
                if event.type in {"thinking", "tool_call", "tool_result", "error"}:
                    steps.append({"type": event.type, **event.data})
            agent = st.session_state.graph_agent
            agent.on_event = on_event
            safety = ("Отвечай только по данным инструментов графа. Каждый вывод называй гипотезой для проверки, "
                      "указывай gid и никогда не утверждай виновность. Вопрос аналитика: ")
            try:
                answer = agent.run(safety + question)
            except Exception as exc:
                answer = f"Не удалось получить ответ ассистента: {exc}"
            st.session_state.graph_chat.append({"role": "assistant", "content": answer, "steps": steps})
            st.rerun()
