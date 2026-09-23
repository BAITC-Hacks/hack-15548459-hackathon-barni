#!/bin/bash
# Установка проекта на Mac/Linux:  bash scripts/setup.sh
set -e
cd "$(dirname "$0")/.."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
[ -f .env ] || { cp .env.example .env; echo "Создан .env — впишите туда свои ключи"; }
python tests/smoke_test.py
echo ""
echo "Готово. Дальше: впишите ключи в .env и запустите:"
echo "  source .venv/bin/activate && python cli.py check"
