import streamlit as st
import streamlit.components.v1 as components  # 모바일 화면 감지용(간단 JS 삽입)
import base64
import pandas as pd
import sqlite3
import os
from datetime import datetime, date
import shutil
import json

# 데이터베이스 파일 경로
DB_PATH = os.path.join(os.path.dirname(__file__), 'inventory.db')
# 새로 추가: 현재 애플리케이션이 기대하는 DB 스키마 버전
APP_DB_VERSION = "1.2"

# ========== 데이터베이스 함수 ==========
def init_db():
    """데이터베이스 초기화 - 테이블 생성 (기존 데이터는 건드리지 않음)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 롤 재고 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS roll_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            제품ID TEXT UNIQUE,
            두께_mm REAL,
            폭_cm REAL,
            롤길이_m REAL,
            현재고_롤 INTEGER,
            최근업데이트 TEXT
        )
    ''')
    
    # 재단 재고 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cut_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            재단ID TEXT UNIQUE,
            업체명 TEXT,
            가로_cm REAL,
            세로_cm REAL,
            두께_mm REAL,
            현재고_장 INTEGER,
            최근업데이트 TEXT
        )
    ''')
    
    # 작업 플로우 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS workflow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            작업ID TEXT UNIQUE,
            업체명 TEXT,
            제품규격 TEXT,
            수량 INTEGER,
            단위 TEXT,
            담당자 TEXT,
            상태 TEXT,
            우선순위 TEXT,
            납기일 TEXT,
            메모 TEXT,
            등록일 TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

    # 추가 테이블: 거래 기록(transactions)과 재주문 임계값(reorder_levels)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_type TEXT,
            item_id TEXT,
            delta REAL,
            note TEXT,
            timestamp TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reorder_levels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_type TEXT,
            item_id TEXT UNIQUE,
            threshold REAL
        )
    ''')

    # 작업자(담당자) 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS managers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    ''')

    # 감사 로그 테이블 (일관된 컬럼명으로 하나만 생성)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_type TEXT,
            item_id TEXT,
            action TEXT,
            before_json TEXT,
            after_json TEXT,
            actor TEXT,
            timestamp TEXT
        )
    ''')

    # DB 메타 (스키마 버전 관리)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS db_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    conn.commit()
    conn.close()

# ========== DB 버전/마이그레이션 헬퍼 ==========
def get_db_version():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT value FROM db_meta WHERE key = 'schema_version'")
        row = cursor.fetchone()
        conn.close()
        return row[0] if row is not None else None
    except sqlite3.OperationalError:
        conn.close()
        return None

def set_db_version(v):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO db_meta (key, value) VALUES ('schema_version', ?)", (str(v),))
    conn.commit()
    conn.close()

def backup_db():
    """현재 DB 파일을 타임스탬프가 붙은 백업으로 복사합니다."""
    if os.path.exists(DB_PATH):
        bak_path = f"{DB_PATH}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
        shutil.copy2(DB_PATH, bak_path)
        return bak_path
    return None

def column_exists(conn, table, column):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    return column in cols

# 각 마이그레이션은 idempotent 하게 작성 (존재하면 무시)
def migration_to_1_1(conn):
    # 예시: 향후 컬럼 추가 등의 non-destructive 변경을 여기에 둡니다.
    pass

def migration_to_1_2(conn):
    # audit_logs에 before_json/after_json 컬럼이 없는 경우 추가하고,
    # 구버전 컬럼(before/after)이 있으면 복사합니다(삭제하지 않음).
    cur = conn.cursor()
    if not column_exists(conn, 'audit_logs', 'before_json'):
        cur.execute("ALTER TABLE audit_logs ADD COLUMN before_json TEXT")
    if not column_exists(conn, 'audit_logs', 'after_json'):
        cur.execute("ALTER TABLE audit_logs ADD COLUMN after_json TEXT")
    # 구 컬럼이 존재한다면 데이터를 복사 (before -> before_json 등)
    cur.execute("PRAGMA table_info(audit_logs)")
    cols = [r[1] for r in cur.fetchall()]
    if 'before' in cols and 'before_json' in cols:
        cur.execute("UPDATE audit_logs SET before_json = before WHERE before_json IS NULL")
    if 'after' in cols and 'after_json' in cols:
        cur.execute("UPDATE audit_logs SET after_json = after WHERE after_json IS NULL")
    conn.commit()

MIGRATIONS = [
    ("1.1", migration_to_1_1),
    ("1.2", migration_to_1_2),
]

def check_and_migrate_db(auto_run=True):
    """현재 DB 버전을 확인하고 필요 시 백업 후 마이그레이션 적용."""
    cur_ver = get_db_version()
    if cur_ver is None:
        # 초기 DB의 경우 기본 버전을 1.0으로 설정
        set_db_version("1.0")
        cur_ver = "1.0"

    if cur_ver == APP_DB_VERSION:
        return

    # 간단한 버전 비교 (문자열 기준, 단순 순서 가정)
    # 필요한 마이그레이션만 적용
    to_apply = [m for m in MIGRATIONS if cur_ver < m[0] <= APP_DB_VERSION]
    if not to_apply:
        set_db_version(APP_DB_VERSION)
        return

    if auto_run:
        bak = backup_db()
        try:
            conn = sqlite3.connect(DB_PATH)
            for ver, func in to_apply:
                func(conn)
            set_db_version(APP_DB_VERSION)
            conn.close()
            # 스트림릿 환경에서 사용자에게 알림
            try:
                st.info(f"DB 마이그레이션 완료 (backup: {bak})")
            except Exception:
                pass
        except Exception as e:
            # 문제 발생시 정보 제공
            try:
                st.error(f"DB 마이그레이션 실패: {e} (backup: {bak})")
            except Exception:
                pass
            raise

def load_roll_inventory():
    """롤 재고 데이터 로드"""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM roll_inventory", conn)
    conn.close()
    
    if df.empty:
        return pd.DataFrame(columns=['제품ID', '두께(mm)', '폭(cm)', '롤 길이(m)', '현재고(롤)', '최근업데이트'])
    
    # 컬럼명 변환
    df = df.rename(columns={
        '두께_mm': '두께(mm)',
        '폭_cm': '폭(cm)',
        '롤길이_m': '롤 길이(m)',
        '현재고_롤': '현재고(롤)'
    })
    return df[['제품ID', '두께(mm)', '폭(cm)', '롤 길이(m)', '현재고(롤)', '최근업데이트']]


def record_roll_transaction(item_id, delta, note=""):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO transactions (item_type, item_id, delta, note, timestamp) VALUES (?, ?, ?, ?, ?)",
        ('roll', item_id, delta, note, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()


def get_monthly_usage_roll(item_id, year=None, month=None):
    """주어진 연/월의 사용량(출고)을 합산해서 반환. 기본은 현재 달."""
    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month

    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT SUM(-delta) FROM transactions WHERE item_type = ? AND item_id = ? AND delta < 0 AND timestamp >= ? AND timestamp < ?",
        ('roll', item_id, start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S"))
    )
    res = cursor.fetchone()[0]
    conn.close()
    return float(res) if res is not None else 0.0


def record_cut_transaction(item_id, delta, note=""):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO transactions (item_type, item_id, delta, note, timestamp) VALUES (?, ?, ?, ?, ?)",
        ('cut', item_id, delta, note, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()


# ========== 감사 로그 기록 ==========
# (기존의 중복된 함수 정의 중복 제거: 아래 하나만 사용)
def record_audit(item_type, item_id, action, before=None, after=None, actor=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    before_json = json.dumps(before, default=str) if before is not None else None
    after_json = json.dumps(after, default=str) if after is not None else None
    cursor.execute(
        "INSERT INTO audit_logs (item_type, item_id, action, before_json, after_json, actor, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (item_type, item_id, action, before_json, after_json, actor, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()


def get_audit_logs(item_type, item_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT action, before_json, after_json, actor, timestamp FROM audit_logs WHERE item_type = ? AND item_id = ? ORDER BY id', (item_type, item_id))
    rows = cursor.fetchall()
    conn.close()
    result = []
    for action, before_json, after_json, actor, timestamp in rows:
        before = json.loads(before_json) if before_json else None
        after = json.loads(after_json) if after_json else None
        result.append({'action': action, 'before': before, 'after': after, 'actor': actor, 'timestamp': timestamp})
    return result


def get_monthly_usage_cut(item_id, year=None, month=None):
    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month

    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT SUM(-delta) FROM transactions WHERE item_type = ? AND item_id = ? AND delta < 0 AND timestamp >= ? AND timestamp < ?",
        ('cut', item_id, start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S"))
    )
    res = cursor.fetchone()[0]
    conn.close()
    return float(res) if res is not None else 0.0


def set_reorder_level(item_type, item_id, threshold):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO reorder_levels (item_type, item_id, threshold)
        VALUES (?, ?, ?)
    ''', (item_type, item_id, threshold))
    conn.commit()
    conn.close()


def get_reorder_level(item_type, item_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT threshold FROM reorder_levels WHERE item_type = ? AND item_id = ?', (item_type, item_id))
    row = cursor.fetchone()
    conn.close()
    return float(row[0]) if row is not None else None


def load_managers():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query('SELECT * FROM managers', conn)
    conn.close()
    if df.empty:
        return []
    return df['name'].tolist()


def add_manager(name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO managers (name) VALUES (?)', (name,))
    conn.commit()
    conn.close()


def delete_manager(name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM managers WHERE name = ?', (name,))
    conn.commit()
    conn.close()


def delete_workflow_item(work_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 작업ID, 업체명, 제품규격, 수량, 단위, 담당자, 상태, 우선순위, 납기일, 메모, 등록일 FROM workflow WHERE 작업ID = ?", (work_id,))
    row = cur.fetchone()
    if row is None:
        conn.close()
        raise ValueError("존재하지 않는 작업ID입니다.")
    before = dict(zip(['작업ID','업체명','제품규격','수량','단위','담당자','상태','우선순위','납기일','메모','등록일'], row))
    cur.execute("DELETE FROM workflow WHERE 작업ID = ?", (work_id,))
    conn.commit()
    conn.close()
    record_audit('workflow', work_id, 'delete', before=before, after=None)

def load_cut_inventory():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM cut_inventory", conn)
    conn.close()
    if df.empty:
        return pd.DataFrame(columns=['재단ID', '업체명', '가로(cm)', '세로(cm)', '두께(mm)', '현재고(장)', '최근업데이트'])
    df = df.rename(columns={
        '가로_cm': '가로(cm)',
        '세로_cm': '세로(cm)',
        '두께_mm': '두께(mm)',
        '현재고_장': '현재고(장)'
    })
    return df[['재단ID', '업체명', '가로(cm)', '세로(cm)', '두께(mm)', '현재고(장)', '최근업데이트']]


def save_roll_inventory(df):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for _, row in df.iterrows():
        stock = int(row['현재고(롤)'])
        if stock < 0:
            conn.close()
            raise ValueError("재고 수량은 음수가 될 수 없습니다.")
        cur.execute('''
            INSERT OR REPLACE INTO roll_inventory (제품ID, 두께_mm, 폭_cm, 롤길이_m, 현재고_롤, 최근업데이트)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (row['제품ID'], float(row['두께(mm)']), float(row['폭(cm)']), float(row['롤 길이(m)']), stock, row.get('최근업데이트')))
    conn.commit()
    conn.close()


def save_cut_inventory(df):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for _, row in df.iterrows():
        cur.execute('''
            INSERT OR REPLACE INTO cut_inventory (재단ID, 업체명, 가로_cm, 세로_cm, 두께_mm, 현재고_장, 최근업데이트)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (row['재단ID'], row['업체명'], float(row['가로(cm)']), float(row['세로(cm)']), float(row['두께(mm)']), int(row['현재고(장)']), row.get('최근업데이트')))
    conn.commit()
    conn.close()


def load_workflow():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM workflow", conn)
    conn.close()
    if df.empty:
        return pd.DataFrame(columns=['작업ID','업체명','제품규격','수량','단위','담당자','상태','우선순위','납기일','메모','등록일'])
    return df[['작업ID','업체명','제품규격','수량','단위','담당자','상태','우선순위','납기일','메모','등록일']]


def save_workflow(df):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for _, row in df.iterrows():
        # 중복 체크
        cur.execute("SELECT COUNT(*) FROM workflow WHERE 작업ID = ?", (row['작업ID'],))
        if cur.fetchone()[0] > 0:
            conn.close()
            raise sqlite3.IntegrityError("UNIQUE constraint failed: workflow.작업ID")
        cur.execute('''
            INSERT INTO workflow (작업ID, 업체명, 제품규격, 수량, 단위, 담당자, 상태, 우선순위, 납기일, 메모, 등록일)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            row['작업ID'], row['업체명'], row['제품규격'], int(row['수량']), row['단위'], row['담당자'],
            row['상태'], row['우선순위'], row['납기일'], row['메모'], row.get('등록일')
        ))
    conn.commit()
    conn.close()


def update_roll_item(item_id, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 제품ID, 두께_mm, 폭_cm, 롤길이_m, 현재고_롤, 최근업데이트 FROM roll_inventory WHERE 제품ID = ?", (item_id,))
    row = cur.fetchone()
    if row is None:
        conn.close()
        raise ValueError("존재하지 않는 제품ID입니다.")
    before = dict(zip(['제품ID','두께(mm)','폭(cm)','롤 길이(m)','현재고(롤)','최근업데이트'], [row[0], row[1], row[2], row[3], row[4], row[5]]))
    fields = {}
    if '두께_mm' in kwargs or '두께(mm)' in kwargs:
        fields['두께_mm'] = float(kwargs.get('두께_mm', kwargs.get('두께(mm)')))
    if '폭_cm' in kwargs or '폭(cm)' in kwargs:
        fields['폭_cm'] = float(kwargs.get('폭_cm', kwargs.get('폭(cm)')))
    if '롤길이_m' in kwargs or '롤 길이(m)' in kwargs:
        fields['롤길이_m'] = float(kwargs.get('롤길이_m', kwargs.get('롤 길이(m)')))
    if '현재고_롤' in kwargs or '현재고(롤)' in kwargs:
        new_stock = int(kwargs.get('현재고_롤', kwargs.get('현재고(롤)')))
        if new_stock < 0:
            conn.close()
            raise ValueError("재고 수량은 음수가 될 수 없습니다.")
        fields['현재고_롤'] = new_stock
    if '최근업데이트' in kwargs:
        fields['최근업데이트'] = kwargs['최근업데이트']
    if fields:
        set_clause = ", ".join(f"{k}=?" for k in fields.keys())
        params = list(fields.values()) + [item_id]
        cur.execute(f"UPDATE roll_inventory SET {set_clause} WHERE 제품ID = ?", params)
    conn.commit()
    cur.execute("SELECT 제품ID, 두께_mm, 폭_cm, 롤길이_m, 현재고_롤, 최근업데이트 FROM roll_inventory WHERE 제품ID = ?", (item_id,))
    row2 = cur.fetchone()
    after = dict(zip(['제품ID','두께(mm)','폭(cm)','롤 길이(m)','현재고(롤)','최근업데이트'], [row2[0], row2[1], row2[2], row2[3], row2[4], row2[5]]))
    conn.close()
    record_audit('roll', item_id, 'update', before=before, after=after)


def delete_roll_item(item_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 제품ID, 두께_mm, 폭_cm, 롤길이_m, 현재고_롤, 최근업데이트 FROM roll_inventory WHERE 제품ID = ?", (item_id,))
    row = cur.fetchone()
    if row is None:
        conn.close()
        raise ValueError("존재하지 않는 제품ID입니다.")
    before = dict(zip(['제품ID','두께(mm)','폭(cm)','롤 길이(m)','현재고(롤)','최근업데이트'], [row[0], row[1], row[2], row[3], row[4], row[5]]))
    cur.execute("DELETE FROM roll_inventory WHERE 제품ID = ?", (item_id,))
    conn.commit()
    conn.close()
    record_audit('roll', item_id, 'delete', before=before, after=None)


def update_cut_item(item_id, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 재단ID, 업체명, 가로_cm, 세로_cm, 두께_mm, 현재고_장, 최근업데이트 FROM cut_inventory WHERE 재단ID = ?", (item_id,))
    row = cur.fetchone()
    if row is None:
        conn.close()
        raise ValueError("존재하지 않는 재단ID입니다.")
    before = dict(zip(['재단ID','업체명','가로(cm)','세로(cm)','두께(mm)','현재고(장)','최근업데이트'], [row[0],row[1],row[2],row[3],row[4],row[5],row[6]]))
    fields = {}
    if '업체명' in kwargs:
        fields['업체명'] = kwargs['업체명']
    if '가로_cm' in kwargs or '가로(cm)' in kwargs:
        fields['가로_cm'] = float(kwargs.get('가로_cm', kwargs.get('가로(cm)')))
    if '세로_cm' in kwargs or '세로(cm)' in kwargs:
        fields['세로_cm'] = float(kwargs.get('세로_cm', kwargs.get('세로(cm)')))
    if '두께_mm' in kwargs or '두께(mm)' in kwargs:
        fields['두께_mm'] = float(kwargs.get('두께_mm', kwargs.get('두께(mm)')))
    if '현재고_장' in kwargs or '현재고(장)' in kwargs:
        fields['현재고_장'] = int(kwargs.get('현재고_장', kwargs.get('현재고(장)')))
    if '최근업데이트' in kwargs:
        fields['최근업데이트'] = kwargs['최근업데이트']
    if fields:
        set_clause = ", ".join(f"{k}=?" for k in fields.keys())
        params = list(fields.values()) + [item_id]
        cur.execute(f"UPDATE cut_inventory SET {set_clause} WHERE 재단ID = ?", params)
    conn.commit()
    cur.execute("SELECT 재단ID, 업체명, 가로_cm, 세로_cm, 두께_mm, 현재고_장, 최근업데이트 FROM cut_inventory WHERE 재단ID = ?", (item_id,))
    row2 = cur.fetchone()
    after = dict(zip(['재단ID','업체명','가로(cm)','세로(cm)','두께(mm)','현재고(장)','최근업데이트'], [row2[0],row2[1],row2[2],row2[3],row2[4],row2[5],row2[6]]))
    conn.close()
    record_audit('cut', item_id, 'update', before=before, after=after)


def delete_cut_item(item_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 재단ID, 업체명, 가로_cm, 세로_cm, 두께_mm, 현재고_장, 최근업데이트 FROM cut_inventory WHERE 재단ID = ?", (item_id,))
    row = cur.fetchone()
    if row is None:
        conn.close()
        raise ValueError("존재하지 않는 재단ID입니다.")
    before = dict(zip(['재단ID','업체명','가로(cm)','세로(cm)','두께(mm)','현재고(장)','최근업데이트'], [row[0],row[1],row[2],row[3],row[4],row[5],row[6]]))
    cur.execute("DELETE FROM cut_inventory WHERE 재단ID = ?", (item_id,))
    conn.commit()
    conn.close()
    record_audit('cut', item_id, 'delete', before=before, after=None)


def update_workflow_item(work_id, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 작업ID, 업체명, 제품규격, 수량, 단위, 담당자, 상태, 우선순위, 납기일, 메모, 등록일 FROM workflow WHERE 작업ID = ?", (work_id,))
    row = cur.fetchone()
    if row is None:
        conn.close()
        raise ValueError("존재하지 않는 작업ID입니다.")
    before = dict(zip(['작업ID','업체명','제품규격','수량','단위','담당자','상태','우선순위','납기일','메모','등록일'], row))
    fields = {}
    allowed = ['업체명','제품규격','수량','단위','담당자','상태','우선순위','납기일','메모','등록일']
    for k in allowed:
        if k in kwargs:
            fields[k] = kwargs[k]
    if fields:
        set_clause = ", ".join(f"{k}=?" for k in fields.keys())
        params = list(fields.values()) + [work_id]
        cur.execute(f"UPDATE workflow SET {set_clause} WHERE 작업ID = ?", params)
    conn.commit()
    cur.execute("SELECT 작업ID, 업체명, 제품규격, 수량, 단위, 담당자, 상태, 우선순위, 납기일, 메모, 등록일 FROM workflow WHERE 작업ID = ?", (work_id,))
    row2 = cur.fetchone()
    after = dict(zip(['작업ID','업체명','제품규격','수량','단위','담당자','상태','우선순위','납기일','메모','등록일'], row2))
    conn.close()
    record_audit('workflow', work_id, 'update', before=before, after=after)

# 데이터베이스 초기화
init_db()
# 새로 추가: 시작 시 DB 버전 체크 및 필요한 경우 백업 + 마이그레이션 수행
check_and_migrate_db()

# 페이지 기본 설정 (페이지 아이콘 추가, 모바일 파비콘/홈아이콘은 외부 호스팅 권장)
st.set_page_config(page_title="비닐 공장 재고 현황판", layout="wide", page_icon="🏭")

# 모바일 대응 메타 및 CSS (간단한 미디어쿼리로 버튼/표/패딩 최적화)
st.markdown('<meta name="viewport" content="width=device-width, initial-scale=1">', unsafe_allow_html=True)
st.markdown("""
<style>
  /* 전역 스타일(기존 .big-font 유지) */
  .big-font { font-size: 20px !important; font-weight: bold; }
  .stDataFrame { width: 100%; }

  /* 모바일 전용 최적화 */
  @media (max-width: 600px) {
    /* 컨테이너 여백 축소 */
    .block-container { padding-left: 8px !important; padding-right: 8px !important; }
    /* 데이터프레임 폰트 축소 */
    .stDataFrame table td, .stDataFrame table th { font-size: 12px !important; }
    /* 버튼 크기 키우기(터치 편의) */
    .stButton>button, button[kind="primary"] { padding: 12px 16px !important; font-size: 16px !important; }
    /* 캡션/메모 등 축약 */
    .big-font { font-size: 16px !important; }
    /* 열 레이아웃이 좁을 때 세로로 쌓이도록 강제 (Streamlit 내부 클래스는 변경될 수 있음) */
    .css-1lcbmhc, .css-1d391kg { flex-direction: column !important; }
  }
</style>
""", unsafe_allow_html=True)

# 간단한 JS로 화면 너비가 작은 경우 body에 클래스 추가 (확인/추가 로직에 활용 가능)
components.html("""
<script>
  if (window && window.innerWidth && window.innerWidth < 600) {
    document.body.classList.add('is-mobile');
  }
</script>
""", height=0)

# 제목
st.title("🏭 유한화학 재고 현황판")
st.caption(f"💾 데이터베이스 연동됨: {DB_PATH}")
st.markdown("---")

# 데이터 로드 (새로고침 버튼 추가)
col_refresh, col_empty = st.columns([1, 5])
with col_refresh:
    if st.button("🔄 새로고침"):
        st.rerun()

# 데이터 로드 함수 (캐싱 없이 항상 최신 데이터)
def get_roll_inventory():
    return load_roll_inventory()

def get_cut_inventory():
    return load_cut_inventory()

def get_workflow():
    return load_workflow()

# 상태 순서 정의
STATUS_ORDER = ['접수', '생산중', '재단중', '완료', '납품완료']
PRIORITY_OPTIONS = ['긴급', '높음', '보통', '낮음']

# 사이드바: 작업 선택
st.sidebar.header("🛠 작업 메뉴")

menu_category = st.sidebar.selectbox("카테고리 선택", ["📦 롤 재고 관리", "✂️ 재단 재고 관리", "📋 작업 플로우 (TODO)"])

if menu_category == "📦 롤 재고 관리":
    menu = st.sidebar.radio("작업을 선택하세요", [
        "롤 재고 현황 보기", 
        "롤 입/출고 입력", 
        "신규 롤 규격 등록"
    ])
elif menu_category == "✂️ 재단 재고 관리":
    menu = st.sidebar.radio("작업을 선택하세요", [
        "재단 재고 현황 보기",
        "재단 입/출고 입력",
        "신규 재단 규격 등록"
    ])
else:
    menu = st.sidebar.radio("작업을 선택하세요", [
        "작업 현황판 (칸반)",
        "신규 작업 등록",
        "작업자 관리",
        "작업 상태 변경",
        "완료된 작업 보기"
    ])

# ========== 롤 재고 관리 ==========
if menu == "롤 재고 현황 보기":
    st.subheader("📊 현재 롤 재고 목록")
    
    df = get_roll_inventory()
    # 이번 달 사용량 컬럼 추가
    df['이번달 사용량'] = df['제품ID'].apply(lambda pid: get_monthly_usage_roll(pid))
    
    if df.empty:
        st.info("등록된 롤 재고가 없습니다. '신규 롤 규격 등록'에서 추가해주세요.")
    else:
        # 정렬 컨트롤
        sort_cols = ['제품ID', '두께(mm)', '폭(cm)', '롤 길이(m)', '현재고(롤)', '이번달 사용량']
        sort_col = st.selectbox('정렬 기준', sort_cols, index=0)
        sort_order = st.radio('정렬 순서', ['오름차순', '내림차순'], horizontal=True)
        ascending = True if sort_order == '오름차순' else False
        if sort_col in df.columns:
            disp_df = df.sort_values(by=sort_col, ascending=ascending)
        else:
            disp_df = df

        st.dataframe(
            disp_df.style.format({
                "두께(mm)": "{:.3f}",
                "폭(cm)": "{:.1f}",
                "롤 길이(m)": "{:.1f}",
                "현재고(롤)": "{:.0f}"
            }),
            use_container_width=True,
            height=400
        )
        
        total_rolls = df['현재고(롤)'].sum()
        st.info(f"📋 총 보유 롤 수량: {int(total_rolls)} 롤")

        # 편집 및 삭제 UI
        with st.expander('제품 수정/삭제'):
            edit_prod = st.selectbox('편집할 제품 선택', df['제품ID'].tolist())
            idx = df[df['제품ID'] == edit_prod].index[0]

            new_thickness = st.number_input('두께 (mm)', value=float(df.loc[idx, '두께(mm)']), format="%.3f")
            new_width = st.number_input('폭 (cm)', value=float(df.loc[idx, '폭(cm)']), format="%.1f")
            new_length = st.number_input('롤 길이 (m)', value=float(df.loc[idx, '롤 길이(m)']), format="%.1f")
            new_stock = st.number_input('현재고 (롤)', min_value=0, value=int(df.loc[idx, '현재고(롤)']), step=1)

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button('저장'):
                    try:
                        update_roll_item(edit_prod, 두께_mm=new_thickness, 폭_cm=new_width, 롤길이_m=new_length, 현재고_롤=new_stock)
                        st.success(f"[{edit_prod}]가 업데이트되었습니다.")
                    except ValueError as e:
                        st.error(str(e))
            with col_b:
                confirm = st.checkbox('삭제 확인 (체크 후 삭제)', key='confirm_delete_roll')
                if st.button('삭제') and confirm:
                    delete_roll_item(edit_prod)
                    st.success(f"[{edit_prod}]가 삭제되었습니다.")
                elif st.button('삭제') and not confirm:
                    st.error('삭제하려면 확인 체크박스를 선택하세요.')

        # 재주문 임계값 알림
        alerts = []
        for _, row in df.iterrows():
            thr = get_reorder_level('roll', row['제품ID'])
            if thr is not None and float(row['현재고(롤)']) <= thr:
                alerts.append(f"재주문 필요: [{row['제품ID']}] 현재 {int(row['현재고(롤)'])} ≤ 임계값 {int(thr)}")

        if alerts:
            for a in alerts:
                st.warning(a)

        # 임계값 설정 UI (간단히 제품 선택 후 설정)
        with st.expander('재주문 임계값 설정'):
            prod = st.selectbox('제품 선택', df['제품ID'].tolist())
            current_thr = get_reorder_level('roll', prod)
            new_thr = st.number_input('임계값 (롤)', min_value=0, value=int(current_thr) if current_thr is not None else 0)
            if st.button('임계값 저장'):
                set_reorder_level('roll', prod, new_thr)
                st.success(f'[{prod}] 임계값이 {int(new_thr)}롤로 설정되었습니다.')

elif menu == "롤 입/출고 입력":
    st.subheader("📝 롤 생산 및 사용 등록")
    
    df = get_roll_inventory()
    
    if df.empty:
        st.warning("등록된 제품이 없습니다. '신규 롤 규격 등록' 메뉴에서 제품을 먼저 등록해주세요.")
    else:
        product_list = df.apply(lambda x: f"[{x['제품ID']}] {x['두께(mm)']}T x {x['폭(cm)']}cm x {x['롤 길이(m)']}m", axis=1)
        selected_product_str = st.selectbox("제품을 선택하세요", product_list)
        
        selected_id = selected_product_str.split(']')[0].replace('[', '')
        
        col1, col2 = st.columns(2)
        
        with col1:
            input_type = st.radio("구분", ["생산 (입고 +)", "사용 (출고 -)"])
        
        with col2:
            qty = st.number_input("수량 (롤 단위)", min_value=1, value=1, step=1)
        
        if st.button("재고 반영"):
            idx = df[df['제품ID'] == selected_id].index[0]
            current_qty = df.loc[idx, '현재고(롤)']
            
            if input_type == "생산 (입고 +)":
                df.loc[idx, '현재고(롤)'] = current_qty + qty
                df.loc[idx, '최근업데이트'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                # 거래 기록
                record_roll_transaction(selected_id, qty, note='입고')
                save_roll_inventory(df)
                st.success(f"{qty}롤 생산 등록 완료! (현재: {current_qty + qty}롤)")
            else:
                if current_qty < qty:
                    st.error(f"재고가 부족합니다! (현재고: {current_qty}롤)")
                else:
                    df.loc[idx, '현재고(롤)'] = current_qty - qty
                    df.loc[idx, '최근업데이트'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    # 거래 기록 (출고는 음수)
                    record_roll_transaction(selected_id, -qty, note='출고')
                    save_roll_inventory(df)
                    st.success(f"{qty}롤 사용 등록 완료! (현재: {current_qty - qty}롤)")

elif menu == "신규 롤 규격 등록":
    st.subheader("✨ 새로운 롤 규격 등록")
    
    with st.form("new_product_form"):
        col1, col2 = st.columns(2)
        with col1:
            new_id = st.text_input("제품 ID (예: V-003)", placeholder="고유 번호 입력")
            thickness = st.number_input("두께 (mm)", min_value=0.01, step=0.001, format="%.3f")
        with col2:
            width = st.number_input("폭 (cm)", min_value=1.0, step=1.0)
            length = st.number_input("롤 길이 (m)", min_value=1.0, step=10.0)
        
        initial_stock = st.number_input("초기 재고 (롤)", min_value=0, value=0)
        
        submitted = st.form_submit_button("규격 추가")
        
        if submitted:
            df = get_roll_inventory()
            if new_id in df['제품ID'].values:
                st.error("이미 존재하는 제품 ID입니다.")
            elif new_id == "":
                st.error("제품 ID를 입력해주세요.")
            else:
                new_data = pd.DataFrame([{
                    '제품ID': new_id,
                    '두께(mm)': thickness,
                    '폭(cm)': width,
                    '롤 길이(m)': length,
                    '현재고(롤)': initial_stock,
                    '최근업데이트': datetime.now().strftime("%Y-%m-%d %H:%M")
                }])
                df = pd.concat([df, new_data], ignore_index=True)
                save_roll_inventory(df)
                st.success(f"[{new_id}] 신규 롤 규격이 등록되었습니다.")

# ========== 재단 재고 관리 ==========
elif menu == "재단 재고 현황 보기":
    st.subheader("✂️ 현재 재단 재고 목록")
    
    df = get_cut_inventory()
    # 이번 달 사용량 컬럼 추가
    def get_cut_usage_wrapper(cid):
        # reuse roll function but for cuts we will implement below
        return get_monthly_usage_cut(cid)

    df['이번달 사용량'] = df['재단ID'].apply(lambda pid: get_monthly_usage_cut(pid))
    
    if df.empty:
        st.info("등록된 재단 규격이 없습니다.")
    else:
        # 정렬 컨트롤 (재단)
        sort_cols = ['재단ID', '업체명', '가로(cm)', '세로(cm)', '두께(mm)', '현재고(장)', '이번달 사용량']
        sort_col = st.selectbox('정렬 기준', sort_cols, index=0, key='cut_sort_col')
        sort_order = st.radio('정렬 순서', ['오름차순', '내림차순'], horizontal=True, key='cut_sort_order')
        ascending = True if sort_order == '오름차순' else False
        if sort_col in df.columns:
            disp_df = df.sort_values(by=sort_col, ascending=ascending)
        else:
            disp_df = df

        st.dataframe(
            disp_df.style.format({
                "가로(cm)": "{:.1f}",
                "세로(cm)": "{:.1f}",
                "두께(mm)": "{:.3f}",
                "현재고(장)": "{:.0f}"
            }),
            use_container_width=True,
            height=400
        )
        
        total_sheets = df['현재고(장)'].sum()
        st.info(f"📋 총 보유 재단 수량: {int(total_sheets)} 장")

        # 편집 및 삭제 UI (재단)
        with st.expander('재단 수정/삭제'):
            edit_prod = st.selectbox('편집할 재단 선택', df['재단ID'].tolist(), key='select_cut_edit')
            idx = df[df['재단ID'] == edit_prod].index[0]

            new_company = st.text_input('업체명', value=df.loc[idx, '업체명'])
            new_width = st.number_input('가로 (cm)', value=float(df.loc[idx, '가로(cm)']))
            new_height = st.number_input('세로 (cm)', value=float(df.loc[idx, '세로(cm)']))
            new_thickness = st.number_input('두께 (mm)', value=float(df.loc[idx, '두께(mm)']), format="%.3f")
            new_stock = st.number_input('현재고 (장)', min_value=0, value=int(df.loc[idx, '현재고(장)']), step=1)

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button('저장', key='save_cut'):
                    try:
                        update_cut_item(edit_prod, 업체명=new_company, 가로_cm=new_width, 세로_cm=new_height, 두께_mm=new_thickness, 현재고_장=new_stock)
                        st.success(f"[{edit_prod}] 재단 데이터가 업데이트되었습니다.")
                    except ValueError as e:
                        st.error(str(e))
            with col_b:
                confirm = st.checkbox('삭제 확인 (체크 후 삭제)', key='confirm_delete_cut')
                if st.button('삭제', key='delete_cut') and confirm:
                    delete_cut_item(edit_prod)
                    st.success(f"[{edit_prod}] 재단 데이터가 삭제되었습니다.")
                elif st.button('삭제', key='delete_cut') and not confirm:
                    st.error('삭제하려면 확인 체크박스를 선택하세요.')

        # 재주문 임계값 알림
        alerts = []
        for _, row in df.iterrows():
            thr = get_reorder_level('cut', row['재단ID'])
            if thr is not None and float(row['현재고(장)']) <= thr:
                alerts.append(f"재주문 필요: [{row['재단ID']}] 현재 {int(row['현재고(장)'])} ≤ 임계값 {int(thr)}")

        if alerts:
            for a in alerts:
                st.warning(a)

        with st.expander('재주문 임계값 설정 (재단)'):
            prod = st.selectbox('재단 선택', df['재단ID'].tolist())
            current_thr = get_reorder_level('cut', prod)
            new_thr = st.number_input('임계값 (장)', min_value=0, value=int(current_thr) if current_thr is not None else 0, key='cut_thr')
            if st.button('임계값 저장(재단)'):
                set_reorder_level('cut', prod, new_thr)
                st.success(f'[{prod}] 임계값이 {int(new_thr)}장으로 설정되었습니다.')

elif menu == "재단 입/출고 입력":
    st.subheader("✂️ 재단 입고 및 출고 등록")
    
    df = get_cut_inventory()
    
    if df.empty:
        st.warning("등록된 재단 규격이 없습니다. '신규 재단 규격 등록' 메뉴에서 먼저 등록해주세요.")
    else:
        product_list = df.apply(
            lambda x: f"[{x['재단ID']}] {x['업체명']} - {x['가로(cm)']}cm x {x['세로(cm)']}cm ({x['두께(mm)']}T)", 
            axis=1
        )
        selected_product_str = st.selectbox("재단 규격을 선택하세요", product_list)
        
        selected_id = selected_product_str.split(']')[0].replace('[', '')
        
        col1, col2 = st.columns(2)
        
        with col1:
            input_type = st.radio("구분", ["재단 완료 (입고 +)", "납품/사용 (출고 -)"])
        
        with col2:
            qty = st.number_input("수량 (장 단위)", min_value=1, value=1, step=1)
        
        if st.button("재단 재고 반영"):
            idx = df[df['재단ID'] == selected_id].index[0]
            current_qty = df.loc[idx, '현재고(장)']
            
            if input_type == "재단 완료 (입고 +)":
                df.loc[idx, '현재고(장)'] = current_qty + qty
                df.loc[idx, '최근업데이트'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                # 거래 기록
                record_cut_transaction(selected_id, qty, note='입고')
                save_cut_inventory(df)
                st.success(f"{qty}장 재단 입고 완료! (현재: {current_qty + qty}장)")
            else:
                if current_qty < qty:
                    st.error(f"재고가 부족합니다! (현재고: {current_qty}장)")
                else:
                    df.loc[idx, '현재고(장)'] = current_qty - qty
                    df.loc[idx, '최근업데이트'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    # 거래 기록 (출고 음수)
                    record_cut_transaction(selected_id, -qty, note='출고')
                    save_cut_inventory(df)
                    st.success(f"{qty}장 출고 완료! (현재: {current_qty - qty}장)")

elif menu == "신규 재단 규격 등록":
    st.subheader("✨ 새로운 재단 규격 등록 (업체별 맞춤 사이즈)")
    
    with st.form("new_cut_form"):
        col1, col2 = st.columns(2)
        with col1:
            new_id = st.text_input("재단 ID (예: C-003)", placeholder="고유 번호 입력")
            company = st.text_input("업체명", placeholder="업체명 입력")
            thickness = st.number_input("두께 (mm)", min_value=0.01, step=0.001, format="%.3f", key="cut_thickness")
        with col2:
            width_cm = st.number_input("가로 (cm)", min_value=1.0, step=1.0)
            height_cm = st.number_input("세로 (cm)", min_value=1.0, step=1.0)
            initial_stock = st.number_input("초기 재고 (장)", min_value=0, value=0)
        
        submitted = st.form_submit_button("재단 규격 추가")
        
        if submitted:
            df = get_cut_inventory()
            if new_id in df['재단ID'].values:
                st.error("이미 존재하는 재단 ID입니다.")
            elif new_id == "":
                st.error("재단 ID를 입력해주세요.")
            elif company == "":
                st.error("업체명을 입력해주세요.")
            else:
                new_data = pd.DataFrame([{
                    '재단ID': new_id,
                    '업체명': company,
                    '가로(cm)': width_cm,
                    '세로(cm)': height_cm,
                    '두께(mm)': thickness,
                    '현재고(장)': initial_stock,
                    '최근업데이트': datetime.now().strftime("%Y-%m-%d %H:%M")
                }])
                df = pd.concat([df, new_data], ignore_index=True)
                save_cut_inventory(df)
                st.success(f"[{new_id}] {company} 재단 규격이 등록되었습니다.")

# ========== 작업 플로우 (TODO) ==========
elif menu == "작업 현황판 (칸반)":
    st.subheader("📋 작업 현황판 (칸반 보드)")
    
    df = get_workflow()
    
    # 납품완료 제외한 작업만 표시
    if df.empty:
        active_df = df
    else:
        active_df = df[df['상태'] != '납품완료']
    
    if active_df.empty:
        st.info("진행 중인 작업이 없습니다.")
    else:
        cols = st.columns(4)
        statuses = ['접수', '생산중', '재단중', '완료']
        
        for i, status in enumerate(statuses):
            with cols[i]:
                if status == '접수':
                    st.markdown(f"### 🟡 {status}")
                elif status == '생산중':
                    st.markdown(f"### 🔵 {status}")
                elif status == '재단중':
                    st.markdown(f"### 🟠 {status}")
                else:
                    st.markdown(f"### 🟢 {status}")
                
                status_df = active_df[active_df['상태'] == status]
                
                for _, row in status_df.iterrows():
                    priority_color = {
                        '긴급': '#f44336',
                        '높음': '#ff9800',
                        '보통': '#2196f3',
                        '낮음': '#9e9e9e'
                    }.get(row['우선순위'], '#9e9e9e')
                    
                    st.markdown(f"""
                    <div style="border-left: 4px solid {priority_color}; padding: 10px; margin: 5px 0; background: #f9f9f9; border-radius: 4px;">
                        <strong>[{row['작업ID']}]</strong> {row['업체명']}<br>
                        📐 {row['제품규격']}<br>
                        📦 {row['수량']} {row['단위']}<br>
                        👤 {row['담당자']}<br>
                        📅 납기: {row['납기일']}<br>
                        <small>📝 {row['메모']}</small>
                    </div>
                    """, unsafe_allow_html=True)
                
                if len(status_df) == 0:
                    st.caption("작업 없음")

elif menu == "신규 작업 등록":
    st.subheader("✨ 새로운 작업 등록")
    
    with st.form("new_workflow_form"):
        col1, col2 = st.columns(2)
        with col1:
            work_id = st.text_input("작업 ID (예: W-003)", placeholder="고유 번호 입력")
            company = st.text_input("업체명", placeholder="업체명 입력")
            spec = st.text_input("제품 규격", placeholder="예: 0.05T x 50cm x 70cm")
            quantity = st.number_input("수량", min_value=1, value=1)
        with col2:
            unit = st.selectbox("단위", ["장", "롤", "kg", "m"])
            managers = load_managers()
            manager_choice = None
            if managers:
                manager_choice = st.selectbox("담당자", managers + ["직접입력"], index=0)
            else:
                manager_choice = "직접입력"
            if manager_choice == "직접입력":
                manager = st.text_input("담당자", placeholder="담당자 이름")
            else:
                manager = manager_choice
            priority = st.selectbox("우선순위", PRIORITY_OPTIONS)
            due_date = st.date_input("납기일", value=date.today())
        
        memo = st.text_area("메모", placeholder="추가 정보나 특이사항 입력")
        
        submitted = st.form_submit_button("작업 등록")
        
        if submitted:
            df = get_workflow()
            if work_id in df['작업ID'].values:
                st.error("이미 존재하는 작업 ID입니다.")
            elif work_id == "" or company == "":
                st.error("작업 ID와 업체명을 입력해주세요.")
            else:
                new_data = pd.DataFrame([{
                    '작업ID': work_id,
                    '업체명': company,
                    '제품규격': spec,
                    '수량': quantity,
                    '단위': unit,
                    '담당자': manager,
                    '상태': '접수',
                    '우선순위': priority,
                    '납기일': due_date.strftime("%Y-%m-%d"),
                    '메모': memo,
                    '등록일': datetime.now().strftime("%Y-%m-%d %H:%M")
                }])
                df = pd.concat([df, new_data], ignore_index=True)
                save_workflow(df)
                st.success(f"[{work_id}] 작업이 등록되었습니다.")

# ========== 작업자 관리 ==========
elif menu == "작업자 관리":
    st.subheader("👥 작업자 관리")

    mgrs = load_managers()
    st.write("등록된 작업자:")
    st.write(mgrs if mgrs else "(없음)")

    with st.form("add_manager_form"):
        new_mgr = st.text_input("작업자 이름", placeholder="이름 입력")
        add_sub = st.form_submit_button("작업자 추가")
        if add_sub:
            if new_mgr.strip() == "":
                st.error("작업자 이름을 입력해주세요.")
            else:
                add_manager(new_mgr.strip())
                st.success(f"작업자 '{new_mgr.strip()}'가 추가되었습니다.")
                st.experimental_rerun()

    # 삭제
    if mgrs:
        to_delete = st.multiselect("삭제할 작업자 선택", mgrs)
        if st.button("선택한 작업자 삭제", key='delete_mgr'):
            for m in to_delete:
                delete_manager(m)
            st.success(f"{len(to_delete)}명 삭제되었습니다.")
            st.experimental_rerun()

elif menu == "작업 상태 변경":
    st.subheader("🔄 작업 상태 변경")
    
    df = get_workflow()
    
    if df.empty:
        active_df = df
    else:
        active_df = df[df['상태'] != '납품완료']
    
    if active_df.empty:
        st.info("진행 중인 작업이 없습니다.")
    else:
        work_list = active_df.apply(
            lambda x: f"[{x['작업ID']}] {x['업체명']} - {x['제품규격']} ({x['상태']})", 
            axis=1
        )
        selected_work_str = st.selectbox("작업을 선택하세요", work_list)
        selected_id = selected_work_str.split(']')[0].replace('[', '')
        
        current_status = df[df['작업ID'] == selected_id]['상태'].values[0]
        st.info(f"현재 상태: **{current_status}**")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            new_status = st.selectbox("변경할 상태", STATUS_ORDER)
        
        with col2:
            if st.button("상태 변경"):
                idx = df[df['작업ID'] == selected_id].index[0]
                df.loc[idx, '상태'] = new_status
                save_workflow(df)
                st.success(f"작업 [{selected_id}] 상태가 '{new_status}'(으)로 변경되었습니다.")
                st.rerun()
        
        with col3:
            current_idx = STATUS_ORDER.index(current_status)
            if current_idx < len(STATUS_ORDER) - 1:
                next_status = STATUS_ORDER[current_idx + 1]
                if st.button(f"▶️ {next_status}로 진행"):
                    idx = df[df['작업ID'] == selected_id].index[0]
                    df.loc[idx, '상태'] = next_status
                    save_workflow(df)
                    st.success(f"작업이 '{next_status}' 단계로 진행되었습니다.")
                    st.rerun()

        # 편집 및 삭제 UI (워크플로우)
        with st.expander('작업 수정/삭제'):
            sel = df[df['작업ID'] == selected_id].iloc[0]

            new_company = st.text_input('업체명', value=sel['업체명'])
            new_spec = st.text_input('제품 규격', value=sel['제품규격'])
            new_qty = st.number_input('수량', min_value=1, value=int(sel['수량']))
            new_unit = st.selectbox('단위', ['장', '롤', 'kg', 'm'], index=['장','롤','kg','m'].index(sel['단위']) if sel['단위'] in ['장','롤','kg','m'] else 0)
            managers = load_managers()
            if managers:
                manager_choice = st.selectbox('담당자', managers + ['직접입력'], index=managers.index(sel['담당자']) if sel['담당자'] in managers else len(managers))
                if manager_choice == '직접입력':
                    new_manager = st.text_input('담당자', value=sel['담당자'])
                else:
                    new_manager = manager_choice
            else:
                new_manager = st.text_input('담당자', value=sel['담당자'])
            new_priority = st.selectbox('우선순위', PRIORITY_OPTIONS, index=PRIORITY_OPTIONS.index(sel['우선순위']) if sel['우선순위'] in PRIORITY_OPTIONS else 2)
            new_due = st.date_input('납기일', value=datetime.strptime(sel['납기일'], "%Y-%m-%d").date() if sel['납기일'] else date.today())
            new_memo = st.text_area('메모', value=sel['메모'])

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button('저장(작업 변경)'):
                    try:
                        update_workflow_item(selected_id, 업체명=new_company, 제품규격=new_spec, 수량=new_qty, 단위=new_unit, 담당자=new_manager, 우선순위=new_priority, 납기일=new_due.strftime("%Y-%m-%d"), 메모=new_memo)
                        st.success(f"[{selected_id}] 작업이 업데이트되었습니다.")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
            with col_b:
                confirm = st.checkbox('삭제 확인 (체크 후 삭제)', key='confirm_delete_work')
                if st.button('삭제(작업 삭제)') and confirm:
                    delete_workflow_item(selected_id)
                    st.success(f"[{selected_id}] 작업이 삭제되었습니다.")
                    st.rerun()
                elif st.button('삭제(작업 삭제)') and not confirm:
                    st.error('삭제하려면 확인 체크박스를 선택하세요.')

elif menu == "완료된 작업 보기":
    st.subheader("✅ 완료된 작업 목록")
    
    df = get_workflow()
    
    if df.empty:
        completed_df = df
    else:
        completed_df = df[df['상태'] == '납품완료']
    
    if completed_df.empty:
        st.info("완료된 작업이 없습니다.")
    else:
        st.dataframe(completed_df, use_container_width=True, height=400)
        
        st.markdown("---")
        st.caption("⚠️ 완료된 작업 정리")
        
        work_list = completed_df['작업ID'].tolist()
        selected_to_delete = st.multiselect("삭제할 작업 선택", work_list)
        
        if st.button("선택한 작업 삭제", type="secondary"):
            if selected_to_delete:
                df = df[~df['작업ID'].isin(selected_to_delete)]
                save_workflow(df)
                st.success(f"{len(selected_to_delete)}개 작업이 삭제되었습니다.")
                st.rerun()

# 하단 푸터
st.markdown("---")
st.markdown("© 2026 유한화학 재고 시스템")

# ========== PWA 아이콘/manifest 연결 ==========
# static 폴더에 icon-192.png / icon-512.png 를 넣으면 자동으로 파비콘/애플 아이콘 및 manifest에 사용됩니다.
STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')

def _load_icon_base64(name):
    p = os.path.join(STATIC_DIR, name)
    if os.path.exists(p):
        with open(p, 'rb') as f:
            return base64.b64encode(f.read()).decode('ascii')
    return None

_icon_192 = _load_icon_base64('icon-192.png')
_icon_512 = _load_icon_base64('icon-512.png')

if _icon_192:
    st.markdown(f'<link rel="icon" href="data:image/png;base64,{_icon_192}">', unsafe_allow_html=True)
    st.markdown(f'<link rel="apple-touch-icon" sizes="192x192" href="data:image/png;base64,{_icon_192}">', unsafe_allow_html=True)

# manifest를 클라이언트에서 Blob으로 생성하여 연결 (data: 또는 blob: 지원 문제 회피)
manifest_obj = {
    "name": "유한화학 재고",
    "short_name": "재고",
    "start_url": ".",
    "display": "standalone",
    "theme_color": "#ffffff",
    "background_color": "#ffffff",
}
icons = []
if _icon_192:
    icons.append({"src": f"data:image/png;base64,{_icon_192}", "sizes": "192x192", "type": "image/png"})
if _icon_512:
    icons.append({"src": f"data:image/png;base64,{_icon_512}", "sizes": "512x512", "type": "image/png"})
if icons:
    manifest_obj["icons"] = icons

# 클라이언트에서 manifest Blob 생성 및 link[rel="manifest"] 연결
components.html(f"""
<script>
  const manifest = {json.dumps(manifest_obj)};
  const blob = new Blob([JSON.stringify(manifest)], {{type: 'application/json'}});
  const url = URL.createObjectURL(blob);
  let link = document.querySelector('link[rel="manifest"]');
  if (!link) {{
    link = document.createElement('link');
    link.rel = 'manifest';
    document.head.appendChild(link);
  }}
  link.href = url;
</script>
""", height=0)

# 안내: 아이콘이 없는 경우 사용자가 static/에 파일을 넣도록 알림
if not (_icon_192 and _icon_512):
    st.info("모바일 홈화면 아이콘을 사용하려면 `./static/icon-192.png` 및 `./static/icon-512.png` 파일을 추가하세요. (권장: 192×192, 512×512 PNG)")
