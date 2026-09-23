"""Мониторинг: токены, стоимость, время, ошибки. Каждое событие пишется в
.harness/traces/<дата>.jsonl — после демо можно показать жюри «что агент делал»."""
import json
import logging
import threading
import time
import uuid
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime

from . import config

logging.basicConfig(level=config.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("harness")

_lock = threading.Lock()


@dataclass
class RunStats:
    session_id: str = ""
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    started: float = field(default_factory=time.time)
    llm_calls: int = 0
    tool_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    errors: int = 0
    models: dict = field(default_factory=dict)

    @property
    def seconds(self):
        return round(time.time() - self.started, 2)

    def to_dict(self):
        d = asdict(self)
        d["seconds"] = self.seconds
        d["cost_usd"] = round(self.cost_usd, 5)
        return d


current_run: ContextVar[RunStats | None] = ContextVar("current_run", default=None)

TOTALS = {"runs": 0, "llm_calls": 0, "tool_calls": 0, "tokens_in": 0, "tokens_out": 0,
          "cost_usd": 0.0, "errors": 0}


def price(model, tokens_in, tokens_out):
    p_in, p_out = config.PRICES.get(model, (0.0, 0.0))
    return (tokens_in * p_in + tokens_out * p_out) / 1_000_000


def record_llm(model_ref, usage, latency):
    tin = getattr(usage, "prompt_tokens", 0) or 0 if usage else 0
    tout = getattr(usage, "completion_tokens", 0) or 0 if usage else 0
    cost = price(model_ref.split(":", 1)[-1], tin, tout)
    run = current_run.get()
    with _lock:
        TOTALS["llm_calls"] += 1
        TOTALS["tokens_in"] += tin
        TOTALS["tokens_out"] += tout
        TOTALS["cost_usd"] += cost
        if run:
            run.llm_calls += 1
            run.tokens_in += tin
            run.tokens_out += tout
            run.cost_usd += cost
            run.models[model_ref] = run.models.get(model_ref, 0) + 1
    trace("llm_call", model=model_ref, tokens_in=tin, tokens_out=tout,
          cost_usd=round(cost, 6), latency=round(latency, 2))
    return cost


def record(kind):
    """kind: 'tool_calls' | 'errors' | 'runs'"""
    run = current_run.get()
    with _lock:
        TOTALS[kind] += 1
        if run and hasattr(run, kind):
            setattr(run, kind, getattr(run, kind) + 1)


def trace(event, **data):
    run = current_run.get()
    line = {"ts": datetime.now().isoformat(timespec="seconds"), "event": event,
            "run_id": run.run_id if run else None,
            "session_id": run.session_id if run else None, **data}
    path = config.DATA_DIR / "traces" / f"{datetime.now():%Y-%m-%d}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock, open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")


def totals():
    with _lock:
        return {**TOTALS, "cost_usd": round(TOTALS["cost_usd"], 5)}
