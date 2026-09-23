"""Авто-карточка узла: markdown-сводка роли, потоков, связей и признаков для проверяющего."""
from pathlib import Path

import pandas as pd

from . import metrics, patterns
from .clusters import RU
from .roles import kzt, pct

_df = None
_G = None


def init(df, G):
    """Задаёт источник данных для карточек (вызывается из run_pipeline после сборки df/G)."""
    global _df, _G
    _df, _G = df, G


def _ensure_loaded():
    """Ленивая загрузка df/G, если init() не вызывался (например, из интерактивной сессии)."""
    global _df, _G
    if _df is not None and _G is not None:
        return
    root = Path(__file__).parent.parent
    _df = pd.read_parquet(root / "outputs" / "metrics.parquet")
    edges = pd.read_parquet(root / "data" / "edges.parquet")
    nodes = pd.read_parquet(root / "data" / "nodes.parquet")
    _G = metrics.build_graph(edges, nodes)


def _top_edges(gid, direction):
    """Топ-3 соседей по сумме переводов: direction 'in' — плательщики, 'out' — получатели."""
    if direction == "in":
        items = [(u, d["sum_kzt"]) for u, _, d in _G.in_edges(gid, data=True)]
    else:
        items = [(v, d["sum_kzt"]) for _, v, d in _G.out_edges(gid, data=True)]
    items.sort(key=lambda t: (-t[1], t[0]))
    return items[:3]


def _fmt_neighbors(items, seed_map):
    if not items:
        return "нет"
    return "; ".join(f"{g}{' (seed)' if seed_map.get(g, False) else ''} — {kzt(s)}" for g, s in items)


def node_card(gid):
    """Markdown-карточка узла gid: роль, потоки, связи, на что обратить внимание."""
    _ensure_loaded()
    try:
        gid = int(gid)
    except (TypeError, ValueError):
        return f"Узел {gid} не найден в выборке"

    rows = _df.loc[_df.gid == gid]
    if rows.empty:
        return f"Узел {gid} не найден в выборке"
    r = next(rows.itertuples())

    header = f"### {gid} — {RU.get(r.role, r.role)} ({r.rule}), приоритет {r.priority_score:.2f}"

    role_line = (f"**Роль:** {r.evidence}; role_score {r.role_score:.2f}; "
                 f"{'seed' if r.is_seed else 'не seed'}; колено {r.depth}; кластер {r.cluster_id}.")

    flow_line = (f"**Потоки:** получено {kzt(r.in_kzt)} от {r.in_deg} плательщиков ({r.in_tx} переводов), "
                 f"отдано {kzt(r.out_kzt)} → {r.out_deg} получателям ({r.out_tx})")
    if not pd.isna(r.pass_through):
        flow_line += f"; доля пропуска {pct(r.pass_through)}"
    if not pd.isna(r.fast_share):
        flow_line += f"; {pct(r.fast_share)} ушло за 2 дня"
    flow_line += f"; максимум плательщиков в один день: {r.max_payers_same_day}."

    seed_map = dict(zip(_df.gid, _df.is_seed))
    payers = _top_edges(gid, "in")
    receivers = _top_edges(gid, "out")
    pr_pct = _df.pagerank.rank(pct=True).loc[r.Index]
    btw_pct = _df.betweenness.rank(pct=True).loc[r.Index]
    links_line = (f"**Связи:** топ-плательщики: {_fmt_neighbors(payers, seed_map)}; "
                  f"топ-получатели: {_fmt_neighbors(receivers, seed_map)}; "
                  f"seed в 2 шагах: {r.seeds_2hop}; "
                  f"pagerank {pct(pr_pct)} перцентиль, betweenness {pct(btw_pct)} перцентиль.")

    notes = list(patterns.notes(r))
    if r.truncated:
        notes.append("обрыв выгрузки на 4-м колене — нужны исходящие (доп. выгрузка)")
    if r.is_seed:
        notes.append("seed: входящие занижены (выгружены только исходящие)")
    if not r.is_seed and not pd.isna(r.pass_through) and r.pass_through > 1.5:
        notes.append("отдаёт больше, чем получил — вероятны поступления извне выборки")
    if r.max_payers_same_day >= 3:
        notes.append(f"синхронные поступления: {r.max_payers_same_day} плательщиков в один день")
    if not notes:
        notes.append("выраженных дополнительных признаков нет")
    notes_block = "\n".join(f"- {n}" for n in notes)

    return "\n".join([header, "", role_line, flow_line, links_line, "",
                       "**На что обратить внимание:**", notes_block])


def write_cards(path, df, n=20):
    """Пишет карточки топ-n узлов по приоритету (priority_score desc, gid asc) в один markdown-файл."""
    top = df.sort_values(["priority_score", "gid"], ascending=[False, True]).head(n)
    header = ("# Карточки узлов — топ-20 по приоритету\n\n"
              "Это гипотезы для проверки, а не готовые выводы.\n")
    cards = "\n\n---\n\n".join(node_card(gid) for gid in top.gid)
    Path(path).write_text(header + "\n" + cards + "\n", encoding="utf-8")
