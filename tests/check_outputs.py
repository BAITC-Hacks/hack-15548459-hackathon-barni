"""Mechanical checks for the CSV files submitted to the jury.

Run from any directory: python tests/check_outputs.py
"""

import csv
import math
import re
import sys
from pathlib import Path


OUTPUTS = Path(__file__).resolve().parents[1] / "outputs"
ROLES = {"coordinator", "consolidator", "distributor", "transit", "terminal", "peripheral"}
NODE_COLUMNS = {"gid", "role", "role_score", "cluster_id", "priority_score", "evidence"}
CLUSTER_COLUMNS = {"cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids", "hypothesis"}
INT64_MIN = -(1 << 63)
INT64_MAX = (1 << 63) - 1
DECIMAL_INTEGER = re.compile(r"[+-]?[0-9]+\Z")


def read_csv(name):
    path = OUTPUTS / name
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise ValueError("нет заголовка")
            return set(reader.fieldnames), list(reader), None
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        return set(), [], f"{name}: {exc}"


def first_bad(rows, predicate):
    for line, row in enumerate(rows, start=2):
        if not predicate(row):
            return line
    return None


def valid_score(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and 0 <= number <= 1


def valid_gid(value):
    if not isinstance(value, str) or not DECIMAL_INTEGER.fullmatch(value):
        return False
    number = int(value)
    return INT64_MIN <= number <= INT64_MAX


def check(condition, label, detail=""):
    print(f"{'✅' if condition else '❌'} {label}{': ' + detail if detail else ''}")
    return condition


def main():
    node_columns, nodes, node_error = read_csv("nodes_roles.csv")
    cluster_columns, clusters, cluster_error = read_csv("clusters.csv")
    top_columns, top, top_error = read_csv("top_nodes.csv")
    results = []

    for name, error in (("nodes_roles.csv", node_error),
                        ("clusters.csv", cluster_error),
                        ("top_nodes.csv", top_error)):
        results.append(check(error is None, f"чтение {name}", error or ""))

    results.append(check(node_error is None and len(nodes) == 2248,
                         "nodes_roles.csv: ровно 2248 строк", f"получено {len(nodes)}"))
    missing = sorted(NODE_COLUMNS - node_columns)
    results.append(check(node_error is None and not missing,
                         "nodes_roles.csv: обязательные колонки", f"нет {', '.join(missing)}" if missing else ""))
    line = first_bad(nodes, lambda row: all(row.get(col) is not None and row[col].strip()
                                                 for col in NODE_COLUMNS)) if not missing else 2
    results.append(check(node_error is None and not missing and line is None,
                         "nodes_roles.csv: обязательные поля заполнены",
                         f"строка {line}" if line else ""))

    line = first_bad(nodes, lambda row: row.get("role") in ROLES)
    results.append(check(node_error is None and line is None,
                         "роль входит в словарь", f"строка {line}" if line else ""))
    line = first_bad(nodes, lambda row: valid_score(row.get("role_score"))
                                           and valid_score(row.get("priority_score")))
    results.append(check(node_error is None and line is None,
                         "role_score и priority_score конечны и в диапазоне 0–1",
                         f"строка {line}" if line else ""))
    line = first_bad(nodes, lambda row: isinstance(row.get("evidence"), str)
                                           and bool(row["evidence"].strip())
                                           and len(row["evidence"]) <= 200
                                           and re.search(r"[0-9]", row["evidence"]) is not None)
    results.append(check(node_error is None and line is None,
                         "evidence: непустой, ≤200 символов, содержит цифры",
                         f"строка {line}" if line else ""))

    missing = sorted(CLUSTER_COLUMNS - cluster_columns)
    results.append(check(cluster_error is None and not missing,
                         "clusters.csv: обязательные колонки", f"нет {', '.join(missing)}" if missing else ""))
    cluster_ids = {row.get("cluster_id") for row in clusters if row.get("cluster_id")}
    line = first_bad(nodes, lambda row: bool(row.get("cluster_id"))
                                           and row["cluster_id"] in cluster_ids)
    results.append(check(node_error is None and cluster_error is None and line is None,
                         "каждый cluster_id узла есть в clusters.csv",
                         f"строка {line}" if line else ""))

    results.append(check(top_error is None and len(top) >= 20,
                         "top_nodes.csv: не менее 20 строк", f"получено {len(top)}"))
    top_score_column = "priority_score" in top_columns
    top_scores_ok = top_score_column and all(valid_score(row.get("priority_score")) for row in top)
    ordered = top_scores_ok and all(float(left["priority_score"]) >= float(right["priority_score"])
                                    for left, right in zip(top, top[1:]))
    results.append(check(top_error is None and ordered,
                         "top_nodes.csv: priority_score в 0–1, порядок по убыванию"))

    line = first_bad(nodes, lambda row: not (str(row.get("truncated", "")).strip().lower() == "true"
                                                 and row.get("role") == "terminal"))
    results.append(check(node_error is None and "truncated" in node_columns and line is None,
                         "truncated=True никогда не terminal", f"строка {line}" if line else ""))

    bad_gid = []
    for name, rows, columns in (("nodes_roles.csv", nodes, node_columns),
                                ("top_nodes.csv", top, top_columns)):
        if "gid" not in columns:
            bad_gid.append(f"{name}: нет gid")
        else:
            line = first_bad(rows, lambda row: valid_gid(row.get("gid")))
            if line is not None:
                bad_gid.append(f"{name}: строка {line}")
    if "top_gids" not in cluster_columns:
        bad_gid.append("clusters.csv: нет top_gids")
    else:
        line = first_bad(clusters, lambda row: all(valid_gid(gid.strip())
                                                  for gid in (row.get("top_gids") or "").split(";")))
        if line is not None:
            bad_gid.append(f"clusters.csv: строка {line}")
    results.append(check(not (node_error or cluster_error or top_error) and not bad_gid,
                         "gid: точная десятичная запись в диапазоне int64",
                         "; ".join(bad_gid[:3])))

    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
