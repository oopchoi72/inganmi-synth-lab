# Experiment Log Schema

POC 1회 실행 로그는 항상 `docs/experiments/<run_id>.json` + `<run_id>.md` 2개를 생성한다.

## JSON schema (fixed keys)

```json
{
  "run_id": "YYYY-MM-DD_HH-MM-SS_microseconds",
  "timestamp": "UTC ISO-8601",
  "mode": "llm | fallback",
  "data_source_mode": "manual_csv | readonly_api",
  "budget": {
    "monthly_budget_usd": 30.0,
    "max_tokens_per_run": 4000,
    "estimated_tokens": 1620,
    "budget_check_passed": true
  },
  "inputs": {
    "source": "inline_seed | /absolute/or/relative/path.csv",
    "row_count": 2
  },
  "outputs": {
    "provider": "gemini | openai | anthropic | fallback",
    "input_rows": 2,
    "llm_summary": "string | null",
    "persona_highlights": [
      {
        "persona": "완벽주의형",
        "finding": "..."
      }
    ]
  },
  "cost_estimate_usd": 0.0,
  "status": "success | success_with_fallback | blocked_by_budget",
  "error": null
}
```

## Status semantics

- `success`: budget guard 통과 후 결과 생성 완료
- `success_with_fallback`: LLM 호출 실패 후 fallback으로 결과 생성
- `blocked_by_budget`: 토큰 추정치가 `MAX_TOKENS_PER_RUN` 초과

## Notes

- 로그는 반드시 append 방식(새 파일 생성)으로 남긴다.
- 읽기 전용 입력만 사용한다. 원본 데이터 파일을 수정하지 않는다.
