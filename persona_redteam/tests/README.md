# Tests

루트 공통 테스트 fixture를 보관한다. 활성 파이프라인 단위 테스트는 현재
`experiments/test_*.py`에 있으며 다음 명령으로 함께 실행한다.

```bash
python3 -m unittest discover -s experiments -p 'test_*.py'
```
