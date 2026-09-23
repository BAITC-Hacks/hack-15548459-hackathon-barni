"""Цвета ролей, русские подписи и общий CSS для интерфейса «Граф денег»."""
from __future__ import annotations

ROLE_LABELS = {
    "coordinator": "Координатор", "consolidator": "Консолидатор",
    "distributor": "Распределитель", "transit": "Транзитный",
    "terminal": "Конечный", "peripheral": "Периферийный",
}
ROLE_COLORS = {
    "coordinator": "#E5484D", "consolidator": "#8E4EC6",
    "distributor": "#F5A524", "transit": "#3E9EF7",
    "terminal": "#30A46C", "peripheral": "#6B7280",
}

RULE_TEXT = {
    "C1": "Хаб: получает деньги от 5+ разных людей и отправляет 5+ разным, через него проходят "
          "кратчайшие пути сети (топ-5% по посредничеству)",
    "C2": "Мост: 3+ входа и 3+ выхода, топ-2% по посредничеству, рядом (в 2 шагах выше) не меньше "
          "2 seed-клиентов",
    "D1": "Веер: отправляет деньги 10+ разным получателям, получателей минимум вдвое больше, чем "
          "плательщиков",
    "K1": "Сбор: получает деньги от 5+ разных плательщиков",
    "K2": "Сбор от seed: 3+ плательщика, из них 2+ — известные seed-клиенты",
    "T1": "Транзит: отдал дальше 80–120% полученного — деньги почти не задерживаются",
    "T2": "Быстрый транзит: отдал 50–150% полученного, и 70%+ суммы ушло в течение 2 дней после "
          "поступления",
    "E1": "Конечный получатель: исходящих переводов нет (узел на 1–3 колене, выгрузка тут не "
          "обрывалась), получил 166 тыс ₸+ или от 2+ плательщиков",
    "P-trunc": "Обрыв выгрузки: узел на 4-м колене, его исходящие не выгружались — куда ушли "
               "деньги, неизвестно",
    "P-leaf": "Разовое небольшое поступление, дальше деньги не ушли",
    "P-seed": "Seed-клиент без выраженного сбора или веера",
    "P-orphan": "Seed-клиент без переводов от 5 тыс ₸ внутри банка",
    "P-other": "Признаков роли недостаточно (удерживает часть средств или получает деньги извне "
               "выборки)",
}


def role_badge(role: str) -> str:
    """HTML-пилюля с цветом роли и русской подписью (для ``st.markdown(unsafe_allow_html=True)``)."""
    color = ROLE_COLORS.get(role, "#6B7280")
    label = ROLE_LABELS.get(role, role)
    return (
        f"<span style='background:{color};color:#ffffff;border-radius:999px;"
        f"padding:2px 10px;font-size:0.8rem;white-space:nowrap;'>{label}</span>"
    )


def role_rgba(role: str, alpha: float = 0.55) -> str:
    """Цвет роли в rgba() для рёбер графа (полупрозрачный, чтобы читалось направление)."""
    hex_color = ROLE_COLORS.get(role, "#94a3b8").lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def role_chips_html(counts) -> str:
    """Цветные пилюли ролей со счётчиком (без пояснений — для легенды и карточки кластера).

    ``counts`` — что-то со `.get(role, 0)` (обычно ``nodes["role"].value_counts()``).
    """
    get = counts.get if hasattr(counts, "get") else (lambda _role, _default=0: _default)
    return "".join(
        f"<span class='aml-chip'><span class='aml-dot' style='background:{color}'></span>"
        f"{ROLE_LABELS[role]} {int(get(role, 0) or 0)}</span>"
        for role, color in ROLE_COLORS.items()
    )


def legend_html(counts) -> str:
    """Легенда сети: цветные пилюли ролей со счётчиком по всей сети + пояснения формы/толщины."""
    notes = (
        "<span class='aml-chip-note'>◆ seed (белая рамка)</span>"
        "<span class='aml-chip-note'>→ направление денег, толщина = сумма, размер = приоритет</span>"
    )
    return f"<div class='aml-legend'>{role_chips_html(counts)}{notes}</div>"


GLOBAL_CSS = (
    "<style>"
    ".block-container{padding-top:2.5rem!important;}"
    "div[data-testid='stIFrame'],div[data-testid='stIFrame'] iframe{"
    "background:#0b1120!important;border:0!important;}"
    "div[data-testid='stMetricValue']{"
    "white-space:normal!important;overflow:visible!important;"
    "text-overflow:clip!important;font-size:1.3rem!important;line-height:1.3!important;}"
    "[data-testid='stMetricLabel'],[data-testid='stMetricLabel'] *{"
    "white-space:normal!important;overflow:visible!important;text-overflow:clip!important;}"
    ".feature-badges{display:flex;flex-wrap:wrap;gap:6px;margin:4px 0 8px;}"
    ".feature-badges span{background:#334155;color:#e2e8f0;border-radius:999px;"
    "padding:3px 10px;font-size:0.8rem;white-space:nowrap;cursor:default;}"
    ".aml-legend{display:flex;flex-wrap:wrap;gap:8px;align-items:center;"
    "margin:2px 0 10px;font-size:0.82rem;color:#e2e8f0;}"
    ".aml-chip{display:inline-flex;align-items:center;gap:6px;background:#1e293b;"
    "border-radius:999px;padding:3px 10px;white-space:nowrap;}"
    ".aml-dot{width:9px;height:9px;border-radius:50%;display:inline-block;flex:none;}"
    ".aml-chip-note{color:#94a3b8;white-space:nowrap;}"
    ".aml-flow{display:flex;flex-wrap:wrap;gap:8px;align-items:stretch;margin:6px 0 16px;}"
    ".aml-flow-box{flex:1 1 200px;min-width:170px;background:#1e293b;color:#e2e8f0;"
    "border-radius:10px;padding:10px 14px;font-size:0.82rem;line-height:1.4;}"
    ".aml-flow-box b{color:#f8fafc;}"
    ".aml-flow-arrow{display:flex;align-items:center;justify-content:center;"
    "color:#94a3b8;font-size:1.3rem;font-weight:700;flex:0 0 auto;padding:0 2px;}"
    ".aml-roles-table{width:100%;border-collapse:collapse;font-size:0.82rem;color:#e2e8f0;"
    "background:#0f172a;border-radius:8px;overflow:hidden;}"
    ".aml-roles-table th,.aml-roles-table td{padding:6px 10px;border-bottom:1px solid #334155;"
    "text-align:left;vertical-align:top;}"
    ".aml-roles-table th{color:#94a3b8;font-weight:600;white-space:nowrap;}"
    ".aml-mono{font-family:monospace;white-space:nowrap;}"
    "</style>"
)
