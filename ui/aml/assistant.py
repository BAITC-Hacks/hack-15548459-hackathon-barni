"""AI-ассистент по графу: чат поверх harness.agent.Agent и инструментов графа."""
from __future__ import annotations

import os
import re
import uuid

import streamlit as st

GID_RE = re.compile(r"\b\d{18}\b")
MAX_GID_BUTTONS = 8
SAFETY_PREFIX = (
    "Отвечай только по данным инструментов графа. Каждый вывод называй гипотезой для проверки, "
    "указывай gid и никогда не утверждай виновность. Вопрос аналитика: "
)
NO_KEY_MESSAGE = (
    "AI-ассистент выключен: нет ключа API. Добавьте OPENAI_API_KEY (или NVIDIA_API_KEY) в файл "
    ".env и перезапустите приложение. Все остальные вкладки работают без ключа."
)


def _has_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("NVIDIA_API_KEY"))


def _example_questions(top) -> list[str]:
    top1 = str(top.iloc[0]["gid"]) if len(top) else "…"
    top3 = [str(g) for g in top["gid"].head(3)]
    if len(top3) == 3:
        q3 = f"Кому одновременно переводили узлы {top3[0]}, {top3[1]}, {top3[2]} из топ-3?"
    else:
        q3 = "Кому переводили узлы из топ-3?"
    return [
        "Кто главный консолидатор и почему?",
        f"Объясни роль узла {top1}",
        q3,
    ]


def _set_pending(question: str) -> None:
    st.session_state.ai_pending_question = question


def _reset_chat() -> None:
    agent = st.session_state.get("graph_agent")
    if agent is not None:
        try:
            agent.reset()
        except Exception:
            pass
    st.session_state.graph_chat = []
    st.session_state.ai_pending_question = None


def _render_steps(steps: list[dict]) -> None:
    n_calls = sum(1 for s in steps if s.get("type") == "tool_call")
    with st.expander(f"Шаги агента: вызвано инструментов — {n_calls}"):
        if not steps:
            st.caption("Инструменты не вызывались")
            return
        for step in steps:
            kind = step.get("type")
            if kind == "tool_call":
                args = ", ".join(f"{k}={v}" for k, v in (step.get("args") or {}).items())
                st.markdown(f"🔧 `{step.get('name', '?')}({args})`")
            elif kind == "tool_result":
                preview = str(step.get("output", ""))[:300]
                if step.get("is_error"):
                    st.markdown(f":red[❌ {preview}]")
                else:
                    st.code(preview, language=None)
            elif kind == "error":
                st.markdown(f":red[⚠️ {step.get('message', 'ошибка')}]")


def _gid_buttons(text: str, nodes, msg_idx: int, open_node) -> None:
    known = set(nodes["gid"])
    found, seen = [], set()
    for gid in GID_RE.findall(text):
        if gid in known and gid not in seen:
            seen.add(gid)
            found.append(gid)
        if len(found) >= MAX_GID_BUTTONS:
            break
    if not found:
        return
    cols = st.columns(min(4, len(found)))
    for i, gid in enumerate(found):
        cols[i % len(cols)].button(
            f"Открыть {gid}", key=f"ai_open_{msg_idx}_{gid}",
            on_click=open_node, args=(gid,), width="stretch",
        )


def render(nodes, top, open_node) -> None:
    """Вкладка «🤖 AI-ассистент». ``open_node(gid)`` переключает на вкладку «Сеть»."""
    st.subheader("AI-ассистент по графу")
    st.caption(
        "Задайте вопрос о сети. Ассистент отвечает только по данным инструментов графа и "
        "показывает, какие инструменты вызвал. Ответы — гипотезы для проверки."
    )

    has_key = _has_key()
    questions = _example_questions(top)
    cols = st.columns(3)
    for i, (col, question) in enumerate(zip(cols, questions)):
        col.button(
            question, key=f"ai_example_{i}", disabled=not has_key,
            on_click=_set_pending, args=(question,), width="stretch",
        )

    if not has_key:
        st.info(NO_KEY_MESSAGE)
        return

    from harness.agent import Agent

    if "graph_agent" not in st.session_state:
        st.session_state.graph_agent = Agent(session_id=uuid.uuid4().hex[:12], on_event=None)
        st.session_state.graph_chat = []
    if "ai_pending_question" not in st.session_state:
        st.session_state.ai_pending_question = None

    st.button("Очистить диалог", on_click=_reset_chat)

    for idx, message in enumerate(st.session_state.graph_chat):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant":
                _render_steps(message.get("steps") or [])
                _gid_buttons(message["content"], nodes, idx, open_node)

    typed = st.chat_input("Например: кто главный консолидатор?")
    question = typed or st.session_state.ai_pending_question

    if question:
        st.session_state.ai_pending_question = None
        st.session_state.graph_chat.append({"role": "user", "content": question})
        steps: list[dict] = []

        def on_event(event):
            if event.type in {"tool_call", "tool_result", "error"}:
                steps.append({"type": event.type, **event.data})

        agent = st.session_state.graph_agent
        agent.on_event = on_event
        try:
            with st.spinner("Ассистент анализирует граф…"):
                answer = agent.run(SAFETY_PREFIX + question)
        except Exception as exc:
            reason = f"{type(exc).__name__}: {str(exc)[:150]}"
            answer = f"Ассистент не ответил: {reason}. Попробуйте ещё раз или откройте узел через поиск."
        st.session_state.graph_chat.append({"role": "assistant", "content": answer, "steps": steps})
        st.rerun()
