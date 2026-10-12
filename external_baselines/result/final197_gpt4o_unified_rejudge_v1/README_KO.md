# Final-197 GPT-4o 통일 재평가 현황과 복구 계획

## 결론

현재 canonical `all_results.csv`는 CARES와 R/B evaluator가 완전히 통일되어 있지
않다. CARES는 21개 셀 중 20개가 `gpt-4o-mini-2024-07-18`, R/B는 21개 셀
전부가 `gpt-4o-mini-2024-07-18`이다. 따라서 현재 GPT-4o evaluator를 사용한
OURS 결과와 judge-sensitive 지표를 직접 비교하려면 저장된 동일 target 응답을
`gpt-4o-2024-11-20`으로 다시 판정해야 한다.

이 작업은 **공격을 다시 생성하는 실험이 아니라 저장 응답의 post-hoc 재평가**다.
집계 CSV의 개수만으로 사례별 라벨을 복원할 수 없으므로 사례별 평가 입력이
필수다.

## 감사 결과

| 항목 | 수량 |
|---|---:|
| canonical 결과 셀 | 21 |
| CARES GPT-4o-mini 셀 | 20 |
| R/B GPT-4o-mini 셀 | 21 |
| 원응답이 필요한 셀 | 20 |
| 복구해야 하는 고유 사례 응답 | 3,940 = 20×197 |
| CARES 재평가 요청 | 3,940 |
| R/B 재평가 요청 | 4,137 = 21×197 |

원응답이 필요한 20개 셀은 기존 9개 방법×2개 target matrix 18셀과 Qwen PCSA
개인화 ablation 2셀이다. 셀별 상태는 `CELL_STATUS.csv`에 기록했다.

별도의 query-16 실험 6셀은 이미 GPT-4o CARES/R/B로 평가됐지만, target 호출
예산과 실행 계약이 다른 sensitivity experiment다. 이를 기존 4-turn matrix의
누락 원응답 대신 사용하거나 같은 행으로 덮어쓰지 않는다.

## 현재 확보된 자료

- Final-197 197개 요청과 `case_id`
- CARES 공식 프롬프트와 실행 코드
- R/B v3 프롬프트, literal-evidence 검증 및 재시도 코드
- HarmBench와 PCSA final-judge 결과
- 기존 `all_results.csv`, JSON, 표 및 집계 코드
- GPT-4o PCSA Persona+History 추가 셀의 197개 evaluation input
- query-16 6셀의 원응답 및 GPT-4o 평가 결과

GPT-4o PCSA Persona+History 추가 셀의 R/B 재평가는 Batch로 실행했다. 197개 중
195개는 검증 완료됐고 2개는 세 번의 재시도 후에도 evaluator가 실제 응답의
literal substring이 아닌 evidence를 반환해 `invalid_evaluator_output`으로 남았다.
두 사례는 점수를 임의로 채우지 않고 별도 복구 대상으로 유지한다.

## 현재 없는 자료

다음 20개 셀의 사례별 저장 응답 또는 그 응답을 포함하는 evaluation input이
현재 Git과 확인된 로컬 작업 폴더에 없다.

1. 기존 matrix: GPT-4o 9개 방법, Qwen 9개 방법
2. Qwen PCSA ablation: No-Persona, Persona+History

정확한 GPT-4o target snapshot이 기록되지 않은 기존 matrix를 지금 다시 생성하면
target 응답 자체가 바뀔 수 있다. 따라서 이를 동일 응답 재평가라고 부르면 안 된다.

## 복구 파일의 최소 조건

전체 공격 실행 로그가 반드시 필요한 것은 아니다. 다음 중 하나가 셀마다 197개
`case_id`를 완전히 포함하면 충분하다.

1. `official_evaluation/.../input.jsonl`
2. 과거 CARES 또는 R/B Batch의 `input.jsonl`
3. `case_id`, 원 GOAL/요청, 최종 target prompt, 최종 target response, 필요한
   대화 문맥을 포함한 JSON/JSONL
4. 과거 Batch 파일을 소유한 OpenAI project의 접근 가능한 파일

집계 `all_results.csv`, summary JSON, A/C/R 개수만으로는 재평가할 수 없다.

## 복구 후 실행 순서

1. 각 셀에서 197개 `case_id`의 집합과 Final-197 순서를 검사한다.
2. 응답 문자열 hash를 저장해 재평가 중 생성 결과가 바뀌지 않았음을 보장한다.
3. CARES 20셀과 R/B 21셀을 `gpt-4o-2024-11-20` OpenAI Batch로 실행한다.
4. R/B evidence가 literal substring인지 자동 검증하고 실패 사례만 재시도한다.
5. 최종 invalid가 0인지 확인한다. 해결되지 않은 행은 실패 정책을 명시하고 별도
   보고하며 임의 라벨을 넣지 않는다.
6. 기존 CSV를 보존하고 새 파일 `all_results_gpt4o_judged.csv`를 생성한다.
7. evaluator snapshot과 입력·출력 hash를 새 AUDIT에 고정한다.

현재 토큰 길이를 기준으로 평가-only 예상 비용은 약 USD 40--70이다. 공격 생성부터
다시 수행하는 비용은 포함하지 않는다.

## 논문 보고 원칙

전체 통일 재평가가 끝나기 전에는 기존 GPT-4o-mini CARES/R/B 행과 GPT-4o judge
OURS 행을 judge-invariant 절대 순위처럼 제시하지 않는다. 사용할 경우 evaluator
snapshot 차이를 표와 본문에 명시한다. 원응답이 복구되지 않아 공격을 다시 실행하면
그 결과는 별도의 replication table로 보고한다.

API 키와 원 유해 응답은 이 폴더에 저장하지 않는다.
