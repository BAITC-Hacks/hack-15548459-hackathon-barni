"""Паттерны: циклы, быстрые цепочки, дробление сумм, аномалии по объёму/связям."""
import numpy as np
import pandas as pd
import networkx as nx

from .config import THRESHOLDS as T


def _cycles(G, max_len):
    """Простые циклы длиной ≤ max_len. cycle_kzt узла — сумма минимальных сумм по его циклам
    (минимум = сколько денег реально может пройти полный круг)."""
    n_cycles, cycle_kzt = {}, {}
    for cyc in nx.simple_cycles(G, length_bound=max_len):
        k = len(cyc)
        if k < 2:  # перевод самому себе — не возвратный поток
            continue
        amt = min(G[cyc[i]][cyc[(i + 1) % k]]["sum_kzt"] for i in range(k))
        for g in cyc:
            n_cycles[g] = n_cycles.get(g, 0) + 1
            cycle_kzt[g] = cycle_kzt.get(g, 0.0) + amt
    return n_cycles, cycle_kzt


def _fast_chains(tx, days):
    """Для узла B: сколько разных маршрутов A→B→C уложились в `days` дней между переводами.
    fast_chain_repeats — из них те, что повторялись (≥2 разных дат t1)."""
    tin = tx.rename(columns={"src": "A", "dst": "B", "date": "t1"})[["A", "B", "t1"]]
    tout = tx.rename(columns={"src": "B", "dst": "C", "date": "t2"})[["B", "C", "t2"]]
    m = tin.merge(tout, on="B")
    m = m[(m.A != m.C) & (m.A != m.B) & (m.C != m.B)]
    dt_days = (m.t2 - m.t1).dt.days
    m = m[(dt_days >= 0) & (dt_days <= days)]

    routes = m.groupby(["B", "A", "C"])["t1"].nunique()  # число разных дат t1 на маршрут
    n_fast_chains = routes.groupby(level="B").size()
    fast_chain_repeats = routes[routes >= 2].groupby(level="B").size()
    return n_fast_chains, fast_chain_repeats


def _split(tx, min_tx, min_kzt, max_kzt):
    """Дробление: узел как отправитель — (получатель, день) с ≥min_tx переводами,
    из которых ≥2 попадают в диапазон [min_kzt, max_kzt]."""
    day = tx.date.dt.date
    grp = tx.groupby(["src", "dst", day])
    agg = grp.agg(n_tx=("sum_kzt", "size"),
                  n_in_range=("sum_kzt", lambda s: ((s >= min_kzt) & (s <= max_kzt)).sum())).reset_index()
    qual = agg[(agg.n_tx >= min_tx) & (agg.n_in_range >= 2)]
    split_days = qual.groupby("src").size()
    split_max_tx = qual.groupby("src")["n_tx"].max()
    return split_days, split_max_tx


def _zscore(values, group):
    """Z-score внутри группы; std=0 или размер группы <2 → 0 (а не NaN/inf)."""
    tmp = pd.DataFrame({"v": values, "g": group})
    mu = tmp.groupby("g")["v"].transform("mean")
    sd = tmp.groupby("g")["v"].transform("std")
    cnt = tmp.groupby("g")["v"].transform("size")
    z = (tmp.v - mu) / sd
    return z.where((sd > 0) & (cnt >= 2), 0.0).fillna(0.0)


def notes(r):
    """Короткие заметки на русском по сработавшим паттернам (только для сработавших),
    с конкретными цифрами. r — namedtuple из df.itertuples()."""
    from .roles import kzt  # lazy import: roles импортирует patterns, поэтому импорт здесь, а не на верху модуля

    out = []  # редкие и сильные признаки — первыми, чтобы влезли в evidence (≤200 символов)

    if getattr(r, "split_flag", False):
        out.append(f"дробление: {getattr(r, 'split_days', 0)} дн. по {getattr(r, 'split_max_tx', 0)}+ "
                   f"перевода одному получателю, {T['split_min_kzt'] / 1e3:g}–{T['split_max_kzt'] / 1e3:g} тыс ₸")

    anomaly_z = getattr(r, "anomaly_z", 0.0)
    if anomaly_z >= T["anomaly_z"]:
        out.append(f"аномалия: {getattr(r, 'anomaly_what', '')} z={anomaly_z:.1f} для колена {getattr(r, 'depth', '?')}")

    n_fast_chains = getattr(r, "n_fast_chains", 0)
    if n_fast_chains > 0:
        rep = getattr(r, "fast_chain_repeats", 0)
        out.append(f"быстрый проброс ≤{T['chain_days']} дн.: {n_fast_chains} маршр." + (f", {rep} повторных" if rep else ""))

    n_cycles = getattr(r, "n_cycles", 0)
    if n_cycles > 0:
        out.append(f"возвратные потоки: {n_cycles} цикл. ≤{T['cycle_max_len']} шагов, {kzt(getattr(r, 'cycle_kzt', 0.0))}")

    return out


def compute(G, df, tx):
    """Добавляет 5 колонок-признаков паттернов + вспомогательные (helper-колонки для evidence)."""
    df = df.copy()

    # 1. циклы
    n_cycles, cycle_kzt = _cycles(G, T["cycle_max_len"])
    df["n_cycles"] = df.gid.map(n_cycles).fillna(0).astype(int)
    df["cycle_kzt"] = df.gid.map(cycle_kzt).fillna(0.0).round(2)

    # 2. быстрые цепочки A→B→C
    n_fast_chains, fast_chain_repeats = _fast_chains(tx, T["chain_days"])
    df["n_fast_chains"] = df.gid.map(n_fast_chains).fillna(0).astype(int)
    df["fast_chain_repeats"] = df.gid.map(fast_chain_repeats).fillna(0).astype(int)

    # 3. дробление сумм
    split_days, split_max_tx = _split(tx, T["split_min_tx"], T["split_min_kzt"], T["split_max_kzt"])
    df["split_days"] = df.gid.map(split_days).fillna(0).astype(int)
    df["split_max_tx"] = df.gid.map(split_max_tx).fillna(0).astype(int)
    df["split_flag"] = df.split_days > 0

    # 4. аномалии по объёму/связям внутри своего колена (depth)
    z_flow = _zscore(np.log1p(df.flow_kzt), df.depth)
    z_deg = _zscore((df.in_deg + df.out_deg).astype(float), df.depth)
    anomaly_z = np.maximum(z_flow, z_deg)
    df["anomaly_z"] = anomaly_z.round(2)
    what = np.where(z_flow >= z_deg, "оборот", "связи")
    df["anomaly_what"] = np.where(df.anomaly_z < T["anomaly_z"], "", what)

    return df
