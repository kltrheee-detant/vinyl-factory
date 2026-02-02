# Firebase Firestore 데이터베이스 함수
"""
기존 SQLite 함수를 Firebase Firestore로 대체
실시간 동기화 지원
"""
import pandas as pd
from datetime import datetime
from firebase_config import get_firestore_client


# ========== 롤 재고 관리 ==========

def load_roll_inventory():
    """롤 재고 데이터 로드"""
    db = get_firestore_client()
    
    if db is None:
        return pd.DataFrame(columns=['제품ID', '두께(mm)', '폭(cm)', '롤 길이(m)', '현재고(롤)', '최근업데이트'])
    
    try:
        docs = db.collection('roll_inventory').stream()
        data = []
        
        for doc in docs:
            d = doc.to_dict()
            data.append({
                '제품ID': doc.id,
                '두께(mm)': d.get('두께_mm', 0),
                '폭(cm)': d.get('폭_cm', 0),
                '롤 길이(m)': d.get('롤길이_m', 0),
                '현재고(롤)': d.get('현재고_롤', 0),
                '최근업데이트': d.get('최근업데이트', '')
            })
        
        if not data:
            return pd.DataFrame(columns=['제품ID', '두께(mm)', '폭(cm)', '롤 길이(m)', '현재고(롤)', '최근업데이트'])
        
        return pd.DataFrame(data)
        
    except Exception as e:
        print(f"롤 재고 로드 오류: {e}")
        return pd.DataFrame(columns=['제품ID', '두께(mm)', '폭(cm)', '롤 길이(m)', '현재고(롤)', '최근업데이트'])


def save_roll_inventory(df):
    """롤 재고 데이터 저장"""
    db = get_firestore_client()
    
    if db is None:
        raise Exception("Firebase 연결 실패")
    
    batch = db.batch()
    
    for _, row in df.iterrows():
        if float(row['현재고(롤)']) < 0:
            raise ValueError("현재고(롤)은 음수일 수 없습니다")
        
        doc_ref = db.collection('roll_inventory').document(str(row['제품ID']))
        batch.set(doc_ref, {
            '두께_mm': float(row['두께(mm)']),
            '폭_cm': float(row['폭(cm)']),
            '롤길이_m': float(row['롤 길이(m)']),
            '현재고_롤': int(row['현재고(롤)']),
            '최근업데이트': row['최근업데이트']
        })
    
    batch.commit()


def update_roll_item(product_id, **kwargs):
    """롤 아이템 업데이트"""
    db = get_firestore_client()
    
    if db is None:
        raise Exception("Firebase 연결 실패")
    
    doc_ref = db.collection('roll_inventory').document(str(product_id))
    doc = doc_ref.get()
    
    if not doc.exists:
        raise KeyError(f"제품ID {product_id} 없음")
    
    update_data = {}
    for k, v in kwargs.items():
        if k == '두께_mm' or k == '두께(mm)':
            update_data['두께_mm'] = float(v)
        elif k == '폭_cm' or k == '폭(cm)':
            update_data['폭_cm'] = float(v)
        elif k == '롤길이_m' or k == '롤 길이(m)':
            update_data['롤길이_m'] = float(v)
        elif k == '현재고_롤' or k == '현재고(롤)':
            update_data['현재고_롤'] = int(v)
    
    update_data['최근업데이트'] = datetime.now().strftime("%Y-%m-%d %H:%M")
    doc_ref.update(update_data)


def delete_roll_item(product_id):
    """롤 아이템 삭제"""
    db = get_firestore_client()
    
    if db is None:
        raise Exception("Firebase 연결 실패")
    
    db.collection('roll_inventory').document(str(product_id)).delete()


def record_roll_transaction(item_id, delta, note=""):
    """롤 거래 기록"""
    db = get_firestore_client()
    
    if db is None:
        return
    
    db.collection('transactions').add({
        'item_type': 'roll',
        'item_id': str(item_id),
        'delta': float(delta),
        'note': note,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


def get_monthly_usage_roll(item_id, year=None, month=None):
    """월별 롤 사용량 조회"""
    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month
    
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    
    db = get_firestore_client()
    
    if db is None:
        return 0.0
    
    try:
        docs = db.collection('transactions')\
            .where('item_type', '==', 'roll')\
            .where('item_id', '==', str(item_id))\
            .stream()
        
        total = 0.0
        for doc in docs:
            d = doc.to_dict()
            ts = datetime.strptime(d.get('timestamp', ''), "%Y-%m-%d %H:%M:%S")
            delta = d.get('delta', 0)
            if start <= ts < end and delta < 0:
                total += -delta
        
        return total
        
    except Exception:
        return 0.0


# ========== 재단 재고 관리 ==========

def load_cut_inventory():
    """재단 재고 데이터 로드"""
    db = get_firestore_client()
    
    if db is None:
        return pd.DataFrame(columns=['재단ID', '업체명', '가로(cm)', '세로(cm)', '두께(mm)', '현재고(장)', '최근업데이트'])
    
    try:
        docs = db.collection('cut_inventory').stream()
        data = []
        
        for doc in docs:
            d = doc.to_dict()
            data.append({
                '재단ID': doc.id,
                '업체명': d.get('업체명', ''),
                '가로(cm)': d.get('가로_cm', 0),
                '세로(cm)': d.get('세로_cm', 0),
                '두께(mm)': d.get('두께_mm', 0),
                '현재고(장)': d.get('현재고_장', 0),
                '최근업데이트': d.get('최근업데이트', '')
            })
        
        if not data:
            return pd.DataFrame(columns=['재단ID', '업체명', '가로(cm)', '세로(cm)', '두께(mm)', '현재고(장)', '최근업데이트'])
        
        return pd.DataFrame(data)
        
    except Exception as e:
        print(f"재단 재고 로드 오류: {e}")
        return pd.DataFrame(columns=['재단ID', '업체명', '가로(cm)', '세로(cm)', '두께(mm)', '현재고(장)', '최근업데이트'])


def save_cut_inventory(df):
    """재단 재고 데이터 저장"""
    db = get_firestore_client()
    
    if db is None:
        raise Exception("Firebase 연결 실패")
    
    batch = db.batch()
    
    for _, row in df.iterrows():
        if float(row['현재고(장)']) < 0:
            raise ValueError("현재고(장)은 음수일 수 없습니다")
        
        doc_ref = db.collection('cut_inventory').document(str(row['재단ID']))
        batch.set(doc_ref, {
            '업체명': row['업체명'],
            '가로_cm': float(row['가로(cm)']),
            '세로_cm': float(row['세로(cm)']),
            '두께_mm': float(row['두께(mm)']),
            '현재고_장': int(row['현재고(장)']),
            '최근업데이트': row['최근업데이트']
        })
    
    batch.commit()


def update_cut_item(item_id, **kwargs):
    """재단 아이템 업데이트"""
    db = get_firestore_client()
    
    if db is None:
        raise Exception("Firebase 연결 실패")
    
    doc_ref = db.collection('cut_inventory').document(str(item_id))
    doc = doc_ref.get()
    
    if not doc.exists:
        raise KeyError(f"재단ID {item_id} 없음")
    
    update_data = {}
    for k, v in kwargs.items():
        if k == '업체명':
            update_data['업체명'] = v
        elif k == '가로_cm':
            update_data['가로_cm'] = float(v)
        elif k == '세로_cm':
            update_data['세로_cm'] = float(v)
        elif k == '두께_mm':
            update_data['두께_mm'] = float(v)
        elif k == '현재고_장':
            update_data['현재고_장'] = int(v)
    
    update_data['최근업데이트'] = datetime.now().strftime("%Y-%m-%d %H:%M")
    doc_ref.update(update_data)


def delete_cut_item(item_id):
    """재단 아이템 삭제"""
    db = get_firestore_client()
    
    if db is None:
        raise Exception("Firebase 연결 실패")
    
    db.collection('cut_inventory').document(str(item_id)).delete()


def record_cut_transaction(item_id, delta, note=""):
    """재단 거래 기록"""
    db = get_firestore_client()
    
    if db is None:
        return
    
    db.collection('transactions').add({
        'item_type': 'cut',
        'item_id': str(item_id),
        'delta': float(delta),
        'note': note,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


def get_monthly_usage_cut(item_id, year=None, month=None):
    """월별 재단 사용량 조회"""
    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month
    
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    
    db = get_firestore_client()
    
    if db is None:
        return 0.0
    
    try:
        docs = db.collection('transactions')\
            .where('item_type', '==', 'cut')\
            .where('item_id', '==', str(item_id))\
            .stream()
        
        total = 0.0
        for doc in docs:
            d = doc.to_dict()
            ts = datetime.strptime(d.get('timestamp', ''), "%Y-%m-%d %H:%M:%S")
            delta = d.get('delta', 0)
            if start <= ts < end and delta < 0:
                total += -delta
        
        return total
        
    except Exception:
        return 0.0


# ========== 재주문 임계값 관리 ==========

def set_reorder_level(item_type, item_id, threshold):
    """재주문 임계값 설정"""
    db = get_firestore_client()
    
    if db is None:
        return
    
    doc_id = f"{item_type}_{item_id}"
    db.collection('reorder_levels').document(doc_id).set({
        'item_type': item_type,
        'item_id': str(item_id),
        'threshold': float(threshold)
    })


def get_reorder_level(item_type, item_id):
    """재주문 임계값 조회"""
    db = get_firestore_client()
    
    if db is None:
        return None
    
    try:
        doc_id = f"{item_type}_{item_id}"
        doc = db.collection('reorder_levels').document(doc_id).get()
        
        if doc.exists:
            return float(doc.to_dict().get('threshold', 0))
        return None
        
    except Exception:
        return None


# ========== 작업 플로우 관리 ==========

def load_workflow():
    """작업 플로우 데이터 로드"""
    db = get_firestore_client()
    
    if db is None:
        return pd.DataFrame(columns=['작업ID', '업체명', '제품규격', '수량', '단위', '담당자', '상태', '우선순위', '납기일', '메모', '등록일'])
    
    try:
        docs = db.collection('workflow').stream()
        data = []
        
        for doc in docs:
            d = doc.to_dict()
            data.append({
                '작업ID': doc.id,
                '업체명': d.get('업체명', ''),
                '제품규격': d.get('제품규격', ''),
                '수량': d.get('수량', 0),
                '단위': d.get('단위', ''),
                '담당자': d.get('담당자', ''),
                '상태': d.get('상태', '접수'),
                '우선순위': d.get('우선순위', '보통'),
                '납기일': d.get('납기일', ''),
                '메모': d.get('메모', ''),
                '등록일': d.get('등록일', '')
            })
        
        if not data:
            return pd.DataFrame(columns=['작업ID', '업체명', '제품규격', '수량', '단위', '담당자', '상태', '우선순위', '납기일', '메모', '등록일'])
        
        return pd.DataFrame(data)
        
    except Exception as e:
        print(f"작업 플로우 로드 오류: {e}")
        return pd.DataFrame(columns=['작업ID', '업체명', '제품규격', '수량', '단위', '담당자', '상태', '우선순위', '납기일', '메모', '등록일'])


def save_workflow(df):
    """작업 플로우 데이터 저장"""
    db = get_firestore_client()
    
    if db is None:
        raise Exception("Firebase 연결 실패")
    
    batch = db.batch()
    
    # 기존 문서 삭제
    existing_docs = db.collection('workflow').stream()
    for doc in existing_docs:
        batch.delete(doc.reference)
    
    # 새 데이터 추가
    for _, row in df.iterrows():
        doc_ref = db.collection('workflow').document(str(row['작업ID']))
        batch.set(doc_ref, {
            '업체명': row['업체명'],
            '제품규격': row['제품규격'],
            '수량': int(row['수량']),
            '단위': row['단위'],
            '담당자': row['담당자'],
            '상태': row['상태'],
            '우선순위': row['우선순위'],
            '납기일': row['납기일'],
            '메모': row['메모'],
            '등록일': row['등록일']
        })
    
    batch.commit()


def update_workflow_item(work_id, **kwargs):
    """작업 플로우 아이템 업데이트"""
    db = get_firestore_client()
    
    if db is None:
        raise Exception("Firebase 연결 실패")
    
    doc_ref = db.collection('workflow').document(str(work_id))
    doc = doc_ref.get()
    
    if not doc.exists:
        raise KeyError(f"작업ID {work_id} 없음")
    
    update_data = {}
    for k, v in kwargs.items():
        if k in ['업체명', '제품규격', '단위', '담당자', '상태', '우선순위', '납기일', '메모']:
            update_data[k] = v
        elif k == '수량':
            update_data[k] = int(v)
    
    doc_ref.update(update_data)


def delete_workflow_item(work_id):
    """작업 플로우 아이템 삭제"""
    db = get_firestore_client()
    
    if db is None:
        raise Exception("Firebase 연결 실패")
    
    db.collection('workflow').document(str(work_id)).delete()
