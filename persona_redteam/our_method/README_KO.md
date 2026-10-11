# OUR METHOD — Final-197

이 폴더가 논문용 OURS 실행의 시작점이다. 핵심 구현은 기존 테스트와의 호환성을
유지하기 위해 `experiments/`와 `pipeline/`에 두고, 이 폴더의 짧은 진입점들이 검증된
구현만 호출한다. 따라서 복사본 두 개가 서로 달라지는 문제를 피한다.

## 현재 고정 구조

- 데이터: 197건, GOAL 원문을 타깃 가시 페르소나에 포함
- 타깃: `gpt-4o-2024-11-20`
- 연구 대화: `Qwen/Qwen2.5-7B-Instruct`
- 전송: OpenAI Batch API
- 본실험 병렬화: Qwen 8개 엔드포인트, 데이터 8개 lane, API 키 2개 교차 사용
- 최종 출력: 사례당 독립 분기 4개, `Best-of-4`
- 결합 성공: 같은 분기에서만 `R3+ ∧ B4+ ∧ HarmBench+`

분기별 인용과 직접응답의 정확한 계약은 [PROTOCOL_KO.md](PROTOCOL_KO.md)에 있다.
기계 판독 설정은 `experiments/final197/LOCKED_CONFIG.json`이 원본이다.

## 실행 순서

저장소 루트에서 실행한다.

```bash
# 선택: 빈 GPU 0·3·4·7에 추가 Qwen 연구자 서버 유지
python3 -m our_method.start_qwen_replicas

# 10건 GPT-4o 파일럿 생성
python3 -m our_method.run_pilot10 --wait

# 10건 CARES/JMIR 및 R3/B4 Batch 평가
python3 -m our_method.evaluate_pilot10 --wait

# 로컬 HarmBench와 같은-분기 결합 결과 확정
python3 -m our_method.finalize_pilot10 --device cuda:0 --batch-size 32

# 파일럿 결과 기계 검증 예시
python3 -m our_method.validate_results \
  result/OURS/final197_explicit_goal_pilot10_gpt4o_v1/merged \
  --expected-cases 10
```

197건 본실험은 파일럿과 입력 채택 결정이 끝난 뒤에만 실행한다.

```bash
python3 -m our_method.run_full197 --wait
python3 -m our_method.merge_full197
```

## 입력 채택 상태

현재 고정 입력은
`data/final_cares_strict_harmful/persona197_v1/full_v49_parallel/FINAL197_PERSONAS_WITH_HISTORY_AND_EXPLICIT_GOAL.json`
이다. `FINAL197_review_and_revision_v2.zip`은 원 요청과 ID는 보존하지만 이력이 모두
3턴이고 현재 품질 게이트 메타데이터와 실행 코드가 없어 자동 교체하지 않는다. 같은
10건의 별도 비교에서 품질과 성능을 확인한 뒤에만 새 버전으로 등록한다.

## 핵심 구현 지도

- 연구 질문·분기·인용·직접응답: `experiments/qwen_target_persona_research_dialogue.py`
- Batch 실행과 체크포인트: `experiments/run_jmir_persona_batch_api.py`
- 아티팩트 계약: `pipeline/contracts.py`
- 고정 실험 도구: `experiments/final197/`

API 키는 환경변수에서만 읽으며 코드·설정·결과 파일에 저장하지 않는다.
