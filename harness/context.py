"""Управление контекстом: когда история не влезает в бюджет токенов,
(1) старые длинные ответы инструментов укорачиваются, (2) старая часть разговора
сжимается быстрой моделью в краткое содержание."""
import json

from . import config, monitor

SUMMARY_PROMPT = (
    "Сожми историю работы AI-агента в краткое содержание для него самого. Сохрани: цель пользователя, "
    "ключевые факты и цифры, найденные данные, созданные файлы, принятые решения и что осталось сделать. "
    "Пиши кратко, списком. Не выдумывай."
)


def estimate_tokens(messages):
    return sum(len(json.dumps(m, ensure_ascii=False, default=str)) for m in messages) // 3


def _shrink_old_tool_outputs(messages, keep_recent):
    cutoff = max(0, len(messages) - keep_recent)
    for m in messages[:cutoff]:
        if m.get("role") == "tool" and len(m.get("content") or "") > 600:
            m["content"] = m["content"][:500] + "\n…[старый вывод сокращён]"


def _transcript(messages):
    lines = []
    for m in messages:
        role = m.get("role")
        if role == "tool":
            lines.append(f"[результат инструмента] {(m.get('content') or '')[:800]}")
        elif m.get("tool_calls"):
            calls = ", ".join(f"{c['function']['name']}({c['function']['arguments'][:200]})"
                              for c in m["tool_calls"])
            lines.append(f"[агент вызвал] {calls}")
            if m.get("content"):
                lines.append(f"[агент] {m['content']}")
        else:
            lines.append(f"[{'пользователь' if role == 'user' else 'агент'}] {m.get('content') or ''}")
    return "\n".join(lines)


def compact(messages, summary, system_tokens=0):
    """Возвращает (messages, summary) так, чтобы всё влезло в CONTEXT_MAX_TOKENS."""
    budget = config.CONTEXT_MAX_TOKENS - system_tokens
    if estimate_tokens(messages) <= budget:
        return messages, summary

    _shrink_old_tool_outputs(messages, config.KEEP_RECENT_MESSAGES)
    if estimate_tokens(messages) <= budget:
        return messages, summary

    # режем только по границе сообщения пользователя, чтобы не разорвать пары tool_call/tool
    cut = None
    for i in range(len(messages) - config.KEEP_RECENT_MESSAGES, 0, -1):
        if messages[i].get("role") == "user":
            cut = i
            break
    if not cut:
        return messages, summary

    old, recent = messages[:cut], messages[cut:]
    from .router import ROUTER
    text = (f"Предыдущее краткое содержание:\n{summary}\n\n" if summary else "") + _transcript(old)
    try:
        new_summary = ROUTER.ask(text[:60000], role="fast", system=SUMMARY_PROMPT)
    except Exception as e:  # сжатие не должно ронять агента
        monitor.log.warning("Не удалось сжать контекст: %s", e)
        new_summary = (summary + "\n" if summary else "") + _transcript(old)[-3000:]
    monitor.trace("context_compacted", dropped_messages=len(old))
    return recent, new_summary
