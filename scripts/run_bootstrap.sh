#!/usr/bin/env bash
# Bash 인터프리터를 env로 찾아 실행한다. (환경마다 bash 경로가 달라도 동작)
set -euo pipefail
# -e: 명령 실패 시 즉시 종료
# -u: 정의되지 않은 변수 사용 시 오류
# -o pipefail: 파이프라인 중간 단계 실패도 전체 실패로 처리

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# 현재 스크립트 파일 위치를 기준으로 프로젝트 루트 절대경로를 계산한다.
ENV_FILE="${ROOT_DIR}/.env"
# 루트의 .env 파일 경로를 변수로 보관한다.
PYTHON_BIN="${PYTHON_BIN:-python3}"
# PYTHON_BIN이 이미 지정되어 있으면 그 값을 쓰고, 없으면 python3를 기본값으로 사용한다.

load_env_defaults() {
  # .env 파일의 값을 "기본값"으로만 로드하는 함수.
  # 이미 셸에 설정된 환경변수는 덮어쓰지 않는다.
  local env_file="$1"
  # 첫 번째 인자를 로컬 변수로 받는다. (함수 밖 변수 오염 방지)
  [[ -f "${env_file}" ]] || return 0
  # 파일이 없으면 조용히 성공 반환(0)하고 종료한다.
  while IFS='=' read -r key raw_value; do
    # key=value 형태를 '=' 기준으로 분리해 한 줄씩 읽는다.
    # IFS='=': 구분자를 '='로 지정, -r: 백슬래시 이스케이프 해석 방지
    [[ -z "${key}" ]] && continue
    # key가 비어 있으면(빈 줄 등) 건너뛴다.
    [[ "${key}" =~ ^[[:space:]]*# ]] && continue
    # 공백 뒤 #으로 시작하는 주석 라인은 건너뛴다.
    if [[ -z "${!key+x}" ]]; then
      # 같은 이름의 환경변수가 아직 정의되지 않았을 때만 .env 값을 적용한다.
      export "${key}=${raw_value}"
      # key=value를 현재 셸 환경에 export한다.
    fi
  done < "${env_file}"
  # while 입력 소스로 env_file을 리다이렉트한다.
}

has_flag() {
  # 전달된 인자 목록($@) 안에 특정 플래그가 있는지 검사하는 함수.
  local flag="$1"
  # 검사 대상 플래그(예: --dry-run)
  shift
  # 첫 번째 인자를 제거해, 나머지 인자들만 순회 대상으로 만든다.
  for arg in "$@"; do
    # 남은 모든 인자를 순회한다.
    if [[ "${arg}" == "${flag}" ]]; then
      # 현재 인자가 찾는 플래그와 일치하면
      return 0
      # true(성공) 반환
    fi
  done
  return 1
  # 끝까지 못 찾으면 false(실패) 반환
}

load_env_defaults "${ENV_FILE}"
# .env 기본값 로드를 먼저 수행한다.

dry_run_state="${DRY_RUN:-false}"
# 환경변수 DRY_RUN 상태를 출력용 변수로 준비한다. (없으면 false)
force_fallback_state="${FORCE_FALLBACK:-false}"
# 환경변수 FORCE_FALLBACK 상태를 출력용 변수로 준비한다. (없으면 false)
if has_flag "--dry-run" "$@"; then
  # 커맨드라인 인자에 --dry-run이 직접 들어오면
  dry_run_state="true"
  # 실제 적용 상태를 true로 표시한다.
fi
if has_flag "--force-fallback" "$@"; then
  # 커맨드라인 인자에 --force-fallback이 직접 들어오면
  force_fallback_state="true"
  # 실제 적용 상태를 true로 표시한다.
fi

echo "[inganmi-synth-lab] bootstrap runner (hybrid)"
# 실행 시작 배너를 출력한다.
echo "- provider: ${LLM_PROVIDER:-gemini}"
# 현재 provider 설정값을 출력한다. (미설정 시 gemini)
echo "- dry-run: ${dry_run_state}"
# dry-run 적용 여부를 출력한다.
echo "- force-fallback: ${force_fallback_state}"
# fallback 강제 여부를 출력한다.

mkdir -p "${ROOT_DIR}/docs/experiments"
# 실험 결과 디렉토리를 미리 생성한다. (-p: 이미 있으면 오류 없이 통과)

"${PYTHON_BIN}" "${ROOT_DIR}/src/poc/run_once.py" "$@"
# Python 본체를 실행한다.
# "$@"를 그대로 전달해 --dry-run, --force-fallback, --input 같은 옵션을 유지한다.
