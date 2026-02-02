import pandas as pd
import pytest

import db_functions as app


def setup_tmp_db(tmp_path):
    app.DB_PATH = str(tmp_path / "test_inventory.db")
    app.init_db()


def test_update_roll_item(tmp_path):
    setup_tmp_db(tmp_path)

    df = pd.DataFrame([{ '제품ID': 'V-E', '두께(mm)': 0.2, '폭(cm)': 50.0, '롤 길이(m)': 100.0, '현재고(롤)': 10, '최근업데이트': '2026-01-05 00:00' }])
    app.save_roll_inventory(df)

    app.update_roll_item('V-E', 두께_mm=0.3, 폭_cm=60.0, 롤길이_m=120.0, 현재고_롤=8)
    loaded = app.load_roll_inventory()

    assert float(loaded.loc[0, '두께(mm)']) == pytest.approx(0.3)
    assert int(loaded.loc[0, '현재고(롤)']) == 8


def test_update_roll_reject_negative(tmp_path):
    setup_tmp_db(tmp_path)

    df = pd.DataFrame([{ '제품ID': 'V-E2', '두께(mm)': 0.2, '폭(cm)': 50.0, '롤 길이(m)': 100.0, '현재고(롤)': 5, '최근업데이트': '2026-01-05 00:00' }])
    app.save_roll_inventory(df)

    with pytest.raises(ValueError):
        app.update_roll_item('V-E2', 현재고_롤=-1)


def test_update_cut_item_and_delete(tmp_path):
    setup_tmp_db(tmp_path)

    df = pd.DataFrame([{ '재단ID': 'C-E', '업체명': 'AC', '가로(cm)': 30.0, '세로(cm)': 40.0, '두께(mm)': 0.1, '현재고(장)': 20, '최근업데이트': '2026-01-05 00:00' }])
    app.save_cut_inventory(df)

    app.update_cut_item('C-E', 업체명='ACME', 가로_cm=50.0, 현재고_장=15)
    loaded = app.load_cut_inventory()

    assert loaded.loc[0, '업체명'] == 'ACME'
    assert int(loaded.loc[0, '현재고(장)']) == 15

    app.delete_cut_item('C-E')
    loaded2 = app.load_cut_inventory()
    assert loaded2.empty


def test_update_workflow_item(tmp_path):
    setup_tmp_db(tmp_path)

    df = pd.DataFrame([{ '작업ID': 'W-E', '업체명': 'Client', '제품규격': 's', '수량': 1, '단위': '장', '담당자': 'kim', '상태': '접수', '우선순위': '보통', '납기일': '2026-01-10', '메모': '', '등록일': '2026-01-05 00:00' }])
    app.save_workflow(df)

    app.update_workflow_item('W-E', 업체명='NewClient', 수량=3)
    loaded = app.load_workflow()

    assert loaded.loc[0, '업체명'] == 'NewClient'
    assert int(loaded.loc[0, '수량']) == 3


def test_delete_workflow_item(tmp_path):
    setup_tmp_db(tmp_path)

    df = pd.DataFrame([{ '작업ID': 'W-DEL', '업체명': 'ToDelete', '제품규격': 's', '수량': 1, '단위': '장', '담당자': 'lee', '상태': '접수', '우선순위': '보통', '납기일': '2026-01-10', '메모': '', '등록일': '2026-01-05 00:00' }])
    app.save_workflow(df)

    app.delete_workflow_item('W-DEL')
    loaded = app.load_workflow()
    assert loaded.empty
