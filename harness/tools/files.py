"""Файлы в рабочей папке (WORKSPACE). За её пределы агент выйти не может."""
from ..config import WORKSPACE
from ..textio import extract_text
from . import tool


def safe_path(path):
    p = (WORKSPACE / path).resolve()
    if p != WORKSPACE and WORKSPACE not in p.parents:
        raise ValueError("Путь должен быть внутри рабочей папки")
    return p


@tool
def list_files() -> list:
    """Список файлов в рабочей папке (данные кейса и файлы, созданные агентом). Вызывай первым, если задача про данные."""
    return [{"path": str(p.relative_to(WORKSPACE)), "size_kb": round(p.stat().st_size / 1024, 1)}
            for p in sorted(WORKSPACE.rglob("*")) if p.is_file() and not p.name.startswith(".")]


@tool
def read_file(path: str, offset: int = 0, limit: int = 15000) -> str:
    """Читает файл и возвращает текст. Понимает txt, md, csv, json, html, pdf, docx, xlsx.
    Для больших файлов читай частями через offset. Для поиска по многим документам лучше search_docs.

    Args:
        path: Путь относительно рабочей папки.
        offset: С какого символа начать.
        limit: Сколько символов вернуть.
    """
    text = extract_text(safe_path(path))
    part = text[offset:offset + limit]
    rest = len(text) - offset - len(part)
    return part + (f"\n…[ещё {rest} символов, продолжи с offset={offset + len(part)}]" if rest > 0 else "")


@tool(dangerous=True)
def write_file(path: str, content: str) -> str:
    """Создаёт или перезаписывает текстовый файл в рабочей папке (отчёт, письмо, JSON, CSV, HTML).

    Args:
        path: Путь относительно рабочей папки, например "output/report.md".
        content: Полное содержимое файла.
    """
    p = safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Сохранено: {p.relative_to(WORKSPACE)} ({len(content)} символов)"
