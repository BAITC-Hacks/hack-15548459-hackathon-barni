"""Агент: цикл «модель → инструменты → модель» со всеми слоями харнеса вокруг.

    agent = Agent(session_id="demo")
    answer = agent.run("Проанализируй файлы и сделай отчёт")
"""
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import dataclass, field

from . import config, monitor
from .context import compact, estimate_tokens
from .memory import SessionStore
from .prompts import build_system_prompt
from .router import ROUTER, LLMError
from .tools import REGISTRY, load_tools, run_tool


@dataclass
class Event:
    type: str   # run_start | thinking | tool_call | tool_result | final | error | run_end
    data: dict = field(default_factory=dict)


def print_event(ev):
    d = ev.data
    if ev.type == "thinking" and d.get("text", "").strip():
        print(f"\n💭 {d['text'].strip()}")
    elif ev.type == "tool_call":
        args = str(d["args"])
        print(f"\n🔧 {d['name']}({args[:200]}{'…' if len(args) > 200 else ''})")
    elif ev.type == "tool_result":
        preview = d["output"][:300].replace("\n", " ")
        print(f"   {'❌' if d['is_error'] else '✅'} {preview}{'…' if len(d['output']) > 300 else ''}")
    elif ev.type == "error":
        print(f"\n⚠️ {d['message']}")
    elif ev.type == "run_end":
        s = d["stats"]
        print(f"\n📊 {s['seconds']} с · вызовов модели: {s['llm_calls']} · инструментов: {s['tool_calls']} · "
              f"токенов: {s['tokens_in']}+{s['tokens_out']} · ${s['cost_usd']}")


def _truncate(text, limit):
    return text if len(text) <= limit else text[:limit] + f"\n…[обрезано, всего {len(text)} символов]"


class Agent:
    def __init__(self, session_id=None, role="smart", system_prompt=None, tools=None, exclude=None,
                 on_event=print_event, approve=None, persist=True, max_steps=None):
        """
        tools   — список имён инструментов (None = все); exclude — какие убрать.
        approve — функция(tool_name, args) -> bool для «опасных» инструментов при REQUIRE_APPROVAL=true.
        persist — сохранять историю сессии на диск.
        """
        load_tools()
        names = tools or list(REGISTRY)
        self.tools = [REGISTRY[n] for n in names if n in REGISTRY and n not in (exclude or [])]
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.role = role
        self.system_prompt = system_prompt or build_system_prompt()
        self.on_event = on_event or (lambda ev: None)
        self.approve = approve
        self.persist = persist
        self.max_steps = max_steps or config.MAX_STEPS
        state = SessionStore.load(self.session_id) if persist else {"messages": [], "summary": ""}
        self.messages, self.summary = state["messages"], state["summary"]
        self.last_stats = None

    # ── служебное ──────────────────────────────────────────────────────────────
    def _emit(self, type_, **data):
        ev = Event(type_, data)
        if type_ not in ("thinking",):
            monitor.trace(f"agent_{type_}", **{k: (str(v)[:2000] if k != "stats" else v) for k, v in data.items()})
        try:
            self.on_event(ev)
        except Exception as e:  # сломанный UI не должен ронять агента
            monitor.log.warning("on_event упал: %s", e)

    def _system(self):
        s = self.system_prompt
        if self.summary:
            s += f"\n\n## Краткое содержание более ранней части диалога\n{self.summary}"
        return s

    def _save(self):
        if self.persist:
            SessionStore.save(self.session_id, {"messages": self.messages, "summary": self.summary})

    def _call_tool(self, call):
        tool = REGISTRY.get(call.name)
        if tool and tool.dangerous and config.REQUIRE_APPROVAL:
            if not (self.approve and self.approve(call.name, call.args)):
                return "Пользователь не разрешил этот вызов. Предложи другой путь или спроси пользователя.", True
        try:
            monitor.record("tool_calls")
            return _truncate(run_tool(call.name, call.args) or "(пусто)", config.TOOL_OUTPUT_LIMIT), False
        except Exception as e:  # ошибку отдаём модели — пусть исправится
            monitor.record("errors")
            return f"Ошибка: {type(e).__name__}: {str(e)[:1500]}", True

    def _execute(self, calls):
        for c in calls:
            self._emit("tool_call", name=c.name, args=c.args)
        if config.PARALLEL_TOOLS and len(calls) > 1:
            with ThreadPoolExecutor(max_workers=min(8, len(calls))) as pool:
                futures = [pool.submit(copy_context().run, self._call_tool, c) for c in calls]
                results = [f.result() for f in futures]
        else:
            results = [self._call_tool(c) for c in calls]
        for c, (out, err) in zip(calls, results):
            self._emit("tool_result", name=c.name, output=out, is_error=err)
        return results

    # ── главный цикл ───────────────────────────────────────────────────────────
    def run(self, user_text):
        if len(user_text) > config.MAX_INPUT_CHARS:
            user_text = user_text[:config.MAX_INPUT_CHARS] + "\n…[сообщение обрезано]"

        parent = monitor.current_run.get()
        stats = parent or monitor.RunStats(session_id=self.session_id)
        token = None if parent else monitor.current_run.set(stats)
        if not parent:
            monitor.record("runs")
        self._emit("run_start", task=user_text)

        self.messages.append({"role": "user", "content": user_text})
        schemas = [t.openai_schema for t in self.tools]
        final = None
        try:
            for _ in range(self.max_steps):
                if stats.seconds > config.MAX_RUN_SECONDS:
                    final = f"Остановлено: превышен лимит времени {config.MAX_RUN_SECONDS} с."
                    break
                if stats.cost_usd > config.MAX_RUN_COST_USD:
                    final = f"Остановлено: превышен бюджет ${config.MAX_RUN_COST_USD} на задачу."
                    break

                system = self._system()
                self.messages, self.summary = compact(self.messages, self.summary,
                                                      estimate_tokens([{"content": system}]))
                result = ROUTER.chat(self.role, [{"role": "system", "content": self._system()}] + self.messages,
                                     tools=schemas or None)
                self.messages.append(result.message)

                if not result.tool_calls:
                    final = result.text
                    break

                self._emit("thinking", text=result.text)
                for call, (out, _err) in zip(result.tool_calls, self._execute(result.tool_calls)):
                    self.messages.append({"role": "tool", "tool_call_id": call.id, "content": out})
            else:
                final = f"Остановлено: достигнут лимит {self.max_steps} шагов."

            if final is not None and self.messages[-1].get("role") != "assistant":
                self.messages.append({"role": "assistant", "content": final})
        except LLMError as e:
            final = f"⚠️ Модели недоступны. {e}"
            self._emit("error", message=str(e))
        finally:
            self._save()
            self.last_stats = stats.to_dict()
            if token is not None:
                monitor.current_run.reset(token)
                self._emit("run_end", stats=self.last_stats)

        self._emit("final", text=final)
        return final

    def reset(self):
        self.messages, self.summary = [], ""
        self._save()

    def history(self):
        """Только реплики пользователя и финальные ответы — для UI."""
        return [{"role": m["role"], "content": m["content"]} for m in self.messages
                if m.get("role") in ("user", "assistant") and m.get("content") and not m.get("tool_calls")]
