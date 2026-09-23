"""Доп. анализ: устойчивость сети при изъятии топ-узлов + сводка ролей."""
import networkx as nx

from .config import THRESHOLDS as T
from .roles import kzt, pct


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


def blind_spots(G, df, clusters):
    """Белые пятна выгрузки: обрыв 4-го колена, seed без исходящих, кластеры с обрывами,
    конкретный список gid для следующей выгрузки."""
    lines = ["## Белые пятна и следующий запрос", ""]

    # 1. Обрыв 4-го колена
    trunc = df[df.truncated].sort_values("gid")
    n_trunc = len(trunc)
    in_kzt_trunc = trunc.in_kzt.sum()
    big = trunc[trunc.in_kzt >= T["terminal_min_in_kzt"]]
    total_in = df.in_kzt.sum()
    share = in_kzt_trunc / total_in if total_in else 0.0
    lines += ["### Обрыв 4-го колена («обрыв выгрузки»)", "",
              f"Узлов на обрыве выгрузки (4-е колено, исходящих нет) (`truncated`): {n_trunc}, на них "
              f"«застряло» {kzt(in_kzt_trunc)} входящих денег ({pct(share)} от всех входящих в графе). "
              f"Из них крупных (получили ≥{kzt(T['terminal_min_in_kzt'])}): {len(big)}, "
              f"сумма {kzt(big.in_kzt.sum())}.", ""]

    # 2. Seed без исходящих
    seed_noout = df[df.is_seed & (df.out_deg == 0)].sort_values("gid")
    no_tx = seed_noout[seed_noout.in_deg == 0]
    only_in = seed_noout[seed_noout.in_deg > 0]
    gids = seed_noout.gid.tolist()
    gid_str = (", ".join(map(str, gids[:15])) + f" и ещё {len(gids) - 15}") if len(gids) > 15 \
        else ", ".join(map(str, gids)) if gids else "—"
    lines += ["### Seed без исходящих переводов", "",
              f"Seed-клиентов без исходящих переводов ≥5 тыс ₸: {len(seed_noout)}. Из них совсем без "
              f"переводов внутри выборки: {len(no_tx)}; только с входящими (исходящие seed выгружались — "
              f"переводов ≥5 тыс ₸ у них действительно нет): {len(only_in)}.",
              f"gid: {gid_str}", ""]

    # 3. Кластеры с наибольшим числом обрывов
    base_cl = df.groupby("cluster_id").agg(n_nodes=("gid", "size"), n_seed=("is_seed", "sum"))
    tr_cl = trunc.groupby("cluster_id").agg(n_trunc=("gid", "size"), trunc_kzt=("in_kzt", "sum"))
    cl = base_cl.join(tr_cl, how="left").fillna(0)
    cl["n_trunc"] = cl.n_trunc.astype(int)
    cl["share"] = cl.n_trunc / cl.n_nodes
    top5 = cl.sort_values(["n_trunc", "cluster_id"], ascending=[False, True]).head(5).reset_index()
    lines += ["### Кластеры с наибольшим числом обрывов", "",
              "| cluster_id | узлов | на обрыве | доля | сумма на обрыве | n_seed |", "|---|---|---|---|---|---|"]
    lines += [f"| {int(r.cluster_id)} | {int(r.n_nodes)} | {int(r.n_trunc)} | {pct(r.share)} | "
              f"{kzt(r.trunc_kzt)} | {int(r.n_seed)} |" for r in top5.itertuples()]
    lines.append("")

    # 4. Следующий запрос данных
    top20 = trunc.sort_values(["in_kzt", "priority_score", "gid"], ascending=[False, False, True]).head(20)
    cover = top20.in_kzt.sum()
    cover_share = cover / in_kzt_trunc if in_kzt_trunc else 0.0
    lines += ["### Следующий запрос данных", "",
              f"Рекомендация: выгрузить исходящие переводы (5-е колено) за июль по gid ниже — это самые "
              f"крупные узлы на обрыве 4-го колена; отдельно выгрузить входящие переводы по seed-клиентам "
              f"(их поступления в текущей выборке не учтены). Топ-20 узлов на обрыве покрывают "
              f"{kzt(cover)} ({pct(cover_share)} от всех денег, застрявших на обрыве).", "",
              "| gid | получено | плательщиков | cluster_id | priority_score |", "|---|---|---|---|---|"]
    lines += [f"| {r.gid} | {kzt(r.in_kzt)} | {r.in_deg} | {int(r.cluster_id)} | {r.priority_score} |"
              for r in top20.itertuples()]
    lines += ["", "gid для выгрузки: " + ", ".join(str(g) for g in top20.gid.tolist())]
    return lines


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
    lines += ["", *blind_spots(G, df, clusters)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
