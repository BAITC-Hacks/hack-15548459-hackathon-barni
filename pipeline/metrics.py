"""Метрики узлов: структура графа + суммы + время (transactions)."""
import numpy as np
import pandas as pd
import networkx as nx

from .config import THRESHOLDS as T


def load(data_dir):
    edges = pd.read_parquet(data_dir / "edges.parquet")
    nodes = pd.read_parquet(data_dir / "nodes.parquet")
    tx = pd.read_parquet(data_dir / "transactions.parquet")
    tx["date"] = pd.to_datetime(tx["date"])
    return edges, nodes, tx


def build_graph(edges, nodes):
    G = nx.DiGraph()
    G.add_nodes_from(nodes.gid)  # включая 19 seed без рёбер
    for r in edges.itertuples(index=False):
        G.add_edge(r.src, r.dst, sum_kzt=float(r.sum_kzt), n_tx=int(r.n_tx))
    return G


def _fast_share(tx, days):
    """Доля исходящей суммы узла, ушедшей в течение `days` дней после входящего поступления."""
    inc = tx.groupby("dst")["date"].apply(lambda s: np.sort(s.values))
    res = {}
    for src, grp in tx.groupby("src"):
        dates_in = inc.get(src)
        if dates_in is None or len(dates_in) == 0:
            continue
        total = grp.sum_kzt.sum()
        fast = 0.0
        for d, amt in zip(grp.date.values, grp.sum_kzt.values):
            i = np.searchsorted(dates_in, d, side="right") - 1  # последнее поступление не позже d
            if i >= 0 and (d - dates_in[i]) <= np.timedelta64(days, "D"):
                fast += amt
        res[src] = fast / total if total else 0.0
    return res


def compute(edges, nodes, tx):
    G = build_graph(edges, nodes)
    seeds = set(nodes.loc[nodes.is_seed, "gid"])
    df = nodes[["gid", "depth", "is_seed"]].copy().set_index("gid")

    df["in_deg"] = pd.Series(dict(G.in_degree()))
    df["out_deg"] = pd.Series(dict(G.out_degree()))
    df["in_kzt"] = pd.Series(dict(G.in_degree(weight="sum_kzt")))
    df["out_kzt"] = pd.Series(dict(G.out_degree(weight="sum_kzt")))
    df["in_tx"] = pd.Series(dict(G.in_degree(weight="n_tx")))
    df["out_tx"] = pd.Series(dict(G.out_degree(weight="n_tx")))
    df = df.fillna(0)
    for c in ("in_deg", "out_deg", "in_tx", "out_tx"):
        df[c] = df[c].astype(int)

    # доля полученного, ушедшая дальше. Для seed не определена: их входящие не выгружены.
    df["pass_through"] = np.where((df.in_kzt > 0) & (~df.is_seed), df.out_kzt / df.in_kzt.replace(0, np.nan), np.nan)

    # Ловушка 1: лист на 4-м колене = обрыв обхода, а не «деньги осели».
    # Лист на 1–3 колене — обход шёл дальше, исходящих ≥5000 KZT у него действительно нет.
    df["truncated"] = (df.depth == 4) & (df.out_deg == 0)
    df["true_leaf"] = (df.depth < 4) & (df.out_deg == 0) & (df.in_deg > 0)

    # связь с seed
    df["seed_payers"] = [sum(p in seeds for p in G.predecessors(g)) for g in df.index]
    two_hop = {}
    for g in df.index:
        preds = set(G.predecessors(g))
        for p in list(preds):
            preds |= set(G.predecessors(p))
        two_hop[g] = len(preds & seeds)
    df["seeds_2hop"] = pd.Series(two_hop)

    # центральность на НАПРАВЛЕННОМ графе
    df["pagerank"] = pd.Series(nx.pagerank(G, weight="sum_kzt"))
    df["betweenness"] = pd.Series(nx.betweenness_centrality(G))
    hubs, auth = nx.hits(G, max_iter=500)
    df["hub"], df["authority"] = pd.Series(hubs), pd.Series(auth)

    # время: быстрый транзит и синхронные поступления
    df["fast_share"] = pd.Series(_fast_share(tx, T["transit_fast_days"])).reindex(df.index)
    sync = tx.groupby(["dst", tx.date.dt.date])["src"].nunique().groupby(level=0).max()
    df["max_payers_same_day"] = sync.reindex(df.index).fillna(0).astype(int)
    per_day = tx.groupby(["src", "dst", tx.date.dt.date]).size().groupby(level=0).max()
    df["max_tx_same_pair_day"] = per_day.reindex(df.index).fillna(0).astype(int)

    df["flow_kzt"] = df.in_kzt + df.out_kzt
    return G, df.reset_index()
