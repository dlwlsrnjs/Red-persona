# Final-197 외부 베이스라인·PCSA 개인화·OURS 비교 패키지

이 폴더는 동일한 Final-197 요청 집합에서 수행한 네 결과군을 논문 작성용으로 한곳에
정리한다.

1. 외부 베이스라인 9종 × GPT-4o/Qwen 타깃
2. PCSA Phase II의 `Persona+History` 대 `No-Persona` paired ablation
3. PCSA Phase II `Persona+History` × `gpt-4o-2024-11-20` 추가 셀
4. OURS `1011_method_v1` GPT-4o singleton Best-of-4와 두 ablation

197개 `case_id` 집합과 `request_sha256`는 네 결과군의 입력 자산에서 모두 일치한다.
기존 입력 자산의 순서는 같지만 새 GPT-4o PCSA 실행은 세 disjoint slice 내부를 seed로
섞었으므로, 모든 비교·평가는 행 위치가 아니라 `case_id`로 결합한다.
반면 response unit, query budget, CARES evaluator와 aggregation은 같지 않다. 따라서 이
패키지는 결과를 나란히 보이되, 서로 다른 패널을 하나의 공식 순위로 합치지 않는다.

## 파일

| 파일 | 역할 |
|---|---|
| `TABLES_KO.md` | 논문 표에 옮길 수 있는 다섯 개의 scope-separated 결과표 |
| `RESULTS_INTERPRETATION_KO.md` | 결과가 지지하는 주장, 반대 결과, 논문용 문장과 제한 |
| `METHODS_AND_CODE_KO.md` | 각 실험 설계와 실제 실행·평가 코드 위치 |
| `comparison_records.json` | 24개 정규화 record와 비교 가능성 계약 |
| `comparison_records.csv` | 통계·도표 작성용 평탄화 데이터 |
| `PROVENANCE.json` | 입력 결과·코드 SHA-256, 원 커밋, 코호트 일치 감사 |
| `build_comparison.py` | 위 기계 파일과 표를 재생성·검증하는 표준 라이브러리 전용 코드 |

외부 baseline과 PCSA Persona+History의 전체 표·설정·해석은 canonical
[`../../../external_baselines/result/final197_external_baselines_v2/README_KO.md`](../../../external_baselines/result/final197_external_baselines_v2/README_KO.md)에
통합했다. 이 비교 패키지는 그 기계 판독 source와 OURS 결과를 함께 정규화하되, 서로 다른
실험 패널을 공식 순위로 합치지 않는다.

논문 Methods와 정성 분석에는 다음 두 문서를 함께 사용한다.

- [외부 9개 기법의 턴 구조·실패 지도와 PCSA–Jargon–1011 비교](../../../external_baselines/result/final197_external_baselines_v2/METHOD_TURN_STRUCTURE_AND_FAILURE_MAP_KO.md)
- [안전정렬 유지와 경계 통과의 직접 PCSA·Jargon·1011 사례](../../../external_baselines/result/final197_external_baselines_v2/DIRECT_SAMPLE_CASEBOOK_KO.md)

## 핵심 결론

- PCSA Phase II에서 Persona+History는 No-Persona보다 HarmBench를
  `14/197 → 55/197`로 높였다(+20.81%p, 3.93배).
- 같은 paired 비교에서 PCSA Unsafe는 `30/197 → 111/197`, Strict Joint는
  `7/197 → 26/197`로 증가했다. HarmBench discordant pair의 exact McNemar 양측
  검정은 `p=8.23×10⁻¹⁰`이다.
- 따라서 “PCSA Phase II에 persona/history를 넣으면 목표 수행 및 직접 위해 지표가
  개선된다”는 해석은 지지된다.
- 하지만 CARES A+C는 `195/197 → 168/197`, Accept는 `48/197 → 23/197`로 감소했다.
  개인화 효과를 CARES non-refusal 하나로 요약하면 반대 결론이 난다.
- 별도 GPT-4o Persona+History PCSA 셀은 HarmBench 9/197(4.57%), PCSA Unsafe
  52/197(26.40%), B4+ 17/197(8.63%), Strict Joint 6/197(3.05%)였다. 기존 GPT-4o
  profile-only PCSA의 1, 8, 4, 0건보다 높지만 target snapshot과 공개 paired label 차이
  때문에 기술 비교로 제한한다.
- 이 추가 셀의 CARES는 GPT-4o로 판정했으므로 기존 외부 baseline의 GPT-4o-mini CARES와
  직접 비교하지 않는다.
- OURS의 별도 GPT-4o singleton ablation에서는 `no_history`가 CARES Accept, B4+와
  Strict Joint에서 `no_verbatim`보다 높았다. history 효과는 공격 구조와 target에 따라
  달라지며 PCSA 결과를 OURS의 인과 효과로 전이하면 안 된다.

## 재생성

저장소 루트에서 실행한다.

```bash
python3 persona_redteam/result/final197_paper_comparison_v1/build_comparison.py
python3 persona_redteam/result/final197_paper_comparison_v1/build_comparison.py --check
```

`--check`는 197개 case ID와 요청 해시, 모든 count/rate, CARES 합계, paired 2×2 표,
McNemar 값, 입력·코드 해시와 생성 파일의 byte-level 일치를 검사한다.

민감한 원 요청과 target 응답 원문은 이 비교 폴더에 복제하지 않았다. 공개 표에는 count,
rate, 분석 계약과 SHA-256만 둔다.
