# Experiments

이 폴더는 활성 파이프라인의 구현체, 단위 테스트, 탐색 파일럿을 함께 보관한다. 사용자는
가능하면 `python -m pipeline.<command>`를 실행한다.

## 활성 구현체

- `prepare_jmir_persona_eval.py`: blueprint 병합과 case adapter
- `qwen_target_persona_research_dialogue.py`: Qwen–target 누적 연구와 8개 분기
- `run_jmir_persona_eval_batch.py`: 사례별 checkpoint·resume 실행
- `evaluate_persona_co_research.py`: 분기 평가
- `evaluate_jmir_persona_eval_batch.py`: 사례별 평가와 전체 집계

## 파일럿

- `pilot_qwen_lexi_persona_history.py`: 전체 persona pool → Qwen 계획 → Lexi 4단계 이력
- `pilot_direct_candidate_matrix.py`: 직접형 질문 탐색
- `pilot_analyst_response_accept_tree.py`: analyst-response 탐색

파일명이 `pilot_`인 코드는 본 625개 실행 경로가 아니다. 파일럿 결과는
`data/pilots/<pilot-name>/`에 둔다.

## 테스트

```bash
python3 -m unittest discover -s experiments -p 'test_*.py'
```
