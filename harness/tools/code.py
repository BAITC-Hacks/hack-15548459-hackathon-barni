"""Выполнение Python — самый мощный инструмент: расчёты, анализ, графики, конвертация файлов."""
import os
import subprocess
import sys

from ..config import WORKSPACE
from . import tool


@tool(dangerous=True)
def run_python(code: str, timeout: int = 60) -> str:
    """Выполняет Python-код в рабочей папке и возвращает вывод print() и ошибки.
    Доступны pandas, numpy, matplotlib (графики сохраняй в файл через plt.savefig).
    Каждый вызов — новый процесс: переменные между вызовами не сохраняются, данные читай из файлов.

    Args:
        code: Полный Python-код. Результат выводи через print().
        timeout: Лимит времени в секундах (максимум 300).
    """
    env = {**os.environ, "MPLBACKEND": "Agg", "PYTHONIOENCODING": "utf-8"}
    try:
        r = subprocess.run([sys.executable, "-c", code], cwd=WORKSPACE, capture_output=True,
                           text=True, timeout=min(max(timeout, 1), 300), env=env)
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"Код выполнялся дольше {timeout} с и был остановлен")
    out = r.stdout.strip()
    if r.stderr.strip():
        out += ("\n" if out else "") + "[stderr]\n" + r.stderr.strip()[-4000:]
    if r.returncode != 0:
        out = f"[код завершился с ошибкой {r.returncode}]\n{out}"
    return out or "(вывода нет — используй print())"
