"""REST API для любого фронтенда (React, мобильное приложение, Telegram-бот).

    uvicorn api.server:app --reload --port 8000      → документация: http://localhost:8000/docs
"""
import json
import queue
import threading

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from harness import config, monitor
from harness.agent import Agent
from harness.memory import MEMORY, SessionStore
from harness.providers import available_providers
from harness.rag import INDEX
from harness.tools import load_tools

app = FastAPI(title="Hackathon Agent API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_agents: dict[str, Agent] = {}
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def _get(session_id):
    with _guard:
        if session_id not in _agents:
            _agents[session_id] = Agent(session_id=session_id, on_event=None)
            _locks[session_id] = threading.Lock()
        return _agents[session_id], _locks[session_id]


class ChatIn(BaseModel):
    message: str
    session_id: str = "default"


def _event_dict(ev):
    return {"type": ev.type, **ev.data}


@app.get("/api/health")
def health():
    return {"status": "ok", "providers": available_providers(), "roles": config.ROLES,
            "tools": [t.name for t in load_tools()]}


@app.post("/api/chat")
def chat(body: ChatIn):
    """Выполнить задачу и вернуть ответ + все шаги агента + статистику."""
    agent, lock = _get(body.session_id)
    steps = []
    with lock:
        agent.on_event = lambda ev: steps.append(_event_dict(ev)) if ev.type in ("thinking", "tool_call", "tool_result", "error") else None
        answer = agent.run(body.message)
    return {"session_id": body.session_id, "answer": answer, "steps": steps, "stats": agent.last_stats}


@app.post("/api/chat/stream")
def chat_stream(body: ChatIn):
    """То же, но шаги приходят в реальном времени (Server-Sent Events)."""
    agent, lock = _get(body.session_id)
    q: queue.Queue = queue.Queue()

    def worker():
        with lock:
            agent.on_event = lambda ev: q.put(_event_dict(ev))
            try:
                agent.run(body.message)
            finally:
                q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def gen():
        while (item := q.get()) is not None:
            yield f"data: {json.dumps(item, ensure_ascii=False, default=str)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/sessions")
def sessions():
    return SessionStore.list()


@app.get("/api/sessions/{session_id}")
def session(session_id: str):
    agent, _ = _get(session_id)
    return {"session_id": session_id, "messages": agent.history(), "summary": agent.summary}


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    with _guard:
        _agents.pop(session_id, None)
    SessionStore.delete(session_id)
    return {"deleted": session_id}


@app.post("/api/upload")
def upload(files: list[UploadFile] = File(...), index: bool = True):
    saved = []
    for f in files:
        name = (f.filename or "file").replace("\\", "/").split("/")[-1]
        (config.WORKSPACE / name).write_bytes(f.file.read())
        saved.append(name)
    report = INDEX.build() if index else None
    return {"saved": saved, "index": report}


@app.get("/api/files")
def files():
    return [{"path": str(p.relative_to(config.WORKSPACE)), "size": p.stat().st_size}
            for p in sorted(config.WORKSPACE.rglob("*")) if p.is_file() and not p.name.startswith(".")]


@app.post("/api/index")
def reindex(force: bool = False):
    try:
        return {"report": INDEX.build(force=force)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/memory")
def memory():
    return MEMORY.all()


@app.get("/api/stats")
def stats():
    return monitor.totals()
