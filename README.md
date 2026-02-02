# 유한화학 재고 시스템 (vinyl-factory)

간단한 Streamlit 기반 재고 관리 앱입니다.

주요 기능
- 롤/재단 재고 관리
- 작업(워크플로우) 관리
- 입/출고 기록(거래) 저장 및 월별 사용량 집계
- 재주문(임계값) 알림

빠른 시작
```bash
# 가상환경 생성 및 활성화 (권장)
python -m venv .venv
source .venv/bin/activate

# 의존성 설치
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 앱 실행
python -m streamlit run inventory_app.py --server.address 0.0.0.0 --server.port 8502

# 테스트 실행
python -m pytest -q
```

테스트
- `pytest`로 유닛 테스트가 포함되어 있습니다.

CI
- GitHub Actions 워크플로(`.github/workflows/pytest.yml`)가 커밋 시 자동으로 `pytest`를 실행합니다.

주의사항
- `inventory.db`는 로컬 DB 파일입니다. 배포 시에는 안전한 DB/스토리지로 이전하세요.

라이선스
- 필요시 추가해주세요.
