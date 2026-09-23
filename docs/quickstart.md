# Быстрый запуск

Нужен Python 3.10 или новее. GPU не требуется. Все команды выполняйте из корня репозитория. `.env` для пайплайна и запуска интерфейсов не нужен: без API-ключа работает всё, кроме запросов AI-ассистента к модели.

## Установка и обработка данных

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-pipeline.txt
python run_pipeline.py
python tests/check_outputs.py
```

Вместо активации окружения можно вызывать интерпретатор явно:

```bash
.venv/bin/python -m pip install -r requirements-pipeline.txt
.venv/bin/python run_pipeline.py
.venv/bin/python tests/check_outputs.py
```

Пайплайн читает `data/` и сохраняет результаты в `outputs/`.

## Интерфейсы

Для AI-ассистента:

```bash
streamlit run ui/app.py
```

Для просмотра графа обработанных данных (сначала выполните пайплайн):

```bash
streamlit run ui/viewer.py
```

Чтобы задавать ассистенту вопросы модели, создайте локальный `.env` из примера и укажите свой ключ:

```bash
cp .env.example .env
```

Задайте `OPENAI_API_KEY` в `.env`. Не публикуйте и не коммитьте секретный ключ.

## Один запуск через скрипт

Если нужен полный цикл — установка зависимостей, обработка данных, проверка CSV и запуск AI-интерфейса — выполните:

```bash
./run.sh
```

Скрипт создаёт `.venv`, если окружения ещё нет. Для просмотра графа после него отдельно запустите `streamlit run ui/viewer.py`.
