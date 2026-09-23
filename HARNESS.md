# 🧠 Hackathon Harness

Универсальный технический каркас для AI-агентов. **Без бизнес-логики и без решения ТЗ**: кейс, промпты
под задачу, специфичные инструменты и интерфейс решения пишутся на площадке.

Провайдеры: **OpenAI** и **NVIDIA** (build.nvidia.com), плюс любой OpenAI-совместимый эндпоинт.

## Что внутри (по схеме harness)

| Блок | Где | Что делает |
|---|---|---|
| **Управление контекстом** | `harness/context.py`, `harness/rag.py` | RAG по документам из `workspace/` (инкрементальный индекс); автосжатие длинной истории быстрой моделью |
| **Инструменты** | `harness/tools/` | Поиск в интернете, чтение страниц, HTTP к любым API, файлы (pdf/docx/xlsx/csv…), таблицы, **выполнение Python**, Telegram |
| **Память** | `harness/memory.py` | Краткосрочная: история сессий на диске. Долгосрочная: факты с поиском по смыслу (`remember`/`recall`) |
| **Распределение между моделями** | `harness/router.py`, `tools/agents.py` | Роли `smart`/`fast`/`embed`, автопереключение на запасную модель, под-агенты (`delegate`), `ask_model` |
| **Логика взаимодействия** | `harness/agent.py`, `harness/prompts.py` | Параллельные вызовы инструментов, лимиты (шаги/время/бюджет), подтверждение «опасных» действий, защита от инструкций внутри данных |
| **Мониторинг** | `harness/monitor.py` | Токены, стоимость, время, ошибки по каждой задаче; все события — в `.harness/traces/*.jsonl` |

Плюс: **Structured outputs** (`harness/structured.py`, Pydantic + автоповтор), **REST API** (FastAPI + стриминг),
**веб-демо** (Streamlit), **CLI**, **Docker**.

---

## 🚀 Установка (каждому)

```bash
git clone <репозиторий> && cd hackathon-harness
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # вписать OPENAI_API_KEY и NVIDIA_API_KEY

python tests/smoke_test.py           # офлайн-проверка всего харнеса → «ВСЁ РАБОТАЕТ»
# или всё сразу одной командой: bash scripts/setup.sh
python cli.py check                  # проверка НАСТОЯЩИХ ключей и моделей (+ умеют ли вызывать инструменты)
```

Если в `check` модель с ❌ — посмотреть, какие есть: `python cli.py models nvidia llama`, и поправить `.env`.

## ▶️ Запуск

```bash
streamlit run ui/app.py                       # демо для жюри → http://localhost:8501
uvicorn api.server:app --reload --port 8000   # API для своего фронта → http://localhost:8000/docs
python cli.py chat                            # агент в терминале
docker compose up --build                     # всё сразу в Docker
```

---

## 🏁 В день хакатона: что пишется на месте

1. **`case/case.md`** — описание кейса (попадает в системный промпт).
2. **Данные кейса** → в `workspace/`, затем `python cli.py index`.
3. **Инструменты под кейс** — новые файлы в `harness/tools/` (образец `_template.py`). Каждый — свой файл, поэтому конфликтов в git нет.
4. **Бизнес-логика** — внутри своих инструментов; для анализа используйте `extract()` из `harness/structured.py`.
5. **Интерфейс** — `TITLE`, `SUBTITLE`, `EXAMPLES` вверху `ui/app.py` (или свой фронт на API).

### Новый инструмент за 1 минуту
```python
# harness/tools/my_case.py
from . import tool
from ..structured import extract
from pydantic import BaseModel

class Risk(BaseModel):
    score: int
    reasons: list[str]

@tool
def assess_risk(text: str) -> dict:
    """Оценивает риск по описанию. Вызывай, когда нужно проверить заявку.

    Args:
        text: Полный текст заявки.
    """
    return extract(f"Оцени риск 0-10:\n{text}", Risk, role="fast").model_dump()
```
Главное — **docstring**: модель решает, когда вызвать инструмент, только по нему.

---

## ⚙️ Модели

В `.env` в формате `провайдер:модель`:
```
MODEL_SMART=openai:gpt-5-mini                    # главный агент
MODEL_SMART_FALLBACK=nvidia:meta/llama-3.3-70b-instruct
MODEL_FAST=nvidia:meta/llama-3.3-70b-instruct    # подзадачи, сжатие контекста
MODEL_EMBED=openai:text-embedding-3-small        # или nvidia:nvidia/nv-embedqa-e5-v5
```
Проверьте, что у выбранной модели NVIDIA есть tool calling (`cli.py check` это показывает).
Если сменили модель эмбеддингов — индекс пересоберётся сам.

---

## 🌿 Git: чтобы коммиты были у всех

Один раз (каждый): `git config --global user.email "почта_от_GitHub"` (иначе коммиты не засчитаются вам).

```bash
git checkout -b tool-search       # своя ветка
git add . && git commit -m "add search tool" && git push -u origin tool-search
# → Pull Request в main → Merge
git checkout main && git pull     # перед новой задачей
```
Коммит каждые 20–30 минут. `.env` не коммитится никогда.

**Разделение ролей:** ядро/интеграции · инструменты кейса (1–2 человека, каждый свои файлы) · UI + питч.

---

## 🩹 Если что-то не так

- **Агент зацикливается** → улучшить docstring инструментов и `case/case.md`, поднять `MAX_STEPS`.
- **Модель не вызывает инструменты** → другая модель (проверка: `cli.py check`).
- **Долго / дорого** → роль `fast` для подзадач, уменьшить `CONTEXT_MAX_TOKENS`, смотреть `python cli.py stats`.
- **Что делал агент?** → `.harness/traces/<дата>.jsonl` — каждый шаг, модель, токены, ошибки.
