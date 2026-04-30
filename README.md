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

입력 동작:
- `--input`을 생략하면 내부 샘플(`inline_seed`) 2건으로 실행
- `--input data/sample.csv`를 주면 해당 CSV를 읽어서 실행
- 실행 로그에서 입력 출처 확인: `inputs.source` (`inline_seed` 또는 CSV 경로)
- 실행 로그에서 입력 의미 축 확인: `inputs.dimensions` (`surface`, `funnel_stage`, `risk_type`, `persona_tag`)

입력 컬럼 의미:
- `surface`: 시나리오가 발생하는 접점/플랫폼 (`mobile`, `web` 등)
- `funnel_stage`: 사용자 여정 단계 (`entry`, `activate`, `retain`)
- `risk_type`: 문제 성격 (`confusion`, `friction`, `error-recovery`)
- `persona_tag`: 특히 민감한 페르소나 라벨 (`벼락치기형`, `완벽주의형`, `불안·회피형` 등)
- 해석 순서: `어디서(surface) → 어느 단계에서(funnel_stage) → 어떤 문제(risk_type) → 누가 특히 아픈지(persona_tag)`

CSV 예시:
```csv
scenario,surface,funnel_stage,risk_type,persona_tag
신규 온보딩 CTA 이해도,mobile,entry,confusion,벼락치기형
회고 작성 완료 동선,web,activate,friction,완벽주의형
실패 후 재시도 복구 경로,mobile,retain,error-recovery,불안·회피형
```

CSV로 실행:
```bash
bash scripts/run_bootstrap.sh --input data/sample.csv
```

결과:
- `docs/experiments/<run_id>.json`
- `docs/experiments/<run_id>.md`

스키마:
- `docs/experiments/LOG_SCHEMA.md`

## 상태
- bootstrap 단계 (저비용 운영)

## License
- MIT
- 상세 원문은 `LICENSE` 파일 참조

MIT 요약:
- 허용: 상업적 이용, 수정, 배포, 사적 사용, 재라이선스 가능
- 조건: 저작권 고지와 라이선스 문구를 포함해야 함
- 면책: 소프트웨어는 "있는 그대로(AS IS)" 제공되며, 작성자는 책임을 지지 않음
