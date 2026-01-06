import pandas as pd

import inventory_app as app


def setup_tmp_db(tmp_path):
    app.DB_PATH = str(tmp_path / "test_inventory.db")
    app.init_db()


def test_audit_on_roll_update_and_delete(tmp_path):
    setup_tmp_db(tmp_path)

    df = pd.DataFrame([{ '제품ID': 'V-AUD', '두께(mm)': 0.5, '폭(cm)': 80.0, '롤 길이(m)': 100.0, '현재고(롤)': 10, '최근업데이트': '2026-01-05 00:00' }])
    app.save_roll_inventory(df)

    app.update_roll_item('V-AUD', 현재고_롤=7)
    audits = app.get_audit_logs('roll', 'V-AUD')
    assert len(audits) >= 1
    assert audits[-1]['action'] == 'update'
    assert audits[-1]['before']['현재고(롤)'] == 10
    assert audits[-1]['after']['현재고(롤)'] == 7

    app.delete_roll_item('V-AUD')
    audits2 = app.get_audit_logs('roll', 'V-AUD')
    # 마지막 액션이 delete 이어야 함
    assert audits2[-1]['action'] == 'delete'
    assert audits2[-1]['after'] is None
