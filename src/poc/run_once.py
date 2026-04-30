#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")


def utc_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


@dataclass
class Settings:
    provider: str
    data_source_mode: str
    monthly_budget_usd: float
    max_tokens_per_run: int
    force_fallback: bool
    dry_run: bool
    input_csv: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one synth-lab POC experiment")
    parser.add_argument("--dry-run", action="store_true", help="Skip external LLM calls")
    parser.add_argument("--force-fallback", action="store_true", help="Force non-LLM mode")
    parser.add_argument("--input", dest="input_csv", help="Optional read-only CSV path")
    return parser.parse_args()


def read_settings(args: argparse.Namespace) -> Settings:
    return Settings(
        provider=os.getenv("LLM_PROVIDER", "gemini").strip().lower(),
        data_source_mode=os.getenv("DATA_SOURCE_MODE", "manual_csv").strip(),
        monthly_budget_usd=float(os.getenv("MONTHLY_BUDGET_USD", "30")),
        max_tokens_per_run=int(os.getenv("MAX_TOKENS_PER_RUN", "4000")),
        force_fallback=bool(args.force_fallback or os.getenv("FORCE_FALLBACK", "").lower() == "true"),
        dry_run=bool(args.dry_run or os.getenv("DRY_RUN", "").lower() == "true"),
        input_csv=args.input_csv,
    )


def estimate_tokens(input_count: int, persona_count: int) -> int:
    base = 900
    return base + input_count * 180 + persona_count * 120


def has_provider_key(provider: str) -> bool:
    key_map = {
        "openai": os.getenv("OPENAI_API_KEY", "").strip(),
        "anthropic": os.getenv("ANTHROPIC_API_KEY", "").strip(),
        "gemini": os.getenv("GEMINI_API_KEY", "").strip(),
    }
    return bool(key_map.get(provider, ""))


def load_rows(input_csv: str | None) -> tuple[list[dict[str, str]], str]:
    if not input_csv:
        return (
            [
                {"scenario": "신규 온보딩 CTA 이해도", "surface": "mobile"},
                {"scenario": "회고 작성 완료 동선", "surface": "web"},
            ],
            "inline_seed",
        )

    path = Path(input_csv)
    if not path.exists():
        raise FileNotFoundError(f"input csv not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]
    return rows, str(path)


def make_persona_summary() -> list[dict[str, str]]:
    return [
        {"persona": "완벽주의형", "finding": "세부 제어/되돌리기 노출이 부족하면 즉시 신뢰 하락"},
        {"persona": "벼락치기형", "finding": "첫 화면에서 즉시 실행 CTA가 없으면 이탈 위험"},
        {"persona": "불안·회피형", "finding": "오류 카피가 공격적으로 느껴지면 재시도율 감소"},
    ]


def call_gemini_once(rows: list[dict[str, str]]) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is empty")

    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    prompt = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "너는 합성소비자 UX 리뷰어다. 아래 시나리오를 보고 리스크 3개와 개선안 3개를 한국어로 짧게 정리해.\n"
                            f"rows={json.dumps(rows, ensure_ascii=False)}"
                        )
                    }
                ]
            }
        ]
    }
    payload = json.dumps(prompt).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini HTTPError {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Gemini URLError: {e.reason}") from e

    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini response has no candidates")
    parts = candidates[0].get("content", {}).get("parts", [])
    texts = [p.get("text", "") for p in parts if p.get("text")]
    text = "\n".join(texts).strip()
    if not text:
        raise RuntimeError("Gemini response text is empty")
    return text


def ensure_dirs(root: Path) -> Path:
    out_dir = root / "docs" / "experiments"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    outputs = payload.get("outputs", {})
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
        "## Persona highlights",
    ]
    for item in outputs.get("persona_highlights", []):
        lines.append(f"- {item['persona']}: {item['finding']}")

    error = payload.get("error")
    if error:
        lines.extend(["", "## Error", f"- {error}"])

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
    llm_summary: str | None,
    error: str | None,
) -> dict[str, Any]:
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
        },
        "outputs": {
            "provider": settings.provider if mode == "llm" else "fallback",
            "input_rows": input_rows,
            "persona_highlights": make_persona_summary(),
            "llm_summary": llm_summary,
        },
        "cost_estimate_usd": 0.0 if mode == "fallback" else round(estimated_tokens * 0.000002, 6),
        "status": status,
        "error": error,
    }


def run() -> int:
    args = parse_args()
    settings = read_settings(args)
    project_root = Path(__file__).resolve().parents[2]
    out_dir = ensure_dirs(project_root)
    run_id = now_ts()

    rows, inputs_ref = load_rows(settings.input_csv)
    estimated_tokens = estimate_tokens(len(rows), persona_count=3)
    budget_check_passed = estimated_tokens <= settings.max_tokens_per_run

    should_use_llm = (
        not settings.dry_run
        and not settings.force_fallback
        and has_provider_key(settings.provider)
        and settings.provider in {"gemini"}
    )
    mode = "llm" if should_use_llm else "fallback"

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
            llm_summary=None,
            error=f"estimated tokens {estimated_tokens} exceed MAX_TOKENS_PER_RUN {settings.max_tokens_per_run}",
        )
        json_path = out_dir / f"{run_id}.json"
        md_path = out_dir / f"{run_id}.md"
        write_json(json_path, payload)
        write_markdown(md_path, payload)
        print(f"blocked_by_budget: {json_path}")
        print(f"blocked_by_budget: {md_path}")
        return 2

    llm_summary = None
    status = "success"
    error = None
    if mode == "llm":
        try:
            llm_summary = call_gemini_once(rows)
        except Exception as e:
            mode = "fallback"
            status = "success_with_fallback"
            error = str(e)

    payload = build_payload(
        run_id=run_id,
        settings=settings,
        mode=mode,
        status=status,
        estimated_tokens=estimated_tokens,
        budget_check_passed=True,
        inputs_ref=inputs_ref,
        input_rows=len(rows),
        llm_summary=llm_summary,
        error=error,
    )
    json_path = out_dir / f"{run_id}.json"
    md_path = out_dir / f"{run_id}.md"
    write_json(json_path, payload)
    write_markdown(md_path, payload)

    print(f"experiment_json={json_path}")
    print(f"experiment_md={md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
