"""Все настройки — из .env (см. .env.example). В коде ничего менять не нужно."""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env(name, default=None):
    value = os.getenv(name)
    return default if value in (None, "") else value


def _int(name, default):
    return int(_env(name, default))


def _float(name, default):
    return float(_env(name, default))


def _bool(name, default):
    return str(_env(name, default)).lower() in ("1", "true", "yes", "on")


# ── Провайдеры (все OpenAI-совместимые) ─────────────────────────────────────────
PROVIDERS = {
    "openai": {"api_key": _env("OPENAI_API_KEY"), "base_url": _env("OPENAI_BASE_URL")},
    "nvidia": {"api_key": _env("NVIDIA_API_KEY"),
               "base_url": _env("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")},
}
if _env("CUSTOM_BASE_URL"):  # например, прокси организаторов
    PROVIDERS["custom"] = {"api_key": _env("CUSTOM_API_KEY", "none"), "base_url": _env("CUSTOM_BASE_URL")}

# ── Роли моделей (маршрутизация). Формат: "провайдер:модель" ───────────────────
ROLES = {
    "smart": _env("MODEL_SMART", "openai:gpt-5-mini"),                    # главный агент
    "fast": _env("MODEL_FAST", "nvidia:meta/llama-3.3-70b-instruct"),     # подзадачи, сжатие контекста
    "embed": _env("MODEL_EMBED", "openai:text-embedding-3-small"),        # RAG и память
}
FALLBACKS = {  # если основная модель упала — пробуем эту
    "smart": _env("MODEL_SMART_FALLBACK", "nvidia:meta/llama-3.3-70b-instruct"),
    "fast": _env("MODEL_FAST_FALLBACK", "openai:gpt-5-mini"),
}

# Цены USD за 1M токенов (вход, выход) — ПРОВЕРЬТЕ актуальные на сайте провайдера.
# Модели NVIDIA на build.nvidia.com бесплатные (по кредитам) → 0.
PRICES = {
    "gpt-5": (1.25, 10.0),
    "gpt-5-mini": (0.25, 2.0),
    "gpt-5-nano": (0.05, 0.4),
    "gpt-4.1-mini": (0.4, 1.6),
    "gpt-4o-mini": (0.15, 0.6),
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
}
PRICES.update({k: tuple(v) for k, v in json.loads(_env("PRICES_JSON", "{}")).items()})

# ── Надёжность ─────────────────────────────────────────────────────────────────
LLM_TIMEOUT = _float("LLM_TIMEOUT", 120)
LLM_RETRIES = _int("LLM_RETRIES", 3)          # повторы при 429/5xx/обрыве сети (с backoff)

# ── Лимиты агента ──────────────────────────────────────────────────────────────
MAX_STEPS = _int("MAX_STEPS", 20)
MAX_RUN_SECONDS = _int("MAX_RUN_SECONDS", 300)
MAX_RUN_COST_USD = _float("MAX_RUN_COST_USD", 1.0)
MAX_INPUT_CHARS = _int("MAX_INPUT_CHARS", 30000)
TOOL_OUTPUT_LIMIT = _int("TOOL_OUTPUT_LIMIT", 12000)
PARALLEL_TOOLS = _bool("PARALLEL_TOOLS", True)
REQUIRE_APPROVAL = _bool("REQUIRE_APPROVAL", False)   # спрашивать разрешение на «опасные» инструменты

# ── Контекст ───────────────────────────────────────────────────────────────────
CONTEXT_MAX_TOKENS = _int("CONTEXT_MAX_TOKENS", 60000)
KEEP_RECENT_MESSAGES = _int("KEEP_RECENT_MESSAGES", 12)

# ── Пути ───────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = Path(_env("WORKSPACE", ROOT / "workspace")).resolve()
DATA_DIR = Path(_env("DATA_DIR", ROOT / ".harness")).resolve()     # сессии, память, индекс, логи
CASE_FILE = Path(_env("CASE_FILE", ROOT / "case" / "case.md")).resolve()

TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _env("TELEGRAM_CHAT_ID")
LOG_LEVEL = _env("LOG_LEVEL", "INFO")

for _d in (WORKSPACE, DATA_DIR):
    _d.mkdir(parents=True, exist_ok=True)
