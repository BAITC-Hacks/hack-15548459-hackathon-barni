#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ ! -d .venv ]]; then
    python3 -m venv .venv
fi

.venv/bin/python -m pip install -r requirements-pipeline.txt -r requirements.txt
.venv/bin/python run_pipeline.py
.venv/bin/python tests/check_outputs.py
exec .venv/bin/streamlit run ui/app.py
