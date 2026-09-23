"""Роли по формальным правилам (порядок проверки = приоритет роли), role_score, приоритет и evidence."""
import numpy as np
import pandas as pd

from .config import THRESHOLDS as T


def kzt(x):
    x = float(x)
    if x >= 1e6:
        return f"{x / 1e6:.1f} млн ₸".replace(".", ",")
    if x >= 1e3:
        return f"{x / 1e3:.0f} тыс ₸"
    return f"{x:.0f} ₸"


def pct(x):
    return f"{x * 100:.0f}%"


def _clip(x):
    return float(min(1.0, max(0.0, x)))


def assign(df):
    """Возвращает df с колонками role, role_score, evidence, rule."""
    df = df.copy()
    btw_cut = df.betweenness.quantile(T["coordinator_betweenness_pct"])
    hub_cut = df.betweenness.quantile(T["coordinator_hub_btw_pct"])
    df["btw_pct"] = df.betweenness.rank(pct=True)
    roles, scores, evid, rules = [], [], [], []

    for r in df.itertuples():
        pt = r.pass_through
        fs = 0.0 if pd.isna(r.fast_share) else r.fast_share
        role = None

        # 1. coordinator — посредник между ветками: много входов и выходов + высокое посредничество или близость к seed
        hub = (r.in_deg >= T["coordinator_hub_min"] and r.out_deg >= T["coordinator_hub_min"]
               and r.betweenness >= hub_cut)
        bridge = (r.in_deg >= T["coordinator_min_in"] and r.out_deg >= T["coordinator_min_out"]
                  and r.betweenness >= btw_cut and r.seeds_2hop >= T["coordinator_min_seeds_2hop"])
        if not r.truncated and (hub or bridge):
            role, rule = "coordinator", "C1" if hub else "C2"
            score = 0.5 + 0.5 * np.mean([_clip(r.in_deg / 8), _clip(r.out_deg / 8), r.btw_pct])
            kind = "Хаб: собирает и раздаёт" if hub else "Мост между ветками"
            ev = (f"{kind}: {r.in_deg} плательщиков → {r.out_deg} получателей, через узел {kzt(r.out_kzt)}; "
                  f"{r.seeds_2hop} seed в 2 шагах выше; посредничество выше {pct(min(r.btw_pct, 0.99))} узлов")

        # 2. distributor — веер
        elif (r.out_deg >= T["distributor_min_receivers"]
              and r.out_deg >= T["distributor_fanout_ratio"] * max(r.in_deg, 1)):
            role, rule = "distributor", "D1"
            score = _clip(0.55 + r.out_deg / 120)
            ev = (f"Веерная рассылка: {kzt(r.out_kzt)} на {r.out_deg} получателей ({r.out_tx} переводов), "
                  f"плательщиков в выборке: {r.in_deg}" + ("; seed-клиент" if r.is_seed else ""))

        # 3. consolidator — сбор от многих
        elif (r.in_deg >= T["consolidator_min_payers"]
              or (r.in_deg >= T["consolidator_min_payers_seed"] and r.seed_payers >= T["consolidator_min_seed_payers"])):
            role, rule = "consolidator", "K1" if r.in_deg >= T["consolidator_min_payers"] else "K2"
            score = _clip(0.5 + r.in_deg / 20 + 0.1 * r.seed_payers)
            kept = "" if pd.isna(pt) else f", дальше ушло {pct(min(pt, 9.99))} полученного"
            ev = (f"Сбор средств: {kzt(r.in_kzt)} от {r.in_deg} плательщиков (из них seed: {r.seed_payers}){kept}"
                  + (f"; до {r.max_payers_same_day} плательщиков в один день" if r.max_payers_same_day >= 2 else ""))

        # 4. transit — пропускает дальше, не удерживая
        elif (not r.is_seed and r.in_deg > 0 and r.out_deg > 0 and not pd.isna(pt)
              and ((T["transit_pass_min"] <= pt <= T["transit_pass_max"])
                   or (fs >= T["transit_fast_share"] and T["transit_pass_min_fast"] <= pt <= T["transit_pass_max_fast"]))):
            role, rule = "transit", "T1" if T["transit_pass_min"] <= pt <= T["transit_pass_max"] else "T2"
            score = _clip(0.5 * (1 - min(abs(pt - 1) / 0.5, 1)) + 0.5 * fs)
            ev = (f"Транзит: получил {kzt(r.in_kzt)}, отдал {kzt(r.out_kzt)} ({pct(pt)}); "
                  f"{pct(fs)} суммы ушло в течение {T['transit_fast_days']} дн. после поступления")

        # 5. terminal — только там, где обход НЕ оборвался
        elif r.true_leaf and (r.in_kzt >= T["terminal_min_in_kzt"] or r.in_deg >= T["terminal_min_payers"]):
            role, rule = "terminal", "E1"
            score = _clip(0.5 + r.in_kzt / 2e6 + 0.05 * r.in_deg)
            ev = (f"Конечный получатель: {kzt(r.in_kzt)} от {r.in_deg} плательщиков, исходящих ≥5 тыс ₸ нет; "
                  f"колено {r.depth} — обход здесь не обрывался")

        # 6. peripheral — признаков роли нет (с объяснением почему)
        else:
            role = "peripheral"
            if r.truncated:
                rule, score = "P-trunc", 0.4
                ev = (f"Обрыв выгрузки на 4-м колене: получил {kzt(r.in_kzt)} от {r.in_deg}; исходящие не выгружены — "
                      f"роль «конечный» не присваиваем, нужна доп. выгрузка")
            elif r.in_deg == 0 and r.out_deg == 0:
                rule, score = "P-orphan", 0.9
                ev = "Seed-клиент без переводов ≥5 тыс ₸ внутри банка за июль"
            elif r.is_seed:
                rule, score = "P-seed", 0.6
                ev = f"Seed-клиент: отправил {kzt(r.out_kzt)} на {r.out_deg} получателей; признаков сбора или веера нет"
            elif r.true_leaf:
                rule, score = "P-leaf", 0.7
                ev = f"Разовое поступление: {kzt(r.in_kzt)} от {r.in_deg} плательщика, дальше не уходило; сумма мала"
            else:
                rule, score = "P-other", 0.5
                p = "н/д" if pd.isna(pt) else pct(min(pt, 99))
                ev = (f"Получил {kzt(r.in_kzt)}, отдал {kzt(r.out_kzt)} ({p}) — "
                      + ("отдаёт больше полученного: вероятны поступления извне выборки" if not pd.isna(pt) and pt > T["transit_pass_max_fast"]
                         else "удерживает часть средств, признаков роли недостаточно"))

        roles.append(role)
        scores.append(round(score, 3))
        evid.append(ev[:200])
        rules.append(rule)

    df["role"], df["role_score"], df["evidence"], df["rule"] = roles, scores, evid, rules
    return df


def priority(df):
    """Приоритет проверки 0–1: взвешенная сумма перцентилей + вес роли."""
    w = T["priority_weights"]
    comp = (
        w["role"] * df.role.map(T["role_weight"])
        + w["flow"] * df.flow_kzt.rank(pct=True)
        + w["seeds"] * df.seeds_2hop.rank(pct=True)
        + w["pagerank"] * df.pagerank.rank(pct=True)
        + w["betweenness"] * df.betweenness.rank(pct=True)
    )
    df = df.copy()
    df["priority_score"] = ((comp - comp.min()) / (comp.max() - comp.min())).round(4)
    return df


def why(r):
    extra = [f"оборот через узел {kzt(r.flow_kzt)}"]
    if r.seeds_2hop and "seed в 2 шагах" not in r.evidence:
        extra.append(f"{r.seeds_2hop} seed в 2 шагах выше")
    if r.fast_share == r.fast_share and r.fast_share >= 0.5 and "дн. после" not in r.evidence:
        extra.append(f"{pct(r.fast_share)} суммы уходит за 2 дня")
    return f"{r.evidence}. " + "; ".join(extra).capitalize()
