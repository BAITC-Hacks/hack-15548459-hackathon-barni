"""Клиенты провайдеров. OpenAI и NVIDIA (build.nvidia.com) говорят на одном API,
поэтому достаточно одного SDK с разными base_url."""
import openai

from . import config

_clients = {}
_http_client = None  # для тестов: подменяем сеть


class ConfigError(RuntimeError):
    pass


def set_http_client(http_client):
    global _http_client
    _http_client = http_client
    _clients.clear()


def parse_ref(ref):
    """'nvidia:meta/llama-3.3-70b-instruct' -> ('nvidia', 'meta/llama-3.3-70b-instruct')"""
    if ":" not in ref:
        raise ConfigError(f"Модель '{ref}' должна быть в формате провайдер:модель")
    provider, model = ref.split(":", 1)
    return provider.strip(), model.strip()


def client(provider):
    if provider not in _clients:
        cfg = config.PROVIDERS.get(provider)
        if cfg is None:
            raise ConfigError(f"Неизвестный провайдер '{provider}'. Есть: {', '.join(config.PROVIDERS)}")
        if not cfg.get("api_key"):
            raise ConfigError(f"Нет API-ключа для '{provider}' — заполните .env")
        kwargs = dict(api_key=cfg["api_key"], base_url=cfg.get("base_url"),
                      timeout=config.LLM_TIMEOUT, max_retries=config.LLM_RETRIES)
        if _http_client is not None:
            kwargs["http_client"] = _http_client
        _clients[provider] = openai.OpenAI(**kwargs)
    return _clients[provider]


def available_providers():
    return [name for name, cfg in config.PROVIDERS.items() if cfg.get("api_key")]
