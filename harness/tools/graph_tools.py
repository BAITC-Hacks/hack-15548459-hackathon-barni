"""Инструменты AI-ассистента для анализа направленного графа денег."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import networkx as nx
import pandas as pd

from . import tool

ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def _data() -> tuple[pd.DataFrame, pd.DataFrame]:
    nodes = pd.read_csv(ROOT / "outputs" / "nodes_roles.csv", dtype={"gid": "string"})
    edges = pd.read_parquet(ROOT / "data" / "edges.parquet")
    edges["src"] = edges["src"].astype("string")
    edges["dst"] = edges["dst"].astype("string")
    return nodes, edges


def _gid(value: str | int) -> str:
    return str(value).strip()


@tool
def node_card(gid: str) -> dict:
    """Возвращает роль, признаки и ключевые метрики узла. Вызывай, чтобы объяснить роль конкретного gid.

    Args:
        gid: Полный идентификатор узла без пробелов.
    """
    nodes, _ = _data()
    found = nodes[nodes["gid"] == _gid(gid)]
    if found.empty:
        raise ValueError(f"gid {gid} не найден")
    fields = ["gid", "role", "rule", "role_score", "priority_score", "evidence", "cluster_id", "depth", "is_seed", "in_deg", "out_deg", "in_kzt", "out_kzt", "in_tx", "out_tx", "pass_through", "fast_share", "seed_payers", "seeds_2hop", "truncated"]
    row = found.iloc[0]
    return {key: row[key] for key in fields if key in row.index}


@tool
def neighbors(gid: str, depth: int = 1, direction: str = "both") -> list[dict]:
    """Показывает входящие и/или исходящие связи gid с суммами, включая окрестность до двух шагов.

    Args:
        gid: Полный идентификатор исходного узла.
        depth: Глубина обхода, 1 или 2.
        direction: Направление: incoming, outgoing или both.
    """
    _, edges = _data()
    if direction not in {"incoming", "outgoing", "both"}:
        raise ValueError("direction: incoming, outgoing или both")
    depth = max(1, min(int(depth), 2))
    frontier, result = {_gid(gid)}, []
    for level in range(1, depth + 1):
        mask = pd.Series(False, index=edges.index)
        if direction in {"outgoing", "both"}: mask |= edges["src"].isin(frontier)
        if direction in {"incoming", "both"}: mask |= edges["dst"].isin(frontier)
        part = edges.loc[mask]
        for row in part.itertuples(index=False):
            result.append({"level": level, "src": str(row.src), "dst": str(row.dst), "sum_kzt": float(row.sum_kzt), "n_tx": int(row.n_tx)})
        frontier = (set(part["src"]) | set(part["dst"])) - frontier
    return result


@tool
def path(src: str, dst: str) -> dict:
    """Находит кратчайший направленный путь денег от src к dst.

    Args:
        src: Gid отправителя в начале пути.
        dst: Gid получателя в конце пути.
    """
    _, edges = _data()
    graph = nx.from_pandas_edgelist(edges, "src", "dst", create_using=nx.DiGraph)
    try:
        route = nx.shortest_path(graph, _gid(src), _gid(dst))
    except (nx.NetworkXNoPath, nx.NodeNotFound) as exc:
        raise ValueError(f"Направленный путь не найден: {exc}") from exc
    return {"src": _gid(src), "dst": _gid(dst), "hops": len(route) - 1, "path": route}


@tool
def top_by_role(role: str, n: int = 10) -> list[dict]:
    """Возвращает самые приоритетные узлы заданной роли.

    Args:
        role: Код роли: coordinator, consolidator, distributor, transit, terminal или peripheral.
        n: Число результатов, от 1 до 50.
    """
    nodes, _ = _data()
    part = nodes[nodes["role"] == role].nlargest(max(1, min(int(n), 50)), "priority_score")
    if part.empty:
        raise ValueError(f"Неизвестная или пустая роль: {role}")
    return part[["gid", "role", "priority_score", "evidence", "cluster_id"]].to_dict("records")


@tool
def common_receivers(gids: str) -> list[dict]:
    """Находит получателей, которым переводили все перечисленные узлы. Используй для вопроса «кто собирает с этих gid?».

    Args:
        gids: Gid отправителей через запятую.
    """
    _, edges = _data()
    senders = [_gid(item) for item in gids.split(",") if item.strip()]
    if len(senders) < 2:
        raise ValueError("Укажите минимум два gid через запятую")
    sets = [set(edges.loc[edges["src"] == sender, "dst"]) for sender in senders]
    common = set.intersection(*sets) if sets else set()
    part = edges[edges["src"].isin(senders) & edges["dst"].isin(common)]
    result = part.groupby("dst", as_index=False).agg(sum_kzt=("sum_kzt", "sum"), n_tx=("n_tx", "sum"), n_senders=("src", "nunique"))
    return result.sort_values("sum_kzt", ascending=False).to_dict("records")

