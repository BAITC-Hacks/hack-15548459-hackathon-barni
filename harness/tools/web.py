"""Интернет: поиск (без ключей), чтение страниц, запросы к любым API."""
import json
import re

import requests
from bs4 import BeautifulSoup

from . import tool

_UA = {"User-Agent": "Mozilla/5.0 (hackathon-harness)"}


@tool
def web_search(query: str, max_results: int = 5) -> list:
    """Поиск в интернете: заголовок, ссылка, фрагмент. Для свежих фактов и того, чего нет в данных.

    Args:
        query: Поисковый запрос (короткий, 2–6 слов).
        max_results: Сколько результатов.
    """
    from ddgs import DDGS
    return [{"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body")}
            for r in DDGS().text(query, max_results=max_results)]


@tool
def fetch_url(url: str) -> str:
    """Открывает веб-страницу и возвращает её текст. Используй после web_search.

    Args:
        url: Полный адрес (http/https).
    """
    resp = requests.get(url, headers=_UA, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "svg"]):
        tag.decompose()
    return re.sub(r"\n\s*\n+", "\n\n", soup.get_text("\n")).strip()


@tool(dangerous=True)
def http_request(url: str, method: str = "GET", body: str = "", headers: str = "") -> str:
    """HTTP-запрос к внешнему API (например, API из кейса). Возвращает статус и ответ.

    Args:
        url: Адрес эндпоинта.
        method: GET, POST, PUT, PATCH или DELETE.
        body: Тело запроса — JSON-строка (для POST/PUT/PATCH).
        headers: Доп. заголовки — JSON-строка, например {"Authorization": "Bearer ..."}.
    """
    h = {**_UA, **(json.loads(headers) if headers else {})}
    data = json.loads(body) if body else None
    resp = requests.request(method.upper(), url, json=data, headers=h, timeout=30)
    return f"HTTP {resp.status_code}\n{resp.text}"
