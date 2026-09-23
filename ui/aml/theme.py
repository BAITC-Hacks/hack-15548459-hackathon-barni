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
    "</style>"
)
