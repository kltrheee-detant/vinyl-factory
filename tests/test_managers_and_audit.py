import pytest
import pandas as pd

import inventory_app as app


def setup_tmp_db(tmp_path):
    app.DB_PATH = str(tmp_path / "test_inventory.db")
    app.init_db()


def test_add_and_delete_manager(tmp_path):
    setup_tmp_db(tmp_path)

    assert app.load_managers() == []
    app.add_manager('kim')
    app.add_manager('lee')
    mgrs = app.load_managers()
    assert 'kim' in mgrs and 'lee' in mgrs

    app.delete_manager('kim')
    mgrs2 = app.load_managers()
    assert 'kim' not in mgrs2


def test_audit_on_workflow_update_and_delete(tmp_path):
    setup_tmp_db(tmp_path)

    df = pd.DataFrame([{ '작업ID': 'W-AUD', '업체명': 'Client', '제품규격': 's', '수량': 1, '단위': '장', '담당자': 'kim', '상태': '접수', '우선순위': '보통', '납기일': '2026-01-10', '메모': '', '등록일': '2026-01-05 00:00' }])
    app.save_workflow(df)

    app.update_workflow_item('W-AUD', 업체명='Client2', 수량=5)
    logs = app.load_audit_logs('workflow', 'W-AUD')
    assert any(log[3] == 'update' for log in logs)

    app.delete_workflow_item('W-AUD')
    logs2 = app.load_audit_logs('workflow', 'W-AUD')
    assert any(log[3] == 'delete' for log in logs2)
