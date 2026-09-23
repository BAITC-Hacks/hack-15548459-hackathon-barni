"""Экран GraphAML: сеть + поиск узла + карточка + топ/кластеры.
Запуск: streamlit run ui/viewer.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import networkx as nx  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402

from pipeline.cards import init as cards_init  # noqa: E402
from pipeline.clusters import RU  # noqa: E402
from pipeline.metrics import build_graph  # noqa: E402
from ui.aml.card import render_node_card  # noqa: E402
from ui.aml.graph import graph_html  # noqa: E402
from ui.aml.theme import GLOBAL_CSS, ROLE_COLORS  # noqa: E402

# ── палитра ролей ────────────────────────────────────────────────────────────
COLORS = ROLE_COLORS
MAX_NODES = 300
DEFAULT_TOP_N = 50


# ── загрузка данных ──────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    nodes_path = ROOT / "outputs" / "nodes_roles.csv"
    top_path = ROOT / "outputs" / "top_nodes.csv"
    clusters_path = ROOT / "outputs" / "clusters.csv"
    edges_path = ROOT / "data" / "edges.parquet"
    if not (nodes_path.exists() and top_path.exists() and clusters_path.exists() and edges_path.exists()):
        return None
    df = pd.read_csv(nodes_path, dtype={"gid": "int64"})
    top = pd.read_csv(top_path, dtype={"gid": "int64"})
    clusters = pd.read_csv(clusters_path)
    edges = pd.read_parquet(edges_path)
    edges["src"] = edges["src"].astype("int64")
    edges["dst"] = edges["dst"].astype("int64")
    return df, top, clusters, edges


@st.cache_resource
def build_nx_graph(_edges, _gids):
    G = build_graph(_edges, pd.DataFrame({"gid": _gids}))
    return G


def parse_gid(text):
    """Пытается распарсить gid из строки поиска. Возвращает (gid|None, ошибка|None)."""
    text = (text or "").strip()
    if not text:
        return None, None
    try:
        return int(text), None
    except ValueError:
        return None, "bad_format"


def cap_by_priority(gids, df, keep, cap=MAX_NODES):
    """Обрезает список gid до cap штук по приоритету (ties gid asc), но всегда оставляет keep."""
    sub = df[df.gid.isin(gids)].sort_values(["priority_score", "gid"], ascending=[False, True])
    ordered = sub.gid.tolist()
    if len(ordered) <= cap:
        return set(ordered), False
    keep_set = set(keep)
    keep_ordered = [gid for gid in ordered if gid in keep_set]
    # Reserve room for selected/context nodes instead of adding them after a full cap.
    preserved = keep_ordered[:cap]
    preserved_set = set(preserved)
    head = preserved + [gid for gid in ordered if gid not in preserved_set][:cap - len(preserved)]
    return set(head), len(head) < len(ordered)


def neighborhood(G, gid, radius):
    """Соседи узла gid в обе стороны до radius шагов (по ненаправленной версии графа)."""
    if gid not in G:
        return set()
    UG = G.to_undirected(as_view=True)
    lengths = nx.single_source_shortest_path_length(UG, gid, cutoff=radius)
    return set(lengths.keys())


def make_graph_html(gids, df, edges, selected_gid=None, height_px=650):
    """Строит общий тёмный граф, сохраняя целочисленные gid пайплайна."""
    sub = df[df.gid.isin(gids)]
    if sub.empty:
        return "<p>После фильтрации не осталось узлов.</p>"
    nodes = sub.copy()
    nodes["gid"] = nodes["gid"].astype(str)
    edge_rows = edges.copy()
    edge_rows["src"] = edge_rows["src"].astype(str)
    edge_rows["dst"] = edge_rows["dst"].astype(str)
    return graph_html(nodes, edge_rows, None if selected_gid is None else str(selected_gid))


# ── страница ──────────────────────────────────────────────────────────────────
st.set_page_config(page_title="GraphAML", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

loaded = load_data()
if loaded is None:
    st.error("Сначала запустите: python run_pipeline.py")
    st.stop()
df, top_df, clusters_df, edges_df = loaded
G = build_nx_graph(edges_df, df.gid.tolist())
cards_init(df, G)
total_nodes = len(df)
all_gids = set(df.gid)

if "gid" not in st.session_state:
    st.session_state["gid"] = None


# ── выбор узла: один источник правды st.session_state["gid"], поле поиска синхронно с ним ──
def select_gid(gid):
    st.session_state["gid"] = gid
    st.session_state["search"] = "" if gid is None else str(gid)


def on_search():
    gid, _ = parse_gid(st.session_state.get("search", ""))
    if not st.session_state.get("search", "").strip():
        st.session_state["gid"] = None  # поле очищено → общий вид
    else:  # не найден / неверный формат → сбросить, чтобы карточка не расходилась с полем поиска
        st.session_state["gid"] = gid if gid in all_gids else None


def on_top_select():
    rows = st.session_state["top_table"].selection.rows
    if rows:
        select_gid(int(top_df.iloc[rows[0]].gid))

st.title("GraphAML")
st.subheader("Схема сети")
st.caption("Роли — гипотезы для проверки, а не обвинения.")

# ── сайдбар: поиск + фильтры ──────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Легенда")
    for role, color in COLORS.items():
        st.markdown(
            f'<span style="display:inline-block;width:12px;height:12px;background:{color};'
            f'border-radius:50%;margin-right:6px;"></span>{RU.get(role, role)}',
            unsafe_allow_html=True,
        )
    st.caption("Ромб с белой рамкой — seed; светлый узел — выбранный узел; "
               "стрелка — направление денег, толщина — сумма, размер — приоритет.")
    st.divider()

    st.subheader("Поиск узла")
    search_text = st.text_input("gid", key="search", on_change=on_search)
    radius = st.radio("Радиус соседства", options=[1, 2], horizontal=True, index=0)
    st.button("Сбросить выбор", on_click=select_gid, args=(None,), use_container_width=True)

    if search_text.strip():
        gid_parsed, err = parse_gid(search_text)
        if err == "bad_format":
            st.warning("Некорректный формат gid — введите целое число.")
        elif gid_parsed is not None and gid_parsed not in all_gids:
            st.warning(f"Узел {gid_parsed} не найден в выборке ({total_nodes} узлов). Проверьте gid.")
    if st.session_state.get("gid") is not None:
        st.caption(f"Выбран узел: {st.session_state['gid']}")

    st.divider()
    st.subheader("Фильтры")
    all_roles = sorted(df.role.unique())
    sel_roles = st.multiselect("Роли", options=all_roles, default=all_roles,
                                format_func=lambda r: RU.get(r, r))
    sel_clusters = st.multiselect("Кластер", options=sorted(df.cluster_id.unique()), default=[])
    sel_depth = st.multiselect("Колено", options=sorted(df.depth.unique()), default=sorted(df.depth.unique()))


def apply_filters(base_df, keep_gid=None):
    mask = base_df.role.isin(sel_roles) & base_df.depth.isin(sel_depth)
    if sel_clusters:
        mask &= base_df.cluster_id.isin(sel_clusters)
    filtered = base_df[mask]
    if keep_gid is not None and keep_gid not in set(filtered.gid) and keep_gid in set(base_df.gid):
        filtered = pd.concat([filtered, base_df[base_df.gid == keep_gid]])
    return filtered


def display_frame(frame, labels):
    """Локализует известные названия столбцов и роли, не меняя исходные данные."""
    shown = frame.copy()
    if "role" in shown.columns:
        shown["role"] = shown["role"].map(lambda role: RU.get(role, role))
    shown = shown.rename(columns={name: labels[name] for name in shown.columns if name in labels})
    return shown


TABLE_LABELS = {
    "gid": "GID", "role": "Роль", "priority_score": "Приоритет",
    "role_score": "Оценка роли", "evidence": "Признаки", "why": "Обоснование",
    "cluster_id": "Кластер", "depth": "Колено", "in_kzt": "Получено",
    "out_kzt": "Отправлено", "in_deg": "Плательщиков", "out_deg": "Получателей",
    "sum_kzt": "Сумма, ₸", "n_tx": "Переводов", "size": "Узлов",
    "top_gids": "Топ GID",
}


def render_card_and_graph(gid, radius_hops, key_suffix=""):
    """Рисует карточку узла + граф его окрестности. Общий блок для нескольких вкладок."""
    if gid is None:
        st.info("Выберите узел: поиск слева, строка в «Топ приоритетов» или узел во вкладке «Кластеры».")
        return
    if gid not in set(df.gid):
        st.warning(f"Узел {gid} не найден в выборке ({total_nodes} узлов). Проверьте gid.")
        return

    row = df.loc[df.gid == gid].iloc[0]
    st.caption(f"Выбранный узел · GID {gid} · {RU.get(row.role, row.role)} · кластер {int(row.cluster_id)}")
    ui_nodes = df.copy()
    ui_nodes["gid"] = ui_nodes["gid"].astype(str)
    ui_edges = edges_df.copy()
    ui_edges["src"] = ui_edges["src"].astype(str)
    ui_edges["dst"] = ui_edges["dst"].astype(str)
    render_node_card(str(gid), ui_nodes, ui_edges, where=f"legacy_{key_suffix or 'graph'}")

    nb = neighborhood(G, gid, radius_hops) | {gid}
    nb = set(apply_filters(df, keep_gid=gid).gid) & nb | {gid}
    shown, truncated = cap_by_priority(nb, df, keep={gid})
    if truncated:
        st.caption(f"Окрестность: показано {len(shown)} из {len(nb)} узлов; лимит {MAX_NODES}, узел {gid} сохранён.")
    else:
        st.caption(f"Окрестность узла: {len(shown)} узлов · радиус {radius_hops}")
    html = make_graph_html(shown, df, edges_df, selected_gid=gid)
    components.html(html, height=680, scrolling=False)


tab_graph, tab_top, tab_clusters = st.tabs(["Схема сети", "Топ приоритетов", "Кластеры"])

with tab_graph:
    gid_sel = st.session_state.get("gid")
    if gid_sel is not None and gid_sel in set(df.gid):
        render_card_and_graph(gid_sel, radius)
    else:
        filtered = apply_filters(df)
        top_gids = (filtered.sort_values(["priority_score", "gid"], ascending=[False, True])
                    .head(DEFAULT_TOP_N).gid.tolist())
        shown, truncated = cap_by_priority(set(top_gids), df, keep=set())
        if not shown:
            st.info("По выбранным фильтрам узлы не найдены. Измените роль, кластер или колено.")
        else:
            if truncated:
                st.caption(f"Схема: показано {len(shown)} из {len(top_gids)} узлов; лимит {MAX_NODES}.")
            else:
                st.caption(f"Показаны {len(shown)} узлов из топа по приоритету с учётом фильтров.")
            components.html(make_graph_html(shown, df, edges_df), height=680, scrolling=False)
            st.caption("Выберите узел поиском слева или строку в таблице топа, чтобы открыть карточку.")

with tab_top:
    st.subheader("Топ приоритетов")
    display_top = top_df.copy()
    display_top["gid"] = display_top["gid"].astype(str)
    st.dataframe(display_frame(display_top, TABLE_LABELS), hide_index=True, use_container_width=True,
                 on_select=on_top_select, selection_mode="single-row", key="top_table")
    st.divider()
    render_card_and_graph(st.session_state.get("gid"), radius, key_suffix="top")

with tab_clusters:
    st.subheader("Кластеры")
    st.dataframe(display_frame(clusters_df, TABLE_LABELS), hide_index=True, use_container_width=True)
    st.divider()
    cid = st.selectbox("Кластер", options=sorted(clusters_df.cluster_id.unique()))
    cluster_gids = set(df[df.cluster_id == cid].gid)
    shown, truncated = cap_by_priority(cluster_gids, df, keep=set())
    if not shown:
        st.info("В этом кластере нет узлов для отображения.")
    else:
        if truncated:
            st.caption(f"Кластер: показано {len(shown)} из {len(cluster_gids)} узлов; лимит {MAX_NODES}.")
        components.html(make_graph_html(shown, df, edges_df), height=680, scrolling=False)
    top_gids_row = clusters_df.loc[clusters_df.cluster_id == cid, "top_gids"].iloc[0]
    cl_top = [int(g) for g in str(top_gids_row).split(";") if g.strip()]
    st.markdown("**Топ gid кластера:** " + ", ".join(map(str, cl_top)))
    if cl_top:
        pick = st.selectbox("Узел кластера", options=cl_top, format_func=str, key="cluster_pick")
        st.button("Показать карточку узла", on_click=select_gid, args=(pick,))
        st.caption("Карточка откроется во вкладках «Схема сети» и «Топ приоритетов».")
