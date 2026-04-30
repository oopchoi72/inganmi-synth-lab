#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
PYTHON_BIN="${PYTHON_BIN:-python3}"

load_env_defaults() {
  local env_file="$1"
  [[ -f "${env_file}" ]] || return 0
  while IFS='=' read -r key raw_value; do
    [[ -z "${key}" ]] && continue
    [[ "${key}" =~ ^[[:space:]]*# ]] && continue
    if [[ -z "${!key+x}" ]]; then
      export "${key}=${raw_value}"
    fi
  done < "${env_file}"
}

has_flag() {
  local flag="$1"
  shift
  for arg in "$@"; do
    if [[ "${arg}" == "${flag}" ]]; then
      return 0
    fi
  done
  return 1
}

load_env_defaults "${ENV_FILE}"

dry_run_state="${DRY_RUN:-false}"
force_fallback_state="${FORCE_FALLBACK:-false}"
if has_flag "--dry-run" "$@"; then
  dry_run_state="true"
fi
if has_flag "--force-fallback" "$@"; then
  force_fallback_state="true"
fi

echo "[inganmi-synth-lab] bootstrap runner (hybrid)"
echo "- provider: ${LLM_PROVIDER:-gemini}"
echo "- dry-run: ${dry_run_state}"
echo "- force-fallback: ${force_fallback_state}"

mkdir -p "${ROOT_DIR}/docs/experiments"

"${PYTHON_BIN}" "${ROOT_DIR}/src/poc/run_once.py" "$@"
