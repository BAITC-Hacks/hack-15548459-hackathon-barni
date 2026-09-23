#!/usr/bin/env bash

# Run this from any directory. Every check runs against a fresh clone of origin/main.
set -u
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -n "${FINAL_CHECK_REMOTE:-}" ]]; then
  REMOTE_URL="$FINAL_CHECK_REMOTE"
else
  REMOTE_URL="$(git -C "$SCRIPT_DIR/.." remote get-url origin 2>/dev/null || true)"
fi
TMP_ROOT="${TMPDIR:-/tmp}"
WORK_DIR=""
declare -a STEP_NAMES=("Clone origin/main" "Create virtualenv" "Install pipeline requirements" "Run pipeline (<300s)" "Check generated outputs" "Pipeline tests" "UI smoke test" "No .env files" "No tracked secret-like keys")
declare -a STEP_RESULTS=("PENDING" "PENDING" "PENDING" "PENDING" "PENDING" "PENDING" "PENDING" "PENDING" "PENDING")

record() {
  STEP_RESULTS[$1]="$2"
}

summary() {
  local i result overall=0
  printf '\nFinal pre-submission check\n'
  printf '+------------------------------------+------------+\n'
  printf '| %-34s | %-10s |\n' "Step" "Result"
  printf '+------------------------------------+------------+\n'
  for i in "${!STEP_NAMES[@]}"; do
    result="${STEP_RESULTS[$i]}"
    if [[ "$result" == "PENDING" ]]; then
      result="❌ NOT RUN"
      overall=1
    elif [[ "$result" == ❌* ]]; then
      overall=1
    fi
    printf '| %-34s | %-10s |\n' "${STEP_NAMES[$i]}" "$result"
  done
  printf '+------------------------------------+------------+\n'
  FINAL_STATUS="$overall"
}

cleanup() {
  local exit_status=$?
  trap - EXIT
  if [[ -n "$WORK_DIR" && -d "$WORK_DIR" ]]; then
    if rm -rf "$WORK_DIR"; then
      WORK_DIR=""
    else
      printf 'Could not remove temporary directory: %s\n' "$WORK_DIR" >&2
      exit_status=1
    fi
  fi
  summary
  if [[ "${FINAL_STATUS:-1}" -ne 0 ]]; then
    exit_status=1
  fi
  exit "$exit_status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if ! WORK_DIR="$(mktemp -d "${TMP_ROOT%/}/final-check.XXXXXX")"; then
  printf 'Could not create temporary directory.\n' >&2
  exit 1
fi

if [[ -z "$REMOTE_URL" ]]; then
  printf 'Could not read the repository origin URL. Set FINAL_CHECK_REMOTE to override it.\n' >&2
  record 0 "❌"
  for idx in 1 2 3 4 5 6 7 8; do record "$idx" "❌ SKIPPED"; done
  exit 1
fi

REPO_DIR="$WORK_DIR/repo"
if git clone --quiet --branch main --single-branch "$REMOTE_URL" "$REPO_DIR"; then
  record 0 "✅"
else
  record 0 "❌"
  printf 'Clone failed for origin main; remaining checks require the clone.\n' >&2
  for idx in 1 2 3 4 5 6 7 8; do record "$idx" "❌ SKIPPED"; done
  exit 1
fi

if (cd "$REPO_DIR" && python3 -m venv .venv); then
  record 1 "✅"
else
  record 1 "❌"
fi

VENV_PYTHON="$REPO_DIR/.venv/bin/python"
if [[ "${STEP_RESULTS[1]}" == "✅" ]] && (cd "$REPO_DIR" && .venv/bin/python -m pip install -r requirements-pipeline.txt); then
  record 2 "✅"
else
  record 2 "❌"
fi

if [[ "${STEP_RESULTS[2]}" == "✅" ]]; then
  if (cd "$REPO_DIR" && "$VENV_PYTHON" -c 'import subprocess,sys,time
started = time.monotonic()
try:
    result = subprocess.run(sys.argv[1:], timeout=300)
except subprocess.TimeoutExpired:
    print("Pipeline exceeded 300 seconds.", file=sys.stderr)
    sys.exit(124)
duration = time.monotonic() - started
print("Pipeline completed in %.3f seconds." % duration)
sys.exit(result.returncode if duration < 300 else 124)' "$VENV_PYTHON" run_pipeline.py); then
    record 3 "✅"
  else
    record 3 "❌"
  fi
else
  record 3 "❌ SKIPPED"
fi

if [[ "${STEP_RESULTS[3]}" == ✅* ]]; then
  if (cd "$REPO_DIR" && "$VENV_PYTHON" tests/check_outputs.py); then record 4 "✅"; else record 4 "❌"; fi
else
  record 4 "❌ SKIPPED"
fi

if [[ "${STEP_RESULTS[2]}" == "✅" ]]; then
  if (cd "$REPO_DIR" && "$VENV_PYTHON" tests/test_pipeline.py); then record 5 "✅"; else record 5 "❌"; fi
  if (cd "$REPO_DIR" && "$VENV_PYTHON" tests/test_ui_smoke.py); then record 6 "✅"; else record 6 "❌"; fi
else
  record 5 "❌ SKIPPED"
  record 6 "❌ SKIPPED"
fi

env_file="$(find "$REPO_DIR" -type d \( -name .git -o -name .venv \) -prune -o -type f -name .env -print -quit)"
if [[ -z "$env_file" ]]; then record 7 "✅"; else record 7 "❌"; fi

# Split the marker so this checker does not match its own source in a repository scan.
key_marker='s''k-'
if (cd "$REPO_DIR" && git grep -I -F -q "$key_marker" HEAD -- >/dev/null 2>&1); then
  record 8 "❌"
else
  grep_status=$?
  if [[ "$grep_status" -eq 1 ]]; then record 8 "✅"; else record 8 "❌"; fi
fi

exit 0
