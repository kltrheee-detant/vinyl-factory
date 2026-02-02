
import os
from datetime import datetime, date
import pandas as pd
import streamlit as st

# Firebase 데이터베이스 함수 import
from firebase_db import (
    load_roll_inventory, save_roll_inventory, update_roll_item, delete_roll_item,
    record_roll_transaction, get_monthly_usage_roll,
    load_cut_inventory, save_cut_inventory, update_cut_item, delete_cut_item,
    record_cut_transaction, get_monthly_usage_cut,
    load_workflow, save_workflow, update_workflow_item, delete_workflow_item,
    set_reorder_level, get_reorder_level,
    load_raw_materials, save_raw_materials, log_raw_material_transaction
)
from firebase_config import verify_company_code, get_firestore_client

# 페이지 기본 설정
st.set_page_config(page_title="비닐 공장 재고 현황판", layout="wide")

# 스타일링
st.markdown("""
    <style>
        .big-font { font-size: 20px !important; font-weight: bold; }
        .stDataFrame { width: 100%; }
        .login-container {
            max-width: 400px;
            margin: 100px auto;
            padding: 40px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        }
        .login-title {
            color: white;
            text-align: center;
            font-size: 28px;
            margin-bottom: 30px;
        }
    </style>
""", unsafe_allow_html=True)

# ========== 로그인 시스템 ==========
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    # 로그인 화면
    st.markdown("<h1 style='text-align: center; color: #667eea;'>🏭 유한화학 재고 시스템</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #666;'>회사 인증 코드를 입력하세요</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            company_code = st.text_input(
                "🔐 회사 코드",
                type="password",
                placeholder="인증 코드를 입력하세요",
                help="관리자에게 회사 코드를 요청하세요"
            )
            
            submitted = st.form_submit_button("로그인", use_container_width=True)
            
            if submitted:
                if company_code.strip() == "":
                    st.error("회사 코드를 입력해주세요.")
                elif verify_company_code(company_code):
                    st.session_state.authenticated = True
                    st.success("로그인 성공! 잠시 후 메인 화면으로 이동합니다...")
                    st.rerun()
                else:
                    st.error("잘못된 회사 코드입니다. 다시 확인해주세요.")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Firebase 연결 상태 표시
        db = get_firestore_client()
        if db is not None:
            st.success("☁️ 클라우드 연결됨")
        else:
            st.warning("⚠️ 오프라인 모드 (Firebase 설정 필요)")
            with st.expander("Firebase 설정 안내"):
                st.markdown("""
                1. [Firebase Console](https://console.firebase.google.com/)에서 프로젝트 생성
                2. Firestore Database 활성화
                3. 서비스 계정 키 다운로드
                4. `firebase_credentials.json` 파일을 프로젝트 폴더에 저장
                """)
    
    st.stop()

# ========== 메인 앱 (인증 후) ==========

# 제목
st.title("🏭 유한화학 재고 현황판")

# Firebase 연결 상태 표시
db = get_firestore_client()
if db is not None:
    st.caption("☁️ Firebase 클라우드 데이터베이스 연동됨")
else:
    st.caption("⚠️ 오프라인 모드 - Firebase 설정 필요")

st.markdown("---")

# 데이터 로드 (새로고침 버튼 추가)
col_refresh, col_logout, col_empty = st.columns([1, 1, 4])
with col_refresh:
    if st.button("🔄 새로고침"):
        st.rerun()
with col_logout:
    if st.button("🚪 로그아웃"):
        st.session_state.authenticated = False
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

menu_category = st.sidebar.selectbox("카테고리 선택", ["📦 롤 재고 관리", "✂️ 재단 재고 관리", "🛢️ 원료 재고 관리", "📋 작업 플로우 (TODO)"])

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
elif menu_category == "🛢️ 원료 재고 관리":
    menu = st.sidebar.radio("작업을 선택하세요", [
        "원료 재고 현황",
        "원료 입/출고",
        "신규 원료 등록"
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
                    update_roll_item(edit_prod, 두께_mm=new_thickness, 폭_cm=new_width, 롤길이_m=new_length, 현재고_롤=new_stock)
                    st.success(f"[{edit_prod}]가 업데이트되었습니다.")
            with col_b:
                if st.button('삭제'):
                    delete_roll_item(edit_prod)
                    st.success(f"[{edit_prod}]가 삭제되었습니다.")

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
                    update_cut_item(edit_prod, 업체명=new_company, 가로_cm=new_width, 세로_cm=new_height, 두께_mm=new_thickness, 현재고_장=new_stock)
                    st.success(f"[{edit_prod}] 재단 데이터가 업데이트되었습니다.")
            with col_b:
                if st.button('삭제', key='delete_cut'):
                    delete_cut_item(edit_prod)
                    st.success(f"[{edit_prod}] 재단 데이터가 삭제되었습니다.")

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

# ========== 원료 재고 관리 ==========
elif menu == "원료 재고 현황":
    st.subheader("🛢️ 원료 재고 목록")
    
    df = load_raw_materials()

    if df.empty:
        st.info("등록된 원료가 없습니다. '신규 원료 등록' 메뉴에서 추가해주세요.")
    else:
        # 정렬
        sort_cols = ['품명', 'Grade', '현재고_kg', '입고일']
        sort_col = st.selectbox('정렬 기준', sort_cols, index=0, key='raw_sort')
        sort_order = st.radio('정렬 순서', ['오름차순', '내림차순'], horizontal=True, key='raw_order')
        ascending = True if sort_order == '오름차순' else False
        
        if sort_col in df.columns:
            df = df.sort_values(by=sort_col, ascending=ascending)

        st.dataframe(
            df.style.format({
                "현재고_kg": "{:.1f}"
            }),
            use_container_width=True,
            height=400
        )
        
        total_kg = df['현재고_kg'].sum()
        st.info(f"📋 총 원료 보유량: {total_kg:,.1f} kg")

elif menu == "원료 입/출고":
    st.subheader("📝 원료 입고 및 사용 등록")
    
    df = load_raw_materials()
    
    if df.empty:
        st.warning("등록된 원료가 없습니다.")
    else:
        # 선택박스 표시용 리스트
        df['label'] = df.apply(lambda x: f"[{x['품명']}] {x['Grade']} (현재: {x['현재고_kg']}kg)", axis=1)
        selected_str = st.selectbox("원료를 선택하세요", df['label'].tolist())
        
        # 선택된 원료 찾기
        selected_row = df[df['label'] == selected_str].iloc[0]
        selected_idx = df[df['label'] == selected_str].index[0]
        
        col1, col2 = st.columns(2)
        with col1:
            input_type = st.radio("구분", ["입고 (+)", "사용 (-)"], horizontal=True, key='raw_type')
        with col2:
            qty = st.number_input("수량 (kg)", min_value=1.0, step=10.0, key='raw_qty')

        if st.button("재고 반영", key='raw_submit'):
            current_qty = float(selected_row['현재고_kg'])
            
            if input_type == "입고 (+)":
                new_qty = current_qty + qty
                df.at[selected_idx, '현재고_kg'] = new_qty
                # 로그 저장
                log_raw_material_transaction(selected_row['품명'], selected_row['Grade'], qty, '입고', datetime.now().strftime("%Y-%m-%d"))
                save_raw_materials(df)
                st.success(f"입고 완료! 현재고: {new_qty} kg")
            else:
                if current_qty < qty:
                    st.error("재고가 부족합니다!")
                else:
                    new_qty = current_qty - qty
                    df.at[selected_idx, '현재고_kg'] = new_qty
                    # 로그 저장
                    log_raw_material_transaction(selected_row['품명'], selected_row['Grade'], -qty, '출고', datetime.now().strftime("%Y-%m-%d"))
                    save_raw_materials(df)
                    st.success(f"사용 등록 완료! 현재고: {new_qty} kg")

elif menu == "신규 원료 등록":
    st.subheader("✨ 신규 원료 등록")
    
    with st.form("new_raw_material"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("품명 (예: LDPE)")
            grade = st.text_input("Grade (예: 530)")
        with col2:
            initial_stock = st.number_input("초기 재고 (kg)", min_value=0.0, step=10.0)
            in_date = st.date_input("입고일", value=date.today())
            
        note = st.text_area("비고")
        
        submitted = st.form_submit_button("등록")
        
        if submitted:
            if not name or not grade:
                st.error("품명과 Grade는 필수입니다.")
            else:
                df = load_raw_materials()
                
                # 중복 체크
                duplicate = df[(df['품명'] == name) & (df['Grade'] == grade)]
                if not duplicate.empty:
                    st.error("이미 등록된 품명/Grade 입니다.")
                else:
                    new_data = pd.DataFrame([{
                        '품명': name,
                        'Grade': grade,
                        '현재고_kg': initial_stock,
                        '입고일': in_date.strftime("%Y-%m-%d"),
                        '비고': note
                    }])
                    df = pd.concat([df, new_data], ignore_index=True)
                    save_raw_materials(df)
                    st.success(f"[{name} {grade}] 등록되었습니다.")


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

        # 편집 및 삭제 UI (워크플로우)
        with st.expander('작업 수정/삭제'):
            sel = df[df['작업ID'] == selected_id].iloc[0]

            new_company = st.text_input('업체명', value=sel['업체명'])
            new_spec = st.text_input('제품 규격', value=sel['제품규격'])
            new_qty = st.number_input('수량', min_value=1, value=int(sel['수량']))
            new_unit = st.selectbox('단위', ['장', '롤', 'kg', 'm'], index=['장','롤','kg','m'].index(sel['단위']) if sel['단위'] in ['장','롤','kg','m'] else 0)
            new_manager = st.text_input('담당자', value=sel['담당자'])
            new_priority = st.selectbox('우선순위', PRIORITY_OPTIONS, index=PRIORITY_OPTIONS.index(sel['우선순위']) if sel['우선순위'] in PRIORITY_OPTIONS else 2)
            new_due = st.date_input('납기일', value=datetime.strptime(sel['납기일'], "%Y-%m-%d").date() if sel['납기일'] else date.today())
            new_memo = st.text_area('메모', value=sel['메모'])

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button('저장(작업 변경)'):
                    update_workflow_item(selected_id, 업체명=new_company, 제품규격=new_spec, 수량=new_qty, 단위=new_unit, 담당자=new_manager, 우선순위=new_priority, 납기일=new_due.strftime("%Y-%m-%d"), 메모=new_memo)
                    st.success(f"[{selected_id}] 작업이 업데이트되었습니다.")
                    st.rerun()
            with col_b:
                if st.button('삭제(작업 삭제)'):
                    delete_workflow_item(selected_id)
                    st.success(f"[{selected_id}] 작업이 삭제되었습니다.")
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
