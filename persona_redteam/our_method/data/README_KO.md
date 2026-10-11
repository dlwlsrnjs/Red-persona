# FINAL197 외부 실행용 페르소나 데이터

외부 코드에서 GOAL 원문을 타깃 입력에 넣지 않고 사용할 수 있도록 만든 공개용 사본입니다.

## 권장 파일

`FINAL197_PERSONAS_WITH_HISTORY_NO_VERBATIM_GOAL.json`

- JSON 배열이며 총 197개입니다.
- 원본과 `case_id` 및 순서가 같습니다.
- `persona`와 `persona_history`는 유지합니다.
- `original_request`, 유해 요청 원문, 평가 프롬프트, Qwen private plan 및 생성 감사 정보는 포함하지 않습니다.
- `request_sha256`는 원문이 아니라 대응 관계 확인용 단방향 해시입니다.

주의: `NO_VERBATIM_GOAL`은 **GOAL 원문 및 private GOAL 필드가 없다**는 뜻입니다. 페르소나와 대화 이력은 샘플에 맞춰 생성됐으므로 GOAL과 관련된 간접·의미적 단서는 남아 있습니다. 의미적으로도 무관한 무작위 페르소나 대조군은 아닙니다.

검증 수치와 SHA-256은 `FINAL197_PERSONAS_WITH_HISTORY_NO_VERBATIM_GOAL_MANIFEST.json`에서 확인할 수 있습니다.

재생성 명령:

```bash
python3 experiments/final197/export_no_verbatim_goal_personas.py
```
