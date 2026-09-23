"""Пути, загрузка датафреймов и отчёта пайплайна, форматирование чисел."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent

NODES_PATH = ROOT / "outputs" / "nodes_roles.csv"
TOP_PATH = ROOT / "outputs" / "top_nodes.csv"
CLUSTERS_PATH = ROOT / "outputs" / "clusters.csv"
EDGES_PATH = ROOT / "data" / "edges.parquet"
REPORT_PATH = ROOT / "outputs" / "report.md"


@st.cache_data(show_spinner="Загружаю граф…")
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    nodes = pd.read_csv(NODES_PATH, dtype={"gid": "string"})
    top = pd.read_csv(TOP_PATH, dtype={"gid": "string"})
    clusters = pd.read_csv(CLUSTERS_PATH)
    edges = pd.read_parquet(EDGES_PATH)
    edges["src"] = edges["src"].astype("string")
    edges["dst"] = edges["dst"].astype("string")
    nodes["gid"] = nodes["gid"].astype("string")
    return nodes, top, clusters, edges


def _empty_report() -> dict:
    return {"resilience": [], "base_component": None, "blind_spots_md": ""}


@st.cache_data(show_spinner=False)
def load_report() -> dict:
    """Читает outputs/report.md: устойчивость сети, размер базовой компоненты, белые пятна.

    Никогда не бросает исключение — при отсутствии файла или несовпадении формата
    возвращает пустые значения.
    """
    result = _empty_report()
    try:
        text = REPORT_PATH.read_text(encoding="utf-8")
    except OSError:
        return result

    try:
        base_match = re.search(r"Крупнейшая компонента до изъятия:\s*([\d\s]+)\s*узлов", text)
        if base_match:
            result["base_component"] = int(base_match.group(1).replace(" ", ""))
    except (ValueError, AttributeError):
        pass

    try:
        resilience_section = re.search(
            r"## Устойчивость сети(.*?)(?:\n## |\Z)", text, re.DOTALL
        )
        if resilience_section:
            rows = []
            for line in resilience_section.group(1).splitlines():
                line = line.strip()
                if not line.startswith("|") or "---" in line:
                    continue
                cells = [c.strip() for c in line.strip("|").split("|")]
                if len(cells) != 4 or not cells[0].isdigit():
                    continue
                rows.append({
                    "removed_top": int(cells[0]),
                    "largest_component": int(cells[1]),
                    "share": float(cells[2]),
                    "components": int(cells[3]),
                })
            result["resilience"] = rows
    except (ValueError, AttributeError):
        pass

    try:
        blind_match = re.search(
            r"(## Белые пятна и следующий запрос.*?)(?:\n## |\Z)", text, re.DOTALL
        )
        if blind_match:
            result["blind_spots_md"] = blind_match.group(1).strip()
    except AttributeError:
        pass

    return result


def money(value: object) -> str:
    try:
        amount = float(value)
        if abs(amount) >= 1_000_000:
            return f"{amount / 1_000_000:.1f}".replace(".", ",") + " млн ₸"
        if abs(amount) >= 1_000:
            return f"{amount / 1_000:.0f}".replace(".", ",") + " тыс ₸"
        return f"{amount:,.0f} ₸".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def bool_value(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def short_why(why: object, limit: int = 140) -> str:
    """Первая фраза/предложение из ``why`` (top_nodes.csv), обрезанная до ``limit`` символов."""
    text = str(why or "").strip()
    if not text:
        return "—"
    clause = re.split(r"[;.]", text, maxsplit=1)[0].strip()
    if len(clause) > limit:
        clause = clause[:limit].rstrip() + "…"
    return clause


def neighborhood(edges: pd.DataFrame, gid: str, depth: int) -> set[str]:
    chosen, frontier = {gid}, {gid}
    for _ in range(depth):
        mask = edges["src"].isin(frontier) | edges["dst"].isin(frontier)
        nxt = set(edges.loc[mask, "src"]) | set(edges.loc[mask, "dst"])
        frontier = nxt - chosen
        chosen |= nxt
    return chosen
