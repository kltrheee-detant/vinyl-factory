import importlib
import pandas as pd
import pandas.testing as pdt

import db_functions as app


def setup_tmp_db(tmp_path):
    app.DB_PATH = str(tmp_path / "test_inventory.db")
    app.init_db()


def test_roll_inventory_roundtrip(tmp_path):
    setup_tmp_db(tmp_path)

    df = pd.DataFrame([{
        '제품ID': 'V-TEST',
        '두께(mm)': 0.50,
        '폭(cm)': 100.0,
        '롤 길이(m)': 200.0,
        '현재고(롤)': 5,
        '최근업데이트': '2026-01-05 00:00'
    }])

    app.save_roll_inventory(df)
    loaded = app.load_roll_inventory()

    assert len(loaded) == 1
    assert loaded.loc[0, '제품ID'] == 'V-TEST'
    assert float(loaded.loc[0, '두께(mm)']) == 0.5
    assert int(loaded.loc[0, '현재고(롤)']) == 5


def test_cut_inventory_roundtrip(tmp_path):
    setup_tmp_db(tmp_path)

    df = pd.DataFrame([{
        '재단ID': 'C-TEST',
        '업체명': 'ACME',
        '가로(cm)': 50.0,
        '세로(cm)': 70.0,
        '두께(mm)': 0.10,
        '현재고(장)': 10,
        '최근업데이트': '2026-01-05 00:00'
    }])

    app.save_cut_inventory(df)
    loaded = app.load_cut_inventory()

    assert len(loaded) == 1
    assert loaded.loc[0, '재단ID'] == 'C-TEST'
    assert loaded.loc[0, '업체명'] == 'ACME'
    assert int(loaded.loc[0, '현재고(장)']) == 10


def test_workflow_roundtrip(tmp_path):
    setup_tmp_db(tmp_path)

    df = pd.DataFrame([{
        '작업ID': 'W-TEST',
        '업체명': 'CLIENT',
        '제품규격': 'spec',
        '수량': 3,
        '단위': '장',
        '담당자': 'kim',
        '상태': '접수',
        '우선순위': '보통',
        '납기일': '2026-01-10',
        '메모': 'note',
        '등록일': '2026-01-05 00:00'
    }])

    app.save_workflow(df)
    loaded = app.load_workflow()

    assert len(loaded) == 1
    assert loaded.loc[0, '작업ID'] == 'W-TEST'
    assert loaded.loc[0, '업체명'] == 'CLIENT'
    assert int(loaded.loc[0, '수량']) == 3
