# inganmi-synth-lab

inganmi 합성 소비자(Synthetic Consumer) 실험용 분리 프로젝트.

## 목적
- 기존 `inganmi-app` 코드에 영향 없이 가설 검증
- 페르소나 기반 UX 리뷰/시나리오 실험
- 필요 시 쉽게 중단/삭제 가능한 독립 구조

## 원칙
- `inganmi-app` 코드 import 금지
- 읽기 전용 데이터만 사용 (수동 CSV/집계 결과)
- 프로덕션 배포와 분리

## 폴더 구조
- `docs/`: 페르소나/체크리스트/실험 기록
- `src/`: 실험 스크립트 및 샘플 코드
- `scripts/`: 실행 보조 스크립트
- `data/`: 입력/출력 데이터 (git 제외 권장)

## 시작
1. `.env.example`를 참고해 `.env` 생성
2. `docs/persona-cards.md`와 `docs/release-checklist.md`부터 작성
3. 필요한 경우 `scripts/run_bootstrap.sh`로 로컬 실험 실행

## POC 1회 실행 (Hybrid)
- 엔트리: `scripts/run_bootstrap.sh`
- 본체: `src/poc/run_once.py`
- 기본 provider: `gemini` (`GEMINI_API_KEY` 있으면 실제 1회 호출, 없으면 fallback)
- 기본 모델: `GEMINI_MODEL=gemini-1.5-flash`

```bash
bash scripts/run_bootstrap.sh
```

옵션:
- `--dry-run`: LLM 호출 없이 fallback 강제
- `--force-fallback`: 키가 있어도 fallback 강제
- `--input data/sample.csv`: 읽기 전용 CSV 입력 사용

결과:
- `docs/experiments/<run_id>.json`
- `docs/experiments/<run_id>.md`

스키마:
- `docs/experiments/LOG_SCHEMA.md`

## 상태
- bootstrap 단계 (저비용 운영)
