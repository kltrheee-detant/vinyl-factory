import sqlite3
import pandas as pd
import pytest

import db_functions as app


def setup_tmp_db(tmp_path):
    app.DB_PATH = str(tmp_path / "test_inventory.db")
    app.init_db()


def test_duplicate_workflow_raises(tmp_path):
    setup_tmp_db(tmp_path)

    # 두 개의 동일한 작업ID를 가진 행을 저장하면 UNIQUE 제약에 의해 에러가 발생해야 한다
    df = pd.DataFrame([
        {
            '작업ID': 'W-DUP',
            '업체명': 'A',
            '제품규격': 's1',
            '수량': 1,
            '단위': '장',
            '담당자': 'a',
            '상태': '접수',
            '우선순위': '보통',
            '납기일': '2026-01-10',
            '메모': '',
            '등록일': '2026-01-05 00:00'
        },
        {
            '작업ID': 'W-DUP',
            '업체명': 'B',
            '제품규격': 's2',
            '수량': 2,
            '단위': '장',
            '담당자': 'b',
            '상태': '접수',
            '우선순위': '보통',
            '납기일': '2026-01-11',
            '메모': '',
            '등록일': '2026-01-05 00:00'
        }
    ])

    try:
        # save_workflow 내부에서 UNIQUE 제약이 걸려있으므로 sqlite3.IntegrityError 예상
        app.save_workflow(df)
    except sqlite3.IntegrityError:
        assert True
    else:
        # 예외가 발생하지 않는다면 테스트 실패
        assert False, "Expected sqlite3.IntegrityError for duplicate 작업ID"


def test_negative_roll_stock_rejected(tmp_path):
    setup_tmp_db(tmp_path)

    df = pd.DataFrame([{
        '제품ID': 'V-NEG',
        '두께(mm)': 0.10,
        '폭(cm)': 50.0,
        '롤 길이(m)': 100.0,
        '현재고(롤)': -5,
        '최근업데이트': '2026-01-05 00:00'
    }])

    with pytest.raises(ValueError):
        app.save_roll_inventory(df)
