# Matching

goal pathology와 persona profile을 연결하는 과거 및 보조 matcher다. 새 history 실행의 기본
검색기는 `pipeline/persona_pool.py`이며 전체 31,733개 pool에서 런타임 검색한다.

- `match_pathology.py`: 구조화 pathology matcher
- `select_by_surrogate.py`: surrogate 기반 선택
- `embeddings.py`: 임베딩 보조 기능
