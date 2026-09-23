"""Кластеры: Louvain на НЕНАПРАВЛЕННОЙ проекции, вес = сумма переводов (оговорено в README),
фиксированный seed → воспроизводимо. Узлы без рёбер — отдельные кластеры."""
import networkx as nx
import pandas as pd

from .config import THRESHOLDS as T
from .roles import kzt

RU = {"consolidator": "консолидатор", "transit": "транзит", "distributor": "распределитель",
      "terminal": "конечный", "coordinator": "координатор", "peripheral": "периферия"}


def build(G):
    UG = nx.Graph()
    UG.add_nodes_from(G.nodes)
    for u, v, d in G.edges(data=True):
        w = UG[u][v]["weight"] + d["sum_kzt"] if UG.has_edge(u, v) else d["sum_kzt"]
        UG.add_edge(u, v, weight=w)
    comms = nx.community.louvain_communities(UG, weight="weight", seed=T["louvain_seed"])
    comms = sorted(comms, key=lambda c: (-len(c), min(c)))
    return {g: i for i, c in enumerate(comms) for g in c}


def hypothesis(sub, internal):
    n = len(sub)
    rc = sub.role.value_counts()
    seeds = int(sub.is_seed.sum())
    if n == 1:
        return "Одиночный узел без связей внутри выборки"
    k, d, t, c = (rc.get(x, 0) for x in ("consolidator", "distributor", "transit", "coordinator"))
    trunc = int(sub.truncated.sum())
    parts = []
    if c:
        parts.append(f"{c} координатор(а) связывают ветки")
    if k and d:
        parts.append(f"схема «сбор → раздача»: {k} точ. консолидации и {d} распределител.")
    elif k:
        parts.append(f"признаки сбора средств в {k} точ. консолидации")
    elif d:
        parts.append(f"признаки веерного распределения ({d} узл.)")
    if t:
        parts.append(f"{t} транзитных счетов")
    if not parts:
        parts.append("структура периферийная, выраженных ролей нет")
    tail = f"; {seeds} seed, оборот {kzt(internal)}"
    if trunc / n > 0.4:
        tail += f"; {trunc} узл. на обрыве выгрузки — картина неполная"
    return ("Гипотеза: " + "; ".join(parts) + tail)[:300]


def table(G, df):
    rows = []
    for cid, sub in df.groupby("cluster_id"):
        members = set(sub.gid)
        internal = sum(d["sum_kzt"] for u, v, d in G.edges(data=True) if u in members and v in members)
        top = sub.sort_values(["priority_score", "gid"], ascending=[False, True]).gid.head(5)
        rows.append({"cluster_id": cid, "n_nodes": len(sub), "n_seed": int(sub.is_seed.sum()),
                     "sum_kzt_internal": round(internal, 2),
                     "top_gids": ";".join(map(str, top)),
                     "hypothesis": hypothesis(sub, internal)})
    return pd.DataFrame(rows).sort_values("cluster_id")
