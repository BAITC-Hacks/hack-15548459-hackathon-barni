"""Все пороги ролей в одном месте. Меняются здесь — пересчитывается всё.
Подобраны по распределению данных (см. docs/roles.md, раздел «Почему такие пороги»)."""

THRESHOLDS = {
    # consolidator: собирает деньги от многих
    "consolidator_min_payers": 5,          # ≥5 разных плательщиков (топ-2% узлов по in_deg)
    "consolidator_min_payers_seed": 3,     # или ≥3 плательщика, из них ≥2 seed
    "consolidator_min_seed_payers": 2,

    # distributor: веерная рассылка
    "distributor_min_receivers": 10,       # ≥10 разных получателей (топ-3% по out_deg)
    "distributor_fanout_ratio": 2.0,       # получателей минимум вдвое больше, чем плательщиков

    # transit: пропускает дальше, не удерживая
    "transit_pass_min": 0.8,
    "transit_pass_max": 1.2,
    "transit_fast_days": 2,                # «быстрый» уход денег — в течение 2 дней после поступления
    "transit_fast_share": 0.7,             # ≥70% исходящих сумм ушли быстро
    "transit_pass_min_fast": 0.5,
    "transit_pass_max_fast": 1.5,

    # coordinator: узел-посредник между ветками сети
    # C1: сильный хаб — и собирает (≥5), и раздаёт (≥5), посредничество в топ-5%
    "coordinator_hub_min": 5,
    "coordinator_hub_btw_pct": 0.95,
    # C2: узел-мост — ≥3 входа и ≥3 выхода, посредничество в топ-2% и ≥2 seed в двух шагах выше
    "coordinator_min_in": 3,
    "coordinator_min_out": 3,
    "coordinator_betweenness_pct": 0.98,
    "coordinator_min_seeds_2hop": 2,

    # terminal: деньги пришли и остались (только там, где обход НЕ оборвался)
    "terminal_min_in_kzt": 166_000,        # ≈ 75-й перцентиль входящих сумм
    "terminal_min_payers": 2,

    # приоритет
    "role_weight": {"coordinator": 1.0, "consolidator": 0.9, "distributor": 0.8,
                    "transit": 0.6, "terminal": 0.5, "peripheral": 0.1},
    "priority_weights": {"role": 0.35, "flow": 0.20, "seeds": 0.20, "pagerank": 0.15, "betweenness": 0.10},

    "louvain_seed": 42,
    "top_n": 30,

    # паттерны (patterns.py)
    "cycle_max_len": 6,
    "chain_days": 2,
    "split_min_tx": 2,
    "split_min_kzt": 5000,
    "split_max_kzt": 10000,
    "anomaly_z": 3.0,
}

ROLES = ["consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral"]
