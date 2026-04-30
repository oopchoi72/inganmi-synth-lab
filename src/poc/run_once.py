#!/usr/bin/env python3
# 이 스크립트를 시스템의 python3 인터프리터로 실행한다.
from __future__ import annotations
# 파이썬 버전에 따른 타입 힌트 평가 이슈를 줄이기 위해 지연 평가를 켠다.

import argparse
# CLI 인자(--dry-run, --input 등) 파싱용 표준 모듈.
import csv
# CSV 입력 파일을 읽기 위한 표준 모듈.
import json
# JSON 로그 직렬화/역직렬화용 모듈.
import os
# 환경변수(.env export 값) 접근용 모듈.
import urllib.error
# Gemini HTTP 호출 실패 예외 타입 처리용 모듈.
import urllib.request
# 외부 의존성 없이 HTTP 요청을 보내기 위한 표준 모듈.
from dataclasses import dataclass
# 설정 객체를 간결하게 정의하기 위한 dataclass 데코레이터.
from datetime import datetime
# 타임스탬프(run_id, 로그 시간) 생성용 모듈.
from pathlib import Path
# 경로 연산을 안전하게 처리하기 위한 Path 객체.
from typing import Any
# payload 타입 힌트(dict[str, Any])에 사용.


def now_ts() -> str:
    # 파일명/실행ID 충돌 방지를 위해 마이크로초 포함 로컬 시각 문자열을 만든다.
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")


def utc_iso() -> str:
    # 로그 표준 타임스탬프를 UTC ISO-8601 포맷으로 반환한다.
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


@dataclass
class Settings:
    # 사용할 LLM 제공자(현재는 gemini만 실사용).
    provider: str
    # 데이터 소스 모드(manual_csv, readonly_api 등) 메타정보.
    data_source_mode: str
    # 월 예산(USD) 메타값.
    monthly_budget_usd: float
    # 1회 실행당 허용 토큰 상한.
    max_tokens_per_run: int
    # LLM 사용 가능해도 fallback을 강제할지 여부.
    force_fallback: bool
    # 외부 LLM 호출을 생략(dry-run)할지 여부.
    dry_run: bool
    # 입력 CSV 경로(없으면 inline_seed 사용).
    input_csv: str | None


def parse_args() -> argparse.Namespace:
    # CLI 파서를 생성한다.
    parser = argparse.ArgumentParser(description="Run one synth-lab POC experiment")
    # 외부 API 호출 자체를 막는 옵션.
    parser.add_argument("--dry-run", action="store_true", help="Skip external LLM calls")
    # LLM 키가 있어도 fallback 경로를 강제하는 옵션.
    parser.add_argument("--force-fallback", action="store_true", help="Force non-LLM mode")
    # 읽기 전용 CSV 입력 경로를 받는 옵션.
    parser.add_argument("--input", dest="input_csv", help="Optional read-only CSV path")
    # 파싱 결과 Namespace를 반환한다.
    return parser.parse_args()


def read_settings(args: argparse.Namespace) -> Settings:
    # 환경변수 + CLI 인자를 합쳐 실행 설정 객체를 만든다.
    return Settings(
        # provider는 소문자로 정규화한다.
        provider=os.getenv("LLM_PROVIDER", "gemini").strip().lower(),
        # 데이터 소스 모드는 로그 메타로 남긴다.
        data_source_mode=os.getenv("DATA_SOURCE_MODE", "manual_csv").strip(),
        # 월 예산 기본값 30달러.
        monthly_budget_usd=float(os.getenv("MONTHLY_BUDGET_USD", "30")),
        # 1회 실행 최대 토큰 기본값 4000.
        max_tokens_per_run=int(os.getenv("MAX_TOKENS_PER_RUN", "4000")),
        # CLI가 우선이며, 그다음 환경변수 FORCE_FALLBACK=true를 반영한다.
        force_fallback=bool(args.force_fallback or os.getenv("FORCE_FALLBACK", "").lower() == "true"),
        # CLI가 우선이며, 그다음 환경변수 DRY_RUN=true를 반영한다.
        dry_run=bool(args.dry_run or os.getenv("DRY_RUN", "").lower() == "true"),
        # CSV 경로는 CLI 인자 그대로 사용한다.
        input_csv=args.input_csv,
    )


def estimate_tokens(input_count: int, persona_count: int) -> int:
    # 아주 단순한 휴리스틱 기반 토큰 추정치 계산.
    base = 900
    # 입력 건수/페르소나 수가 늘수록 선형으로 증가시킨다.
    return base + input_count * 180 + persona_count * 120


def has_provider_key(provider: str) -> bool:
    # provider별 키를 읽어와 존재 여부만 판단한다.
    key_map = {
        "openai": os.getenv("OPENAI_API_KEY", "").strip(),
        "anthropic": os.getenv("ANTHROPIC_API_KEY", "").strip(),
        "gemini": os.getenv("GEMINI_API_KEY", "").strip(),
    }
    # 지원하지 않는 provider면 빈 문자열로 처리되어 False가 된다.
    return bool(key_map.get(provider, ""))


def load_rows(input_csv: str | None) -> tuple[list[dict[str, str]], str]:
    # CSV 경로가 없으면 내부 시드 데이터(inline_seed)로 실행한다.
    if not input_csv:
        return (
            [
                {
                    "scenario": "신규 온보딩 CTA 이해도",
                    "surface": "mobile",
                    "funnel_stage": "entry",
                    "risk_type": "confusion",
                    "persona_tag": "벼락치기형",
                },
                {
                    "scenario": "회고 작성 완료 동선",
                    "surface": "web",
                    "funnel_stage": "activate",
                    "risk_type": "friction",
                    "persona_tag": "완벽주의형",
                },
            ],
            "inline_seed",
        )

    # CSV 경로가 있으면 Path 객체로 감싼다.
    path = Path(input_csv)
    # 파일이 없으면 즉시 예외를 던져 호출자에서 실패를 인지하게 한다.
    if not path.exists():
        raise FileNotFoundError(f"input csv not found: {path}")

    # UTF-8로 파일을 열고 DictReader로 헤더 기반 파싱한다.
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # 각 행을 일반 dict로 변환해 리스트에 담는다.
        rows = [dict(r) for r in reader]
    # (행 데이터, 입력 출처 문자열) 형태로 반환한다.
    return rows, str(path)


def summarize_input_dimensions(rows: list[dict[str, str]]) -> dict[str, dict[str, int]]:
    # 입력 row에서 핵심 축(surface/funnel_stage/risk_type/persona_tag) 분포를 집계한다.
    dimensions = {
        "surface": {},
        "funnel_stage": {},
        "risk_type": {},
        "persona_tag": {},
    }
    for row in rows:
        for key in dimensions:
            value = str(row.get(key, "unknown")).strip() or "unknown"
            dimensions[key][value] = dimensions[key].get(value, 0) + 1
    return dimensions


def make_persona_summary() -> list[dict[str, str]]:
    # 최소 실행 보장을 위한 기본 페르소나 요약(LLM 실패/미사용 시에도 사용 가능).
    return [
        {"persona": "완벽주의형", "finding": "세부 제어/되돌리기 노출이 부족하면 즉시 신뢰 하락"},
        {"persona": "벼락치기형", "finding": "첫 화면에서 즉시 실행 CTA가 없으면 이탈 위험"},
        {"persona": "불안·회피형", "finding": "오류 카피가 공격적으로 느껴지면 재시도율 감소"},
    ]


def call_gemini_once(rows: list[dict[str, str]]) -> str:
    # Gemini API 키를 읽는다.
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    # 키가 없으면 즉시 실패시켜 fallback 경로로 내려가게 한다.
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is empty")

    # 모델명은 환경변수로 바꿀 수 있게 두고 기본값을 제공한다.
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()
    # Gemini generateContent 엔드포인트를 구성한다.
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    # 실험 입력(rows)을 그대로 프롬프트에 포함한다.
    prompt = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "너는 합성소비자 UX 리뷰어다. 아래 시나리오를 보고 리스크 3개와 개선안 3개를 한국어로 짧게 정리해.\n"
                            "각 항목의 funnel_stage, risk_type, persona_tag를 반영해서 분석해.\n"
                            f"rows={json.dumps(rows, ensure_ascii=False)}"
                        )
                    }
                ]
            }
        ]
    }
    # JSON 문자열을 UTF-8 바이트로 인코딩해 HTTP body로 보낸다.
    payload = json.dumps(prompt).encode("utf-8")
    # POST 요청 객체를 생성한다.
    req = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    # 네트워크 호출을 시도한다.
    try:
        # timeout=25초로 장시간 대기를 제한한다.
        with urllib.request.urlopen(req, timeout=25) as resp:
            # 응답 본문을 문자열로 읽는다.
            body = resp.read().decode("utf-8")
            # JSON 파싱한다.
            data = json.loads(body)
    # HTTP 상태코드 오류(4xx/5xx)는 본문을 포함해 예외로 감싼다.
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini HTTPError {e.code}: {detail}") from e
    # DNS/연결 등 URL 레벨 오류 처리.
    except urllib.error.URLError as e:
        raise RuntimeError(f"Gemini URLError: {e.reason}") from e

    # Gemini 응답에서 candidates 배열을 추출한다.
    candidates = data.get("candidates", [])
    # 후보가 없으면 비정상 응답으로 간주한다.
    if not candidates:
        raise RuntimeError("Gemini response has no candidates")
    # 첫 후보의 content.parts를 읽는다.
    parts = candidates[0].get("content", {}).get("parts", [])
    # part 중 text가 있는 항목만 수집한다.
    texts = [p.get("text", "") for p in parts if p.get("text")]
    # 여러 텍스트 파트를 줄바꿈으로 합친다.
    text = "\n".join(texts).strip()
    # 텍스트가 비어 있으면 실패 처리한다.
    if not text:
        raise RuntimeError("Gemini response text is empty")
    # 최종 요약 텍스트 반환.
    return text


def ensure_dirs(root: Path) -> Path:
    # 실험 로그 출력 디렉토리 경로를 계산한다.
    out_dir = root / "docs" / "experiments"
    # 디렉토리가 없으면 부모까지 생성한다.
    out_dir.mkdir(parents=True, exist_ok=True)
    # 생성/확인된 경로를 반환한다.
    return out_dir


def write_json(path: Path, payload: dict[str, Any]) -> None:
    # JSON 로그 파일을 UTF-8로 쓴다.
    with path.open("w", encoding="utf-8") as f:
        # 한글 보존(ensure_ascii=False), 사람이 읽기 쉬운 들여쓰기.
        json.dump(payload, f, ensure_ascii=False, indent=2)
        # POSIX 스타일 newline 보장.
        f.write("\n")


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    # outputs 하위 필드를 안전하게 꺼낸다.
    outputs = payload.get("outputs", {})
    # 마크다운 템플릿의 기본 줄 목록을 만든다.
    lines = [
        "# Experiment Log",
        "",
        f"- run_id: {payload['run_id']}",
        f"- timestamp: {payload['timestamp']}",
        f"- mode: {payload['mode']}",
        f"- provider: {outputs.get('provider', 'none')}",
        f"- data_source_mode: {payload['data_source_mode']}",
        f"- input_rows: {outputs.get('input_rows', 0)}",
        f"- status: {payload['status']}",
        f"- cost_estimate_usd: {payload['cost_estimate_usd']}",
        "",
        "## Input dimensions",
    ]
    input_dimensions = payload.get("inputs", {}).get("dimensions", {})
    for dim_name, counts in input_dimensions.items():
        lines.append(f"- {dim_name}: {counts}")

    lines.extend(
        [
            "",
        "## Persona highlights",
        ]
    )
    # persona_highlights를 bullet로 순회 추가한다.
    for item in outputs.get("persona_highlights", []):
        lines.append(f"- {item['persona']}: {item['finding']}")

    # 에러가 있으면 Error 섹션을 추가한다.
    error = payload.get("error")
    if error:
        lines.extend(["", "## Error", f"- {error}"])

    # 최종 문자열을 파일에 저장한다.
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_payload(
    run_id: str,
    settings: Settings,
    mode: str,
    status: str,
    estimated_tokens: int,
    budget_check_passed: bool,
    inputs_ref: str,
    input_rows: int,
    input_dimensions: dict[str, dict[str, int]],
    llm_summary: str | None,
    error: str | None,
) -> dict[str, Any]:
    # 고정 스키마(JSON 로그) 딕셔너리를 구성한다.
    return {
        "run_id": run_id,
        "timestamp": utc_iso(),
        "mode": mode,
        "data_source_mode": settings.data_source_mode,
        "budget": {
            "monthly_budget_usd": settings.monthly_budget_usd,
            "max_tokens_per_run": settings.max_tokens_per_run,
            "estimated_tokens": estimated_tokens,
            "budget_check_passed": budget_check_passed,
        },
        "inputs": {
            "source": inputs_ref,
            "row_count": input_rows,
            "dimensions": input_dimensions,
        },
        "outputs": {
            "provider": settings.provider if mode == "llm" else "fallback",
            "input_rows": input_rows,
            "persona_highlights": make_persona_summary(),
            "llm_summary": llm_summary,
        },
        # fallback은 비용 0, llm은 단순 추정치 계산.
        "cost_estimate_usd": 0.0 if mode == "fallback" else round(estimated_tokens * 0.000002, 6),
        "status": status,
        "error": error,
    }


def run() -> int:
    # 1) CLI 인자를 파싱한다.
    args = parse_args()
    # 2) 환경변수+CLI를 합쳐 설정을 만든다.
    settings = read_settings(args)
    # 3) 현재 파일 기준으로 프로젝트 루트를 계산한다.
    project_root = Path(__file__).resolve().parents[2]
    # 4) 로그 출력 디렉토리를 준비한다.
    out_dir = ensure_dirs(project_root)
    # 5) 이번 실행의 고유 run_id를 생성한다.
    run_id = now_ts()

    # 6) 입력 행 데이터를 로드한다. (CSV 또는 inline_seed)
    rows, inputs_ref = load_rows(settings.input_csv)
    # 입력 의미 축 분포를 집계한다.
    input_dimensions = summarize_input_dimensions(rows)
    # 7) 토큰 추정치를 계산한다.
    estimated_tokens = estimate_tokens(len(rows), persona_count=3)
    # 8) 실행당 토큰 상한을 넘는지 검사한다.
    budget_check_passed = estimated_tokens <= settings.max_tokens_per_run

    # 9) LLM 사용 가능 조건을 모두 만족하는지 계산한다.
    should_use_llm = (
        not settings.dry_run
        and not settings.force_fallback
        and has_provider_key(settings.provider)
        and settings.provider in {"gemini"}
    )
    # 10) 실행 모드를 결정한다.
    mode = "llm" if should_use_llm else "fallback"

    # 11) 예산 가드 실패 시 즉시 차단 로그를 남기고 종료한다.
    if not budget_check_passed:
        payload = build_payload(
            run_id=run_id,
            settings=settings,
            mode=mode,
            status="blocked_by_budget",
            estimated_tokens=estimated_tokens,
            budget_check_passed=False,
            inputs_ref=inputs_ref,
            input_rows=len(rows),
            input_dimensions=input_dimensions,
            llm_summary=None,
            error=f"estimated tokens {estimated_tokens} exceed MAX_TOKENS_PER_RUN {settings.max_tokens_per_run}",
        )
        # 차단 결과도 JSON/MD 두 포맷으로 남긴다.
        json_path = out_dir / f"{run_id}.json"
        md_path = out_dir / f"{run_id}.md"
        write_json(json_path, payload)
        write_markdown(md_path, payload)
        # 호출자가 경로를 바로 알 수 있게 표준출력에 남긴다.
        print(f"blocked_by_budget: {json_path}")
        print(f"blocked_by_budget: {md_path}")
        # 종료코드 2 = 예산 차단.
        return 2

    # 기본 성공 상태를 먼저 세팅한다.
    llm_summary = None
    status = "success"
    error = None
    # 12) llm 모드일 때만 Gemini를 호출한다.
    if mode == "llm":
        try:
            llm_summary = call_gemini_once(rows)
        # LLM 실패 시 전체 실패로 끊지 않고 fallback으로 다운그레이드한다.
        except Exception as e:
            mode = "fallback"
            status = "success_with_fallback"
            error = str(e)

    # 13) 최종 payload를 구성한다.
    payload = build_payload(
        run_id=run_id,
        settings=settings,
        mode=mode,
        status=status,
        estimated_tokens=estimated_tokens,
        budget_check_passed=True,
        inputs_ref=inputs_ref,
        input_rows=len(rows),
        input_dimensions=input_dimensions,
        llm_summary=llm_summary,
        error=error,
    )
    # 14) 결과 로그 파일(JSON/MD)을 저장한다.
    json_path = out_dir / f"{run_id}.json"
    md_path = out_dir / f"{run_id}.md"
    write_json(json_path, payload)
    write_markdown(md_path, payload)

    # 15) 결과 파일 경로를 출력한다.
    print(f"experiment_json={json_path}")
    print(f"experiment_md={md_path}")
    # 정상 종료코드 0.
    return 0


if __name__ == "__main__":
    # 스크립트 직접 실행 시 run()의 종료코드를 프로세스 종료코드로 전달한다.
    raise SystemExit(run())
