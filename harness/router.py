"""Распределение задач между моделями.

    ROUTER.chat("smart", messages, tools)   — главная модель (с запасной, если упала)
    ROUTER.chat("fast", messages)           — дешёвая/быстрая модель для подзадач
    ROUTER.chat("nvidia:some/model", ...)   — конкретная модель напрямую
    ROUTER.embed(["текст", ...])            — эмбеддинги для RAG и памяти
"""
import json
import time
from dataclasses import dataclass, field

import openai

from . import config, monitor
from .providers import ConfigError, client, parse_ref

log = monitor.log


class LLMError(RuntimeError):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict
    raw_args: str = ""


@dataclass
class ChatResult:
    text: str
    tool_calls: list = field(default_factory=list)
    message: dict = field(default_factory=dict)   # для истории (формат OpenAI)
    model: str = ""


def candidates(role):
    if ":" in role:
        return [role]
    if role not in config.ROLES:
        raise ConfigError(f"Неизвестная роль '{role}'. Есть: {', '.join(config.ROLES)}")
    refs = [config.ROLES[role], config.FALLBACKS.get(role)]
    return list(dict.fromkeys(r for r in refs if r))


def _parse_args(raw):
    try:
        args = json.loads(raw or "{}")
        return args if isinstance(args, dict) else {}
    except json.JSONDecodeError:
        return {"__invalid_json__": raw}


class Router:
    def chat(self, role, messages, tools=None, **kwargs):
        errors = []
        for ref in candidates(role):
            provider, model = parse_ref(ref)
            params = dict(model=model, messages=messages, **kwargs)
            if tools:
                params["tools"] = tools
            t0 = time.time()
            try:
                resp = client(provider).chat.completions.create(**params)
            except (openai.OpenAIError, ConfigError) as e:
                errors.append(f"{ref}: {type(e).__name__}: {str(e)[:300]}")
                log.warning("Модель %s не ответила: %s", ref, e)
                monitor.record("errors")
                monitor.trace("llm_error", model=ref, error=str(e)[:500])
                continue

            monitor.record_llm(ref, resp.usage, time.time() - t0)
            msg = resp.choices[0].message
            calls = [ToolCall(tc.id, tc.function.name, _parse_args(tc.function.arguments),
                              tc.function.arguments or "")
                     for tc in (msg.tool_calls or [])]
            history_msg = {"role": "assistant", "content": msg.content or None}
            if calls:
                history_msg["tool_calls"] = [
                    {"id": c.id, "type": "function",
                     "function": {"name": c.name, "arguments": c.raw_args or "{}"}}
                    for c in calls
                ]
            elif not msg.content:
                history_msg["content"] = ""
            return ChatResult(text=msg.content or "", tool_calls=calls, message=history_msg, model=ref)

        raise LLMError("Ни одна модель не ответила:\n" + "\n".join(errors))

    def ask(self, prompt, role="fast", system=None):
        messages = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": prompt}]
        return self.chat(role, messages).text

    def embed(self, texts, input_type="passage"):
        """input_type: 'passage' для документов, 'query' для поисковых запросов (нужно NVIDIA)."""
        provider, model = parse_ref(config.ROLES["embed"])
        extra = {"extra_body": {"input_type": input_type, "truncate": "END"}} if provider == "nvidia" else {}
        vectors = []
        for i in range(0, len(texts), 64):
            batch = [t[:8000] or " " for t in texts[i:i + 64]]
            t0 = time.time()
            resp = client(provider).embeddings.create(model=model, input=batch, **extra)
            monitor.record_llm(config.ROLES["embed"], resp.usage, time.time() - t0)
            vectors.extend(d.embedding for d in sorted(resp.data, key=lambda d: d.index))
        return vectors


ROUTER = Router()
