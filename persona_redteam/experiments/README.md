# Experiments

이 폴더에는 활성 625개 파이프라인의 구현체와 테스트만 둔다. 사용자 진입점은 가능한 한
`python -m pipeline.<command>`를 사용한다.

## 구현체

- `build_jmir_eval_set_full.py`: 625 goals와 route의 full blueprint 생성
- `prepare_jmir_persona_eval.py`: blueprint 검증·병합과 case adapter
- `qwen_target_persona_research_dialogue.py`: Qwen–target 누적 연구와 4개 독립 분기
- `run_jmir_persona_eval_batch.py`: 사례별 checkpoint, retry, resume 실행
- `evaluate_cares_official.py`: candidate-only CARES 판정
- `evaluate_persona_co_research.py`: Recovery/Behavior 평가
- `evaluate_jmir_persona_eval_batch.py`: 사례 평가와 전체·범주별 집계

## 테스트

```bash
python3 -m unittest discover -s experiments -p 'test_*.py'
```
