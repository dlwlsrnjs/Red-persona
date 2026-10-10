# Experiment registry

이 폴더는 실행 결과가 아니라 **왜 이 실험을 했고 어떤 설정으로 재현하는지**를 고정한다.
실제 공용 runner는 `external_baselines/`와 `persona_redteam/`에 두고, 여기에는 논문 단위의
설명과 실행 당시 핵심 config/launcher 스냅샷을 보존한다.

## 등록된 실험

- [`gpt6_luna_llama_pilot/`](gpt6_luna_llama_pilot/): 9개 jailbreak 기법을 GPT-6 Luna와
  Meta-Llama-3.1-8B-Instruct target에 적용하는 10-case 파일럿
- 기존 Official-500 생성·평가 명세:
  [`../external_baselines/EVALUATION_PROTOCOL_KO.md`](../external_baselines/EVALUATION_PROTOCOL_KO.md)
- RED-Persona 전체 방법·결과 명세:
  [`../persona_redteam/docs/PAPER_METHODS_RESULTS_KO.md`](../persona_redteam/docs/PAPER_METHODS_RESULTS_KO.md)

스냅샷은 재현 기록이며, 기능 수정은 원본 runner에 먼저 반영한다.

