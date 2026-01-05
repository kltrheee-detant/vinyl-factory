import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime, date

# 데이터베이스 파일 경로
DB_PATH = os.path.join(os.path.dirname(__file__), 'inventory.db')

# ========== 데이터베이스 함수 ==========
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

# 데이터베이스 초기화
init_db()

# 페이지 기본 설정
st.set_page_config(page_title="비닐 공장 재고 현황판", layout="wide")

# 스타일링
st.markdown("""
    <style>
        .big-font { font-size: 20px !important; font-weight: bold; }
        .stDataFrame { width: 100%; }
    </style>
""", unsafe_allow_html=True)

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
        st.dataframe(
            df.style.format({
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
        st.dataframe(
            df.style.format({
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
            manager = st.text_input("담당자", placeholder="담당자 이름")
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
