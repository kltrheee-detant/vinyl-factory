# Firebase 설정 및 인증
"""
Firebase 연결 설정 및 회사 코드 인증 관리
"""
import os
import json
import streamlit as st

# Firebase 클라이언트 초기화 (lazy loading)
_db = None
_initialized = False


def initialize_firebase():
    """Firebase 초기화"""
    global _db, _initialized
    
    if _initialized:
        return _db
    
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        
        # Streamlit Cloud secrets에서 설정 로드 시도
        if hasattr(st, 'secrets') and 'firebase' in st.secrets:
            # Streamlit Cloud 배포 환경
            cred_dict = dict(st.secrets['firebase'])
            cred = credentials.Certificate(cred_dict)
        else:
            # 로컬 개발 환경 - JSON 파일 사용
            cred_path = os.environ.get(
                'FIREBASE_CREDENTIALS_PATH',
                os.path.join(os.path.dirname(__file__), 'firebase_credentials.json')
            )
            
            if not os.path.exists(cred_path):
                return None
            
            cred = credentials.Certificate(cred_path)
        
        # Firebase 앱이 이미 초기화되어 있는지 확인
        try:
            firebase_admin.get_app()
        except ValueError:
            firebase_admin.initialize_app(cred)
        
        _db = firestore.client()
        _initialized = True
        return _db
        
    except Exception as e:
        st.error(f"Firebase 초기화 오류: {e}")
        return None


def get_firestore_client():
    """Firestore 클라이언트 반환"""
    return initialize_firebase()


def verify_company_code(input_code: str) -> bool:
    """
    회사 코드 검증
    
    Args:
        input_code: 사용자가 입력한 회사 코드
        
    Returns:
        bool: 코드가 일치하면 True
    """
    db = get_firestore_client()
    
    if db is None:
        # Firebase 연결 실패 시 환경변수로 폴백
        env_code = os.environ.get('COMPANY_CODE', '2026')
        return input_code == env_code
    
    try:
        # Firestore에서 회사 코드 조회
        settings_ref = db.collection('settings').document('auth')
        settings = settings_ref.get()
        
        if settings.exists:
            company_code = settings.to_dict().get('company_code', '')
            return input_code == company_code
        else:
            # 설정이 없으면 기본 코드 생성
            default_code = os.environ.get('COMPANY_CODE', '2026')
            settings_ref.set({'company_code': default_code})
            return input_code == default_code
            
    except Exception as e:
        st.error(f"인증 확인 오류: {e}")
        return False


def get_company_code() -> str:
    """현재 설정된 회사 코드 반환 (관리용)"""
    db = get_firestore_client()
    
    if db is None:
        return os.environ.get('COMPANY_CODE', '2026')
    
    try:
        settings_ref = db.collection('settings').document('auth')
        settings = settings_ref.get()
        
        if settings.exists:
            return settings.to_dict().get('company_code', '2026')
        return '2026'
        
    except Exception:
        return '2026'


def update_company_code(new_code: str) -> bool:
    """회사 코드 업데이트"""
    db = get_firestore_client()
    
    if db is None:
        return False
    
    try:
        settings_ref = db.collection('settings').document('auth')
        settings_ref.set({'company_code': new_code}, merge=True)
        return True
    except Exception:
        return False
