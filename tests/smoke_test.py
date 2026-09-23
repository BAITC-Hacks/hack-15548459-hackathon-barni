"""Полная проверка харнеса БЕЗ настоящих ключей: сеть подменяется фейковым OpenAI-совместимым сервером.
Запуск:  python tests/smoke_test.py      → в конце должно быть «ВСЁ РАБОТАЕТ»

Проверяет: цикл агента, параллельные инструменты, запасную модель (fallback), run_python, RAG,
долгосрочную память, под-агента, structured outputs, сжатие контекста, сохранение сессии, REST API."""
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ.update({
    "OPENAI_API_KEY": "test", "NVIDIA_API_KEY": "test", "LLM_RETRIES": "0",
    "MODEL_SMART": "openai:broken-model",                     # основная «падает» → должен сработать fallback
    "MODEL_SMART_FALLBACK": "nvidia:meta/llama-3.3-70b-instruct",
    "MODEL_FAST": "nvidia:meta/llama-3.3-70b-instruct",
    "MODEL_EMBED": "nvidia:nvidia/nv-embedqa-e5-v5",
    "WORKSPACE": str(tmp / "ws"), "DATA_DIR": str(tmp / "data"), "CASE_FILE": str(tmp / "none.md"),
    "LOG_LEVEL": "ERROR",
})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from harness import config, providers  # noqa: E402

calls = {"models": [], "embed_input_types": []}


def _tool_call(i, name, args):
    return {"id": f"call_{name}_{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}


def _reply(content=None, tool_calls=None):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {"id": "x", "object": "chat.completion", "created": 0, "model": "m",
            "choices": [{"index": 0, "message": msg, "finish_reason": "tool_calls" if tool_calls else "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}}


def _vec(text):
    v = [0.0] * 64
    for w in text.lower().split():
        v[int(hashlib.md5(w.strip(".,:!?").encode()).hexdigest(), 16) % 64] += 1.0
    return v


def handler(request: httpx.Request):
    body = json.loads(request.content)
    if request.url.path.endswith("/embeddings"):
        calls["embed_input_types"].append(body.get("input_type"))
        data = [{"object": "embedding", "index": i, "embedding": _vec(t)} for i, t in enumerate(body["input"])]
        return httpx.Response(200, json={"object": "list", "data": data, "model": body["model"],
                                         "usage": {"prompt_tokens": 5, "total_tokens": 5}})

    model = body["model"]
    calls["models"].append(model)
    if model == "broken-model":
        return httpx.Response(500, json={"error": {"message": "boom"}})

    msgs = body["messages"]
    system = msgs[0]["content"] if msgs[0]["role"] == "system" else ""
    if "Сожми историю" in system:
        return httpx.Response(200, json=_reply("- пользователь тестирует агента"))
    if "JSON-схеме" in system:
        if len(msgs) == 2:  # первый ответ специально кривой — проверяем повтор
            return httpx.Response(200, json=_reply("вот ответ: не json"))
        return httpx.Response(200, json=_reply('```json\n{"risk": 7, "reasons": ["дорого"]}\n```'))

    last_user = max(i for i, m in enumerate(msgs) if m["role"] == "user")
    task = msgs[last_user]["content"]
    step = sum(1 for m in msgs[last_user:] if m["role"] == "assistant" and m.get("tool_calls"))

    if task.startswith("ПОДЗАДАЧА"):
        return httpx.Response(200, json=_reply("итог подзадачи: 42"))
    if task == "главный тест":
        if step == 0:  # два инструмента сразу → параллельно
            return httpx.Response(200, json=_reply("План: создам файл и запомню факт", [
                _tool_call(0, "write_file", {"path": "sales.csv", "content": "city,amount\nАстана,100\nАлматы,250\nАстана,50\n"}),
                _tool_call(1, "remember", {"fact": "Пользователь любит отчёты в markdown"}),
            ]))
        if step == 1:
            return httpx.Response(200, json=_reply(None, [
                _tool_call(2, "run_python", {"code": "import pandas as pd\nprint(pd.read_csv('sales.csv').amount.sum())"}),
                _tool_call(3, "search_docs", {"query": "бюджет проекта"}),
                _tool_call(4, "recall", {"query": "отчёты markdown"}),
                _tool_call(5, "no_such_tool", {}),
            ]))
        if step == 2:
            return httpx.Response(200, json=_reply(None, [_tool_call(6, "delegate", {"task": "ПОДЗАДАЧА: посчитай"})]))
        return httpx.Response(200, json=_reply("Готово: сумма 400, бюджет 500 тысяч, подзадача 42."))
    return httpx.Response(200, json=_reply(f"ответ на: {task[:30]}"))


providers.set_http_client(httpx.Client(transport=httpx.MockTransport(handler)))
(config.WORKSPACE / "doc.txt").write_text("Бюджет проекта составляет 500 тысяч тенге.\nСрок — два месяца.", encoding="utf-8")

from harness.agent import Agent  # noqa: E402
from harness.structured import extract  # noqa: E402

events = []
agent = Agent(session_id="smoke", on_event=lambda ev: events.append(ev))
answer = agent.run("главный тест")

results = {e.data["name"]: e.data for e in events if e.type == "tool_result"}
check = lambda cond, msg: print(("✅ " if cond else "❌ ") + msg) or cond  # noqa: E731
ok = all([
    check(answer.startswith("Готово"), "цикл агента дошёл до ответа"),
    check("broken-model" in calls["models"] and "meta/llama-3.3-70b-instruct" in calls["models"], "fallback на запасную модель"),
    check("Сохранено" in results["write_file"]["output"], "write_file"),
    check(results["run_python"]["output"].strip() == "400", "run_python выполнил код"),
    check("500 тысяч" in results["search_docs"]["output"], "RAG нашёл документ"),
    check("markdown" in results["recall"]["output"], "долгосрочная память"),
    check(results["no_such_tool"]["is_error"], "ошибка инструмента не роняет агента"),
    check("42" in results["delegate"]["output"], "под-агент (delegate)"),
    check("query" in calls["embed_input_types"] and "passage" in calls["embed_input_types"], "эмбеддинги NVIDIA с input_type"),
    check(agent.last_stats["llm_calls"] >= 5 and agent.last_stats["tool_calls"] >= 7, f"мониторинг: {agent.last_stats['llm_calls']} вызовов модели, {agent.last_stats['tool_calls']} инструментов"),
])


class Verdict(BaseModel):
    risk: int
    reasons: list[str]


v = extract("оцени", Verdict)
ok &= check(v.risk == 7 and v.reasons == ["дорого"], "structured output (с повтором после кривого JSON)")

restored = Agent(session_id="smoke", on_event=None)
ok &= check(len(restored.messages) == len(agent.messages), "сессия сохранилась на диск")

config.CONTEXT_MAX_TOKENS, config.KEEP_RECENT_MESSAGES = 800, 2
for i in range(4):
    restored.run(f"сообщение номер {i} " + "текст " * 150)
ok &= check(bool(restored.summary) and len(restored.messages) < 12, "сжатие контекста")
config.CONTEXT_MAX_TOKENS = 60000

from fastapi.testclient import TestClient  # noqa: E402

from api.server import app  # noqa: E402

api = TestClient(app)
r = api.post("/api/chat", json={"message": "привет", "session_id": "api"}).json()
ok &= check(r["answer"].startswith("ответ на") and r["stats"]["llm_calls"] >= 1, "REST API /api/chat")
stream = api.post("/api/chat/stream", json={"message": "поток", "session_id": "api"}).text
ok &= check("[DONE]" in stream and '"final"' in stream, "REST API стриминг событий")
up = api.post("/api/upload", files=[("files", ("note.md", "Новая заметка про логистику".encode(), "text/markdown"))]).json()
ok &= check(up["saved"] == ["note.md"] and "фрагментов" in up["index"], "загрузка файлов + индексация")

traces = list((config.DATA_DIR / "traces").glob("*.jsonl"))
ok &= check(traces and "llm_call" in traces[0].read_text(encoding="utf-8"), "логи-трейсы пишутся")

print("\n✅ ВСЁ РАБОТАЕТ" if ok else "\n❌ ЕСТЬ ОШИБКИ")
sys.exit(0 if ok else 1)
