"""Демо-интерфейс для питча:  streamlit run ui/app.py
Показывает каждый шаг агента, модели, токены и стоимость — жюри видит, что агент реально работает."""
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from harness import config, monitor  # noqa: E402
from harness.agent import Agent  # noqa: E402
from harness.memory import MEMORY  # noqa: E402
from harness.rag import INDEX  # noqa: E402

# ── Поменяйте под кейс ──────────────────────────────────────────────────────────
TITLE = "🤖 AI Agent"
SUBTITLE = "Опишите задачу — агент сам спланирует шаги, найдёт данные и выдаст результат."
EXAMPLES = ["Что лежит в рабочей папке? Кратко опиши каждый файл.",
            "Найди в документах главное и сделай отчёт в report.md"]
# ────────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title=TITLE, page_icon="🤖", layout="wide")


def new_session():
    st.session_state.sid = uuid.uuid4().hex[:12]
    st.session_state.agent = Agent(session_id=st.session_state.sid, on_event=None)
    st.session_state.chat = []


if "agent" not in st.session_state:
    new_session()
agent: Agent = st.session_state.agent

with st.sidebar:
    st.subheader("Модели")
    for role, ref in config.ROLES.items():
        st.caption(f"**{role}** · `{ref}`")

    st.subheader("Документы")
    uploads = st.file_uploader("Загрузить в рабочую папку", accept_multiple_files=True)
    if uploads and st.button("📥 Сохранить и проиндексировать", use_container_width=True):
        for f in uploads:
            (config.WORKSPACE / f.name).write_bytes(f.getvalue())
        with st.spinner("Индексирую…"):
            try:
                st.success(INDEX.build())
            except Exception as e:
                st.error(f"Индексация не удалась: {e}")
    files = [p.name for p in config.WORKSPACE.rglob("*") if p.is_file() and not p.name.startswith(".")]
    st.caption(f"Файлов: {len(files)}")

    st.subheader("Статистика")
    if agent.last_stats:
        s = agent.last_stats
        c1, c2 = st.columns(2)
        c1.metric("Время", f"{s['seconds']} с")
        c2.metric("Стоимость", f"${s['cost_usd']}")
        c1.metric("Шаги модели", s["llm_calls"])
        c2.metric("Инструменты", s["tool_calls"])
        st.caption(f"Токены: {s['tokens_in']} → {s['tokens_out']}")
    t = monitor.totals()
    st.caption(f"Всего за сеанс сервера: {t['llm_calls']} вызовов · ${t['cost_usd']}")

    with st.expander(f"🧠 Долгосрочная память ({len(MEMORY.all())})"):
        for item in MEMORY.all()[-20:]:
            st.caption(f"• {item['text']}")
    with st.expander(f"🔧 Инструменты ({len(agent.tools)})"):
        for tl in agent.tools:
            st.caption(f"`{tl.name}`{' ⚠️' if tl.dangerous else ''}")

    if st.button("🔄 Новый диалог", use_container_width=True):
        new_session()
        st.rerun()

st.title(TITLE)
st.caption(SUBTITLE)


def render_step(step):
    kind = step["type"]
    if kind == "thinking" and step.get("text", "").strip():
        st.markdown(f"💭 {step['text']}")
    elif kind == "tool_call":
        st.markdown(f"🔧 **{step['name']}**")
        st.code(json.dumps(step["args"], ensure_ascii=False, indent=2)[:3000], language="json")
    elif kind == "tool_result":
        with st.expander(f"{'❌' if step['is_error'] else '✅'} результат {step['name']}"):
            st.text(step["output"][:4000])
    elif kind == "error":
        st.error(step["message"])


for msg in st.session_state.chat:
    with st.chat_message(msg["role"]):
        if msg.get("steps"):
            with st.expander(f"Шаги агента ({len(msg['steps'])})"):
                for s in msg["steps"]:
                    render_step(s)
        st.markdown(msg["content"])

prompt = st.chat_input("Задача для агента…")
if not st.session_state.chat:
    cols = st.columns(len(EXAMPLES))
    for col, ex in zip(cols, EXAMPLES):
        if col.button(ex, use_container_width=True):
            prompt = ex

if prompt:
    st.session_state.chat.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        steps = []
        status = st.status("Агент работает…", expanded=True)

        def on_event(ev):
            if ev.type in ("thinking", "tool_call", "tool_result", "error"):
                step = {"type": ev.type, **ev.data}
                steps.append(step)
                with status:
                    render_step(step)

        agent.on_event = on_event
        agent.approve = lambda name, args: True  # в демо разрешаем всё (включите REQUIRE_APPROVAL только для CLI)
        try:
            answer = agent.run(prompt)
            s = agent.last_stats
            status.update(label=f"Готово · {s['seconds']} с · шагов: {s['llm_calls']} · инструментов: {s['tool_calls']}",
                          state="complete", expanded=False)
        except Exception as e:
            answer = f"⚠️ {type(e).__name__}: {e}"
            status.update(label="Ошибка", state="error")
        st.markdown(answer)
    st.session_state.chat.append({"role": "assistant", "content": answer, "steps": steps})
    st.rerun()
