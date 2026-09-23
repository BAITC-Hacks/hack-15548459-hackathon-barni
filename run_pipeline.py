#!/usr/bin/env python3
"""Граф денег: одна команда от сырых .parquet до выгрузок.

    python run_pipeline.py                     # data/ → outputs/
    python run_pipeline.py --data путь --out путь
"""
import argparse
import sys
import time
from pathlib import Path

from pipeline import clusters, metrics, patterns, report, roles
from pipeline.config import THRESHOLDS as T

REQUIRED = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="outputs")
    a = ap.parse_args()
    t0 = time.time()
    data, out = Path(a.data), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    edges, nodes, tx = metrics.load(data)
    G, df = metrics.compute(edges, nodes, tx)
    df = patterns.compute(G, df, tx)
    df = df.round({"pagerank": 10, "betweenness": 10, "pass_through": 6, "fast_share": 6})
    df = roles.assign(df)
    df = roles.priority(df)
    cmap = clusters.build(G)
    df["cluster_id"] = df.gid.map(cmap).astype(int)

    # 1. nodes_roles.csv — обязательные колонки + метрики для объяснения
    extra = ["rule", "depth", "is_seed", "in_deg", "out_deg", "in_kzt", "out_kzt", "in_tx", "out_tx",
             "pass_through", "fast_share", "seed_payers", "seeds_2hop", "pagerank", "betweenness",
             "max_payers_same_day", "truncated",
             "n_cycles", "cycle_kzt", "n_fast_chains", "split_flag", "anomaly_z"]
    df.sort_values("gid")[REQUIRED + extra].to_csv(out / "nodes_roles.csv", index=False)

    # 2. clusters.csv
    cl = clusters.table(G, df)
    cl.to_csv(out / "clusters.csv", index=False)

    # 3. top_nodes.csv
    top = df.sort_values(["priority_score", "gid"], ascending=[False, True]).head(T["top_n"]).copy()
    top.insert(0, "rank", range(1, len(top) + 1))
    top["why"] = [roles.why(r) for r in top.itertuples()]
    top[["rank", "gid", "role", "priority_score", "why", "cluster_id"]].to_csv(out / "top_nodes.csv", index=False)

    df.to_parquet(out / "metrics.parquet", index=False)  # для интерфейса и ассистента

    base, res = report.resilience(G, df)
    sec = time.time() - t0
    report.write(out / "report.md", G, df, cl, base, res, sec)

    # самопроверка схемы
    nr = df[REQUIRED]
    assert len(nr) == len(nodes) == 2248, f"строк {len(nr)}"
    assert nr.notna().all().all() and (nr.evidence.str.len() > 0).all()
    assert len(top) >= 20
    print(f"✅ Готово за {sec:.1f} с → {out}/")
    print(df.role.value_counts().to_string())
    print(f"кластеров: {len(cl)}, топ: {len(top)}")


if __name__ == "__main__":
    sys.exit(main())
