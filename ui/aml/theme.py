"""Цвета ролей, пояснения правил и тема интерфейса GraphAML."""
from __future__ import annotations

from html import escape

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
    """Нейтральный бейдж роли с цветным индикатором и доступным текстом."""
    color = ROLE_COLORS.get(role, ROLE_COLORS["peripheral"])
    label = escape(ROLE_LABELS.get(role, role))
    return (
        f"<span class='role-badge' style='--role-color:{color}'>"
        f"<span class='role-badge__dot' aria-hidden='true'></span>{label}</span>"
    )


def role_rgba(role: str, alpha: float = 0.55) -> str:
    """Цвет роли в rgba() для рёбер графа (полупрозрачный, чтобы читалось направление)."""
    hex_color = ROLE_COLORS.get(role, "#94a3b8").lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def role_chips_html(counts) -> str:
    """Пилюли ролей со счётчиками для легенды и карточки кластера."""
    get = counts.get if hasattr(counts, "get") else (lambda _role, _default=0: _default)
    return "".join(
        f"<span class='aml-chip'><span class='aml-dot' style='background:{color}'></span>"
        f"{ROLE_LABELS[role]} {int(get(role, 0) or 0)}</span>"
        for role, color in ROLE_COLORS.items()
    )


def legend_html(counts) -> str:
    """Легенда сети с количеством ролей и краткой подсказкой о кодировании графа."""
    notes = (
        "<span class='aml-chip-note'>◆ seed (белая рамка)</span>"
        "<span class='aml-chip-note'>→ направление денег, толщина = сумма, размер = приоритет</span>"
    )
    return f"<div class='aml-legend'>{role_chips_html(counts)}{notes}</div>"


GLOBAL_CSS = """
<style>
:root {
  color-scheme: dark;
  --aml-bg: #0b1018;
  --aml-surface: #111a26;
  --aml-surface-raised: #172231;
  --aml-border: #29384a;
  --aml-text: #e8eef6;
  --aml-muted: #b3c0ce;
  --aml-accent: #3e9ef7;
}
.stApp { background: var(--aml-bg); color: var(--aml-text); }
.block-container { max-width: 1500px; padding-top: 4.25rem !important; padding-bottom: 3rem; }
[data-testid="stSidebar"] { background: #0e1621; border-right: 1px solid var(--aml-border); }
[data-testid="stHeader"] { background: rgba(11, 16, 24, .92); }
h1, h2, h3, h4 { color: #f4f7fb; letter-spacing: -.02em; overflow: visible; }
h1 { line-height: 1.2 !important; padding-bottom: .08em; }
p, li, label, [data-testid="stCaptionContainer"] { color: var(--aml-muted); }
[data-testid="stMetric"] {
  background: var(--aml-surface); border: 1px solid var(--aml-border);
  border-radius: 12px; padding: 14px 16px;
}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {
  color: #b8c5d4; white-space: normal !important; overflow: visible !important;
  text-overflow: clip !important; font-size: .9rem !important; line-height: 1.35 !important;
}
[data-testid="stMetricValue"] {
  color: #f4f7fb; white-space: normal !important; overflow: visible !important;
  text-overflow: clip !important; font-size: 1.3rem !important; line-height: 1.3 !important;
  font-variant-numeric: tabular-nums;
}
[data-testid="stTabs"] [data-baseweb="tab-list"] { gap: 8px; border-bottom: 1px solid var(--aml-border); }
[data-testid="stTabs"] button[role="tab"] {
  min-height: 44px; color: #b8c5d4; border-radius: 8px 8px 0 0;
}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
  color: #f4f7fb; border-bottom: 2px solid var(--aml-accent);
}
[data-testid="stTabs"] button[role="tab"]:focus-visible,
button:focus-visible, input:focus-visible, textarea:focus-visible {
  outline: 2px solid #75bdff !important; outline-offset: 2px;
}
div[data-testid="stIFrame"], div[data-testid="stIFrame"] iframe {
  background: var(--aml-bg) !important; border: 1px solid var(--aml-border) !important;
  border-radius: 12px;
}
[data-testid="stDataFrame"] { border: 1px solid var(--aml-border); border-radius: 10px; }
[data-testid="stVerticalBlockBorderWrapper"] {
  border-color: var(--aml-border) !important; background: var(--aml-surface);
  border-radius: 12px;
}
div.stButton > button {
  min-height: 42px; border-radius: 8px; border: 1px solid #3a4a5f;
  background: #172231; color: #eef4fb; transition: background-color 120ms ease, border-color 120ms ease;
}
div.stButton > button:hover { border-color: #75bdff; background: #1c2b3d; color: #fff; }
div.stButton > button[kind="primary"] { background: #1d67a5; border-color: #378fda; color: #fff; }
[data-testid="stTextInput"] input, [data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stMultiSelect"] [data-baseweb="select"] > div {
  background-color: #121d2a; border-color: #34465a; color: #edf3fa;
}
[data-testid="stProgressBar"] > div > div { background: var(--aml-accent); }
.role-badge {
  display: inline-flex; align-items: center; gap: 7px; padding: 4px 10px;
  color: #edf3fa; background: #182332; border: 1px solid var(--role-color);
  border-radius: 999px; font-size: .82rem; line-height: 1.25; white-space: nowrap;
}
.role-badge__dot { width: 8px; height: 8px; border-radius: 50%; background: var(--role-color); flex: 0 0 auto; }
.feature-badges { display: flex; flex-wrap: wrap; gap: 6px; margin: 4px 0 8px; }
.feature-badges span { background: #243449; color: #e8eef6; border: 1px solid #3b5068; border-radius: 999px; padding: 3px 10px; font-size: .8rem; white-space: nowrap; }
.aml-legend { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 2px 0 10px; font-size: .82rem; color: #e2e8f0; }
.aml-chip { display: inline-flex; align-items: center; gap: 6px; background: #182332; border: 1px solid #34465a; border-radius: 999px; padding: 3px 10px; white-space: nowrap; }
.aml-dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; flex: none; }
.aml-chip-note { color: #b3c0ce; white-space: normal; }
.aml-flow { display: flex; flex-wrap: wrap; gap: 8px; align-items: stretch; margin: 6px 0 16px; }
.aml-flow-box { flex: 1 1 200px; min-width: 170px; background: #182332; color: #e2e8f0; border: 1px solid #34465a; border-radius: 10px; padding: 10px 14px; font-size: .82rem; line-height: 1.45; }
.aml-flow-box b { color: #f8fafc; }
.aml-flow-arrow { display: flex; align-items: center; justify-content: center; color: #b3c0ce; font-size: 1.3rem; font-weight: 700; flex: 0 0 auto; padding: 0 2px; }
.aml-roles-table { width: 100%; border-collapse: collapse; font-size: .82rem; color: #e2e8f0; background: #0f172a; border-radius: 8px; overflow: hidden; }
.aml-roles-table th, .aml-roles-table td { padding: 6px 10px; border-bottom: 1px solid #34465a; text-align: left; vertical-align: top; }
.aml-roles-table th { color: #b3c0ce; font-weight: 600; white-space: nowrap; }
.aml-mono { font-family: monospace; white-space: nowrap; }
@media (max-width: 720px) {
  .block-container { padding: 4.25rem 1rem 2rem !important; }
  [data-testid="stTabs"] [data-baseweb="tab-list"] { gap: 2px; overflow-x: auto; }
  [data-testid="stTabs"] button[role="tab"] { padding-inline: 10px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; transition-duration: .01ms !important; }
}
</style>
"""
