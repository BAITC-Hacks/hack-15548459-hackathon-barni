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
    "</style>"
)
