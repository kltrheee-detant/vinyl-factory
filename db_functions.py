"""
데이터베이스 관련 함수들 (테스트용으로 분리)
"""
import sqlite3
import os
from datetime import datetime
import pandas as pd

# 데이터베이스 파일 경로
DB_PATH = os.path.join(os.path.dirname(__file__), 'inventory.db')


def init_db():
    """데이터베이스 초기화 - 테이블 생성"""
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
    conn.commit()
    conn.close()


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


def save_roll_inventory(df):
    """롤 재고 데이터 저장"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for _, row in df.iterrows():
        # 재고는 음수일 수 없음
        if float(row['현재고(롤)']) < 0:
            conn.close()
            raise ValueError("현재고(롤)은 음수일 수 없습니다")

        cursor.execute('''
            INSERT OR REPLACE INTO roll_inventory (제품ID, 두께_mm, 폭_cm, 롤길이_m, 현재고_롤, 최근업데이트)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (row['제품ID'], row['두께(mm)'], row['폭(cm)'], row['롤 길이(m)'], row['현재고(롤)'], row['최근업데이트']))
    
    conn.commit()
    conn.close()


def update_roll_item(product_id, **kwargs):
    df = load_roll_inventory()
    if product_id not in df['제품ID'].values:
        raise KeyError(f"제품ID {product_id} 없음")
    idx = df[df['제품ID'] == product_id].index[0]
    for k, v in kwargs.items():
        if k == '두께_mm' or k == '두께(mm)':
            df.loc[idx, '두께(mm)'] = v
        elif k == '폭_cm' or k == '폭(cm)':
            df.loc[idx, '폭(cm)'] = v
        elif k == '롤길이_m' or k == '롤 길이(m)':
            df.loc[idx, '롤 길이(m)'] = v
        elif k == '현재고_롤' or k == '현재고(롤)':
            df.loc[idx, '현재고(롤)'] = v
    df.loc[idx, '최근업데이트'] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_roll_inventory(df)


def delete_roll_item(product_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM roll_inventory WHERE 제품ID = ?', (product_id,))
    conn.commit()
    conn.close()


def load_cut_inventory():
    """재단 재고 데이터 로드"""
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


def save_cut_inventory(df):
    """재단 재고 데이터 저장"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for _, row in df.iterrows():
        # 재고는 음수일 수 없음
        if float(row['현재고(장)']) < 0:
            conn.close()
            raise ValueError("현재고(장)은 음수일 수 없습니다")

        cursor.execute('''
            INSERT OR REPLACE INTO cut_inventory (재단ID, 업체명, 가로_cm, 세로_cm, 두께_mm, 현재고_장, 최근업데이트)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (row['재단ID'], row['업체명'], row['가로(cm)'], row['세로(cm)'], row['두께(mm)'], row['현재고(장)'], row['최근업데이트']))
    
    conn.commit()
    conn.close()


def update_cut_item(item_id, **kwargs):
    df = load_cut_inventory()
    if item_id not in df['재단ID'].values:
        raise KeyError(f"재단ID {item_id} 없음")
    idx = df[df['재단ID'] == item_id].index[0]
    for k, v in kwargs.items():
        # kwargs use DB column names (업체명, 가로_cm etc)
        if k in ['업체명', '가로_cm', '세로_cm', '두께_mm', '현재고_장']:
            # map to display columns if necessary
            if k == '업체명':
                df.loc[idx, '업체명'] = v
            elif k == '가로_cm':
                df.loc[idx, '가로(cm)'] = v
            elif k == '세로_cm':
                df.loc[idx, '세로(cm)'] = v
            elif k == '두께_mm':
                df.loc[idx, '두께(mm)'] = v
            elif k == '현재고_장':
                df.loc[idx, '현재고(장)'] = v
    df.loc[idx, '최근업데이트'] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_cut_inventory(df)


def delete_cut_item(item_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM cut_inventory WHERE 재단ID = ?', (item_id,))
    conn.commit()
    conn.close()


def load_workflow():
    """작업 플로우 데이터 로드"""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM workflow", conn)
    conn.close()
    
    if df.empty:
        return pd.DataFrame(columns=['작업ID', '업체명', '제품규격', '수량', '단위', '담당자', '상태', '우선순위', '납기일', '메모', '등록일'])
    
    return df[['작업ID', '업체명', '제품규격', '수량', '단위', '담당자', '상태', '우선순위', '납기일', '메모', '등록일']]


def save_workflow(df):
    """작업 플로우 데이터 저장"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 기존 데이터 삭제 후 새로 저장
    cursor.execute("DELETE FROM workflow")
    
    for _, row in df.iterrows():
        cursor.execute('''
            INSERT INTO workflow (작업ID, 업체명, 제품규격, 수량, 단위, 담당자, 상태, 우선순위, 납기일, 메모, 등록일)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (row['작업ID'], row['업체명'], row['제품규격'], row['수량'], row['단위'], 
              row['담당자'], row['상태'], row['우선순위'], row['납기일'], row['메모'], row['등록일']))
    
    conn.commit()
    conn.close()


def update_workflow_item(work_id, **kwargs):
    df = load_workflow()
    if work_id not in df['작업ID'].values:
        raise KeyError(f"작업ID {work_id} 없음")
    idx = df[df['작업ID'] == work_id].index[0]
    for k, v in kwargs.items():
        if k in df.columns:
            df.loc[idx, k] = v
    save_workflow(df)


def delete_workflow_item(work_id):
    df = load_workflow()
    df = df[df['작업ID'] != work_id]
    save_workflow(df)
