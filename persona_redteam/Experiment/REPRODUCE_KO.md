# Official-500 재현 절차

프로젝트 루트 `persona_redteam/`에서 실행한다. API 키는 파일이나 명령행에 넣지 않고 현재 쉘의
`OPENAI_API_KEY` 환경변수로만 제공한다.

> **현재 비용 정책:** 추가 API 예산이 없으므로 기본 동작은 무호출 preflight뿐이다. 새 실행이
> 다시 승인되더라도 OpenAI 호출은 Batch API만 사용한다. standard endpoint는 이번 완료 실행의
> provenance일 뿐, 후속 실행 경로로 사용하지 않는다.

## 1. 무호출 preflight

```bash
python -m ablation.cares_jmir_rq.evaluate --api-mode batch
```

이 단계는 11개 arm의 case/direction pairing, 재사용 행, 신규 요청 수와 예상 비용만 검사하며
API 호출을 하지 않는다.

## 2. 누락분만 평가

```bash
python -m ablation.cares_jmir_rq.evaluate \
  --api-mode batch \
  --output-dir data/evaluations/ablation_cares_jmir_rq_official500_context \
  --execute
```

큰 Batch가 늦어도 standard tail로 전환하지 않는다. checkpoint를 유지한 채 Batch 완료를
기다리거나, Batch를 취소한 뒤 다음 승인 시 미완료 custom ID만 새 Batch로 제출한다.

이번 확정 실행은 Batch가 0건에서 장시간 정체되어 standard checkpoint 디렉터리에서 끝냈다.
이는 이미 발생한 실행 provenance를 투명하게 남기는 설명이며 재실행 권고가 아니다. 완료된
22,000개 공개 label과 집계는 추가 호출 없이 그대로 재사용한다.

## 3. 결과 무결성 검사

```bash
python -m pytest -q ablation/cares_jmir_rq/test_evaluate.py experiments/test_*.py
wc -l \
  ablation/cares_jmir_rq/OFFICIAL500_PUBLIC_LABELED.jsonl \
  ablation/cares_jmir_rq/LABELED_ROWS.jsonl \
  ablation/cares_jmir_rq/CARES_HARM_LEVEL_LABELS.jsonl
```

기대값은 cohort 500행, 평가 label 22,000행이다. harm-level 파일은 exact prompt hash로 중복 제거돼
15,038행이며 22,000과 같을 필요가 없다.

## 4. 공개 경계

Git에는 aggregate, label, hash, 공개 source goal만 둔다. target-visible prompt/response 원문,
evaluator rationale와 checkpoint는 `data/`의 Git 제외 경로 및 `/data1/users/ljk98` 원시 산출물에
보관한다.
