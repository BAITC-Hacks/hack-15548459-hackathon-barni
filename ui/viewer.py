"""Экран схемы сети: GraphAML (pyvis) + поиск узла + карточка + топ/кластеры.
Запуск: streamlit run ui/viewer.py"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import networkx as nx  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
from pyvis.network import Network  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402

from pipeline.cards import node_card, init as cards_init  # noqa: E402
from pipeline.clusters import RU  # noqa: E402
from pipeline.metrics import build_graph  # noqa: E402
from pipeline.roles import kzt  # noqa: E402

# ── палитра ролей ────────────────────────────────────────────────────────────
COLORS = {
    "coordinator": "#e74c3c", "consolidator": "#e67e22", "distributor": "#9b59b6",
    "transit": "#3498db", "terminal": "#2ecc71", "peripheral": "#95a5a6",
}
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
    keep = set(keep)
    sub = df[df.gid.isin(gids)].sort_values(["priority_score", "gid"], ascending=[False, True])
    ordered = sub.gid.tolist()
    if len(ordered) <= cap:
        return set(ordered), False
    head = set(ordered[:cap]) | keep
    return head, len(head) < len(ordered)


def neighborhood(G, gid, radius):
    """Соседи узла gid в обе стороны до radius шагов (по ненаправленной версии графа)."""
    if gid not in G:
        return set()
    UG = G.to_undirected(as_view=True)
    lengths = nx.single_source_shortest_path_length(UG, gid, cutoff=radius)
    return set(lengths.keys())


def make_graph_html(gids, df, edges, selected_gid=None, height_px=650):
    """Строит pyvis-граф по набору gid: направленные рёбра, цвет по роли, размер по приоритету."""
    sub = df[df.gid.isin(gids)]
    if sub.empty:
        return "<p>Нет узлов для отображения.</p>"
    gid_set = set(sub.gid)
    e = edges[edges.src.isin(gid_set) & edges.dst.isin(gid_set)]
    max_sum = float(e.sum_kzt.max()) if not e.empty else 1.0

    net = Network(height=f"{height_px}px", width="100%", directed=True, cdn_resources="in_line",
                  bgcolor="#ffffff", font_color="#222222")
    net.barnes_hut(gravity=-8000, central_gravity=0.3, spring_length=120, damping=0.9)
    net.set_options('{"physics": {"stabilization": {"iterations": 120}}}')

    for r in sub.itertuples():
        nid = str(r.gid)
        color = COLORS.get(r.role, COLORS["peripheral"])
        size = 10 + 30 * float(r.priority_score)
        title = "\n".join([
            f"gid: {r.gid}",
            f"роль: {RU.get(r.role, r.role)} ({r.rule})",
            f"приоритет: {r.priority_score:.2f}",
            f"{r.evidence}",
        ])
        border_w = 1
        shape = "dot"
        if bool(r.is_seed):
            border_w = 4
            shape = "star"
            color = {"background": color, "border": "#f1c40f"}
        if r.gid == selected_gid:  # выбранный узел: чёрная рамка (seed остаётся звездой)
            border_w = 5
            color = {"background": color["background"] if isinstance(color, dict) else color,
                     "border": "#000000"}
        net.add_node(nid, label=str(r.gid)[-6:], title=title, color=color, size=size,
                     borderWidth=border_w, shape=shape)

    for r in e.itertuples():
        w = 1 + 6 * math.log1p(r.sum_kzt) / math.log1p(max_sum) if max_sum > 0 else 1
        title = f"{kzt(r.sum_kzt)}, {r.n_tx} переводов"
        net.add_edge(str(r.src), str(r.dst), value=w, title=title, arrows="to")

    return net.generate_html()


# ── страница ──────────────────────────────────────────────────────────────────
st.set_page_config(page_title="GraphAML", page_icon="🕸️", layout="wide")

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

st.title("GraphAML — схема сети")
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
    st.caption("★ с жёлтой рамкой — seed; чёрная рамка — выбранный узел; "
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


def render_card_and_graph(gid, radius_hops, key_suffix=""):
    """Рисует карточку узла + граф его окрестности. Общий блок для нескольких вкладок."""
    if gid is None:
        st.info("Выберите узел: поиск слева, строка в «Топ приоритетов» или узел во вкладке «Кластеры».")
        return
    if gid not in set(df.gid):
        st.warning(f"Узел {gid} не найден в выборке ({total_nodes} узлов). Проверьте gid.")
        return

    row = df.loc[df.gid == gid].iloc[0]
    st.markdown(node_card(gid))

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Роль", RU.get(row.role, row.role))
    c2.metric("Приоритет", f"{row.priority_score:.2f}")
    c3.metric("Получено", kzt(row.in_kzt))
    c4.metric("Отдано", kzt(row.out_kzt))
    c5.metric("Колено", int(row.depth))
    c6.metric("Кластер", int(row.cluster_id))

    badges = []
    if row.get("n_cycles", 0) and row.n_cycles > 0:
        badges.append(f"🔁 циклы: {int(row.n_cycles)}")
    if row.get("n_fast_chains", 0) and row.n_fast_chains > 0:
        badges.append(f"⚡ быстрый проброс: {int(row.n_fast_chains)}")
    if row.get("split_flag", False):
        badges.append("✂️ дробление")
    if row.get("anomaly_z", 0) and row.anomaly_z >= 3:
        badges.append(f"📈 аномалия z={row.anomaly_z:.1f}")
    if badges:
        chips = " ".join(
            f'<span style="background:#eef2f7;border-radius:12px;padding:3px 10px;margin-right:6px;'
            f'font-size:0.85em;">{b}</span>' for b in badges
        )
        st.markdown(chips, unsafe_allow_html=True)

    if bool(row.truncated):
        st.warning("Обрыв выгрузки на 4-м колене: исходящие не выгружены — это не конечный получатель, "
                    "нужна доп. выгрузка")

    payers = edges_df[edges_df.dst == gid].merge(
        df[["gid", "role"]], left_on="src", right_on="gid", how="left"
    )[["src", "role", "sum_kzt", "n_tx"]].rename(columns={"src": "gid", "role": "роль",
                                                            "sum_kzt": "сумма", "n_tx": "переводов"})
    payers = payers.sort_values("сумма", ascending=False)
    payers["gid"] = payers["gid"].astype(str)
    receivers = edges_df[edges_df.src == gid].merge(
        df[["gid", "role"]], left_on="dst", right_on="gid", how="left"
    )[["dst", "role", "sum_kzt", "n_tx"]].rename(columns={"dst": "gid", "role": "роль",
                                                            "sum_kzt": "сумма", "n_tx": "переводов"})
    receivers = receivers.sort_values("сумма", ascending=False)
    receivers["gid"] = receivers["gid"].astype(str)

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**От кого получил**")
        st.dataframe(payers, hide_index=True, use_container_width=True)
    with col_b:
        st.markdown("**Кому отправил**")
        st.dataframe(receivers, hide_index=True, use_container_width=True)

    nb = neighborhood(G, gid, radius_hops) | {gid}
    nb = set(apply_filters(df, keep_gid=gid).gid) & nb | {gid}
    shown, truncated = cap_by_priority(nb, df, keep={gid})
    if truncated:
        st.caption(f"Окрестность обрезана до {MAX_NODES} узлов по приоритету.")
    html = make_graph_html(shown, df, edges_df, selected_gid=gid)
    components.html(html, height=650, scrolling=False)


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
        if truncated:
            st.caption(f"Вид обрезан до {MAX_NODES} узлов по приоритету.")
        html = make_graph_html(shown, df, edges_df)
        components.html(html, height=650, scrolling=False)
        st.caption(f"Показаны топ-{DEFAULT_TOP_N} узлов по приоритету (с учётом фильтров). "
                   "Выберите узел через поиск слева, чтобы увидеть карточку.")

with tab_top:
    st.subheader("Топ приоритетов")
    display_top = top_df.copy()
    display_top["gid"] = display_top["gid"].astype(str)
    st.dataframe(display_top, hide_index=True, use_container_width=True,
                 on_select=on_top_select, selection_mode="single-row", key="top_table")
    st.divider()
    render_card_and_graph(st.session_state.get("gid"), radius, key_suffix="top")

with tab_clusters:
    st.subheader("Кластеры")
    st.dataframe(clusters_df, hide_index=True, use_container_width=True)
    st.divider()
    cid = st.selectbox("Кластер", options=sorted(clusters_df.cluster_id.unique()))
    cluster_gids = set(df[df.cluster_id == cid].gid)
    shown, truncated = cap_by_priority(cluster_gids, df, keep=set())
    if truncated:
        st.caption(f"Кластер обрезан до {MAX_NODES} узлов по приоритету.")
    html = make_graph_html(shown, df, edges_df)
    components.html(html, height=650, scrolling=False)
    top_gids_row = clusters_df.loc[clusters_df.cluster_id == cid, "top_gids"].iloc[0]
    cl_top = [int(g) for g in str(top_gids_row).split(";") if g.strip()]
    st.markdown("**Топ gid кластера:** " + ", ".join(map(str, cl_top)))
    if cl_top:
        pick = st.selectbox("Узел кластера", options=cl_top, format_func=str, key="cluster_pick")
        st.button("Показать карточку узла", on_click=select_gid, args=(pick,))
        st.caption("Карточка откроется во вкладках «Схема сети» и «Топ приоритетов».")
