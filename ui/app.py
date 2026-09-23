"""Русский интерфейс AML-графа: ``streamlit run ui/app.py``."""
from __future__ import annotations

import html
import json
import os
import sys
import uuid
from pathlib import Path

import networkx as nx
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from pyvis.network import Network

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

NODES_PATH = ROOT / "outputs" / "nodes_roles.csv"
TOP_PATH = ROOT / "outputs" / "top_nodes.csv"
CLUSTERS_PATH = ROOT / "outputs" / "clusters.csv"
EDGES_PATH = ROOT / "data" / "edges.parquet"

ROLE_LABELS = {
    "coordinator": "Координатор", "consolidator": "Консолидатор",
    "distributor": "Распределитель", "transit": "Транзитный",
    "terminal": "Конечный", "peripheral": "Периферийный",
}
ROLE_COLORS = {
    "coordinator": "#e63946", "consolidator": "#f77f00",
    "distributor": "#fcbf49", "transit": "#457b9d",
    "terminal": "#2a9d8f", "peripheral": "#94a3b8",
}

st.set_page_config(page_title="Граф денег", page_icon="🔎", layout="wide")


@st.cache_data(show_spinner="Загружаю граф…")
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    nodes = pd.read_csv(NODES_PATH, dtype={"gid": "string"})
    top = pd.read_csv(TOP_PATH, dtype={"gid": "string"})
    clusters = pd.read_csv(CLUSTERS_PATH)
    edges = pd.read_parquet(EDGES_PATH)
    edges["src"] = edges["src"].astype("string")
    edges["dst"] = edges["dst"].astype("string")
    nodes["gid"] = nodes["gid"].astype("string")
    return nodes, top, clusters, edges


def money(value: object) -> str:
    try:
        return f"{float(value):,.0f} ₸".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def bool_value(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def neighborhood(edges: pd.DataFrame, gid: str, depth: int) -> set[str]:
    chosen, frontier = {gid}, {gid}
    for _ in range(depth):
        mask = edges["src"].isin(frontier) | edges["dst"].isin(frontier)
        nxt = set(edges.loc[mask, "src"]) | set(edges.loc[mask, "dst"])
        frontier = nxt - chosen
        chosen |= nxt
    return chosen


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
        title = (f"<b>gid:</b> {html.escape(gid)}<br><b>Роль:</b> "
                 f"{html.escape(ROLE_LABELS.get(role, role))}<br><b>Признаки:</b> "
                 f"{html.escape(str(getattr(row, 'evidence', '—')))}")
        net.add_node(gid, label=gid[-6:], title=title, color={
            "background": "#ffffff" if gid == selected else ROLE_COLORS.get(role, "#94a3b8"),
            "border": "#ffffff" if seed else ROLE_COLORS.get(role, "#94a3b8"),
            "highlight": {"background": "#ffffff", "border": "#f8fafc"},
        }, borderWidth=5 if seed or gid == selected else 2, size=12 + 28 * max(0, priority), shape="diamond" if seed else "dot")
    visible = edges[edges["src"].isin(node_ids) & edges["dst"].isin(node_ids)].copy()
    max_sum = max(float(visible["sum_kzt"].max() or 1), 1) if not visible.empty else 1
    for row in visible.itertuples(index=False):
        amount = float(row.sum_kzt)
        net.add_edge(str(row.src), str(row.dst), value=1 + 8 * (amount / max_sum) ** 0.5,
                     title=f"{money(amount)} · переводов: {int(row.n_tx)}")
    return net.generate_html(notebook=False)


def node_card(gid: str, nodes: pd.DataFrame, edges: pd.DataFrame) -> None:
    match = nodes[nodes["gid"] == gid]
    if match.empty:
        st.warning(f"GID {gid} не найден в выгрузке.")
        return
    row = match.iloc[0]
    st.subheader(f"Карточка узла {gid}")
    if bool_value(row.get("truncated", False)):
        st.error("Обрыв выгрузки на 4-м колене: исходящие не выгружены. Нужен дополнительный запрос данных.")
    st.markdown(f"**{ROLE_LABELS.get(str(row.role), row.role)}** (`{row.role}`) · правило `{row.get('rule', '—')}` · кластер `{row.get('cluster_id', '—')}`")
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
    left.dataframe(incoming.sort_values("сумма, ₸", ascending=False), hide_index=True, use_container_width=True)
    right.markdown("#### Кому отправил")
    right.dataframe(outgoing.sort_values("сумма, ₸", ascending=False), hide_index=True, use_container_width=True)


def render_network(nodes: pd.DataFrame, edges: pd.DataFrame, gid: str | None, roles: list[str], cluster: int | None, depth: int) -> None:
    if gid:
        ids = neighborhood(edges, gid, depth)
    elif cluster is not None:
        ids = set(nodes.loc[nodes["cluster_id"] == cluster, "gid"])
    else:
        ids = set(nodes.nlargest(50, "priority_score")["gid"])
    shown = nodes[nodes["gid"].isin(ids) & nodes["role"].isin(roles)]
    if shown.empty:
        st.warning("После фильтрации не осталось узлов.")
        return
    components.html(graph_html(shown, edges, gid), height=680, scrolling=False)


try:
    nodes, top, clusters, edges = load_data()
except Exception as exc:
    st.error(f"Не удалось загрузить данные графа: {exc}")
    st.stop()

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
    roles = st.multiselect("Роли", list(ROLE_LABELS), default=list(ROLE_LABELS), format_func=lambda x: ROLE_LABELS[x])
    cluster_values = sorted(int(x) for x in nodes["cluster_id"].dropna().unique())
    cluster_choice = st.selectbox("Кластер", ["Все"] + cluster_values)
    depth = st.radio("Глубина окрестности", [1, 2], horizontal=True)
    st.text_input("Найти по GID", key="gid_search", placeholder="100000…")
    st.button("Сбросить выбор", on_click=reset_selection, use_container_width=True)

legend = " ".join(f"<span style='color:{color}'>●</span> {ROLE_LABELS[role]}" for role, color in ROLE_COLORS.items())
st.markdown(legend + " &nbsp; ◇ seed", unsafe_allow_html=True)

tab_network, tab_top, tab_clusters, tab_ai = st.tabs(["Сеть", "Топ приоритетов", "Кластеры", "AI-ассистент"])

with tab_network:
    cols = st.columns(4)
    cols[0].metric("Узлов", f"{len(nodes):,}".replace(",", " "))
    cols[1].metric("Seed", int(nodes["is_seed"].map(bool_value).sum()))
    cols[2].metric("Оборот", money(edges["sum_kzt"].sum()))
    role_counts = nodes["role"].value_counts()
    cols[3].metric("Роли", " · ".join(f"{ROLE_LABELS.get(k, k)}: {v}" for k, v in role_counts.items()))
    selected = st.session_state.gid_search.strip() or None
    if selected and selected not in set(nodes["gid"]):
        st.warning(f"GID {selected} не найден. Проверьте число без пробелов.")
    else:
        render_network(nodes, edges, selected, roles, None if cluster_choice == "Все" else int(cluster_choice), depth)
        if selected:
            node_card(selected, nodes, edges)

with tab_top:
    st.subheader("Узлы с наивысшим приоритетом проверки")
    st.dataframe(top, hide_index=True, use_container_width=True)
    chosen_top = st.selectbox(
        "Открыть карточку", [""] + top["gid"].astype(str).tolist(),
        key="top_gid", on_change=select_top_gid,
    )
    if chosen_top:
        node_card(chosen_top, nodes, edges)

with tab_clusters:
    st.subheader("Кластеры и рабочие гипотезы")
    st.dataframe(clusters, hide_index=True, use_container_width=True)
    chosen_cluster = st.selectbox("Показать кластер", cluster_values, key="cluster_gid")
    render_network(nodes, edges, None, roles, int(chosen_cluster), depth)

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

