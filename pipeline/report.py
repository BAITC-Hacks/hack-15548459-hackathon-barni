"""Доп. анализ: устойчивость сети при изъятии топ-узлов + сводка ролей."""
import networkx as nx


def resilience(G, df, ns=(5, 10, 20)):
    base = max((len(c) for c in nx.weakly_connected_components(G)), default=0)
    order = df.sort_values(["priority_score", "gid"], ascending=[False, True]).gid.tolist()
    out = []
    for n in ns:
        H = G.copy()
        H.remove_nodes_from(order[:n])
        comps = list(nx.weakly_connected_components(H))
        largest = max((len(c) for c in comps), default=0)
        out.append({"removed_top": n, "largest_component": largest,
                    "largest_share_of_base": round(largest / base, 3), "components": len(comps)})
    return base, out


def write(path, G, df, clusters, base, res, seconds):
    rc = df.role.value_counts()
    lines = ["# Отчёт пайплайна", "", f"Время расчёта: {seconds:.1f} с", "",
             "## Роли", "", "| роль | узлов |", "|---|---|"]
    lines += [f"| {r} | {rc.get(r, 0)} |" for r in ["coordinator", "consolidator", "distributor", "transit", "terminal", "peripheral"]]
    lines += ["", "## Правила (сколько узлов сработало)", "", "| правило | узлов |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in df.rule.value_counts().sort_index().items()]
    lines += ["", f"## Кластеры: {len(clusters)} (с ≥2 seed: {(clusters.n_seed >= 2).sum()})", "",
              "## Устойчивость сети", "", f"Крупнейшая компонента до изъятия: {base} узлов", "",
              "| изъято топ-N | крупнейшая компонента | доля от исходной | компонент |", "|---|---|---|---|"]
    lines += [f"| {r['removed_top']} | {r['largest_component']} | {r['largest_share_of_base']} | {r['components']} |" for r in res]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
