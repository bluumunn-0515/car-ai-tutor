"""
Google Sheets 연동 (streamlit_gsheets.GSheetsConnection 공식 API 기반).
최신 라이브러리 버전 대응 및 Private 모드 검증 강화 버전
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Optional

import pandas as pd
import streamlit as st

try:
    from streamlit_gsheets import GSheetsConnection
except ImportError:
    GSheetsConnection = None 

SHEET_USERS = "users"
SHEET_HISTORY = "history"

USERS_COLS = ["student_id", "name", "password_hash"]
HISTORY_COLS = [
    "datetime", "student_id", "name", "subject", "unit",
    "diagnosis_result", "ncs_score", "mode", "record_id",
    "symptom", "reasoning", "teacher_feedback", "teacher_feedback_updated_at",
    # ── 포트폴리오 확장 컬럼 ──
    # reflection: 학생의 '오늘의 실습 소감' 자유 서술
    # image_b64: 단계 1에서 업로드한 사진의 작은 썸네일(JPEG, base64) — 포트폴리오 표시용
    "reflection", "image_b64",
]

_CACHE_TTL_SEC = 60.0 # 캐시 시간 약간 단축 (실시간성 향상)

# ---------------------------------------------------------------------------
# 비밀번호 해시 유틸
# ---------------------------------------------------------------------------
def _pepper() -> str:
    try:
        p = st.secrets.get("GSHEETS_PASSWORD_PEPPER")
        if p: return str(p)
    except: pass
    return "dev-only-pepper-yongsan-rr"

def hash_student_password(student_id: str, plain_password: str) -> str:
    raw = f"{_pepper()}|{student_id}|{plain_password}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _is_sha256_hex(s: str) -> bool:
    s = (s or "").strip()
    if len(s) != 64: return False
    try:
        int(s, 16)
        return True
    except ValueError: return False

def verify_student_password(student_id: str, plain_password: str, stored_hash: str) -> bool:
    if not stored_hash: return False
    stored_hash = str(stored_hash).strip()
    if _is_sha256_hex(stored_hash):
        return hash_student_password(student_id, plain_password) == stored_hash.lower()
    return plain_password == stored_hash

# ---------------------------------------------------------------------------
# Connection (공식 API 대응)
# ---------------------------------------------------------------------------
def gsheets_available() -> bool:
    return GSheetsConnection is not None

def get_gsheets_connection() -> Any:
    if not gsheets_available():
        raise RuntimeError("st-gsheets-connection 패키지가 없습니다.")
    # 공식 가이드에 따른 연결 방식
    return st.connection("gsheets", type=GSheetsConnection)

def _ensure_private_mode_for_write() -> Any:
    """쓰기 권한(Private Mode)이 활성화되어 있는지 Secrets 기반으로 확인"""
    try:
        conf = st.secrets["connections"]["gsheets"]
        # 'type' 이 service_account 가 아니면 무조건 에러 발생
        if conf.get("type") != "service_account":
             raise RuntimeError("Secrets 설정에서 type = 'service_account'가 아니면 쓰기가 불가능합니다.")
    except Exception:
        raise RuntimeError("Secrets에 구글 서비스 계정 정보가 설정되지 않았습니다.")

    conn = get_gsheets_connection()
    return conn

# ---------------------------------------------------------------------------
# 읽기 및 쓰기 최적화 로직
# ---------------------------------------------------------------------------
def _normalize_df(df: Optional[pd.DataFrame], cols: list[str]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=cols)
    # 컬럼명 공백 제거
    df.columns = [str(c).strip() for c in df.columns]
    # 누락된 컬럼 생성
    for c in cols:
        if c not in df.columns: df[c] = ""
    return df[cols]

def read_users_df() -> pd.DataFrame:
    now = time.time()
    if st.session_state.get("_gs_users_df") is not None and now - st.session_state.get("_gs_users_ts", 0) < _CACHE_TTL_SEC:
        return st.session_state._gs_users_df
    
    conn = get_gsheets_connection()
    try:
        df = conn.read(worksheet=SHEET_USERS, ttl=0)
    except:
        df = pd.DataFrame(columns=USERS_COLS)
    
    df = _normalize_df(df, USERS_COLS)
    st.session_state._gs_users_df = df
    st.session_state._gs_users_ts = now
    return df

def get_user_row(student_id: str) -> Optional[dict[str, Any]]:
    sid = str(student_id).strip()
    df = read_users_df()
    if df.empty: return None
    # 학번 매칭 시 타입을 문자열로 통일하여 비교
    m = df[df["student_id"].astype(str).str.strip() == sid]
    if m.empty: return None
    row = m.iloc[0]
    return {k: str(row.get(k, "")).strip() for k in USERS_COLS}

def _append_rows_via_update(worksheet: str, cols: list[str], new_rows: list[dict[str, Any]]) -> None:
    conn = _ensure_private_mode_for_write()
    # 최신 데이터를 읽어와서 병합 (Append 시뮬레이션)
    try:
        current_df = conn.read(worksheet=worksheet, ttl=0)
    except:
        current_df = pd.DataFrame(columns=cols)
    
    current_df = _normalize_df(current_df, cols)
    new_df = pd.DataFrame(new_rows, columns=cols)
    
    # 모든 데이터를 문자열로 변환하여 병합 (데이터 깨짐 방지)
    combined = pd.concat([current_df.astype(str), new_df.astype(str)], ignore_index=True)
    
    try:
        conn.update(worksheet=worksheet, data=combined)
    except Exception as e:
        raise RuntimeError(f"시트 업데이트 중 오류 발생: {e}")

def append_user_row(student_id: str, name: str, plain_password: str) -> None:
    h = hash_student_password(student_id, plain_password)
    _append_rows_via_update(SHEET_USERS, USERS_COLS, [{"student_id": student_id, "name": name, "password_hash": h}])
    st.session_state.pop("_gs_users_df", None)

def append_history_from_record(record: dict[str, Any], ncs_score: float) -> None:
    row = {
        "datetime": record.get("submitted_at", ""),
        "student_id": record.get("student_id", ""),
        "name": record.get("student_display_name", ""),
        "subject": record.get("subject", ""),
        "unit": record.get("unit", ""),
        "diagnosis_result": record.get("result", ""),
        "ncs_score": str(round(float(ncs_score), 2)),
        "mode": record.get("mode", ""),
        "record_id": record.get("record_id", ""),
        "symptom": record.get("symptom", ""),
        "reasoning": record.get("reasoning", ""),
        "teacher_feedback": "",
        "teacher_feedback_updated_at": "",
        "reflection": record.get("reflection", ""),
        "image_b64": record.get("image_b64", ""),
    }
    _append_rows_via_update(SHEET_HISTORY, HISTORY_COLS, [row])
    st.session_state.pop("_gs_history_df", None)

# --- 나머지 헬퍼 함수들 (history_df_to_records 등)은 기존 로직 유지 ---
def read_history_df() -> pd.DataFrame:
    now = time.time()
    if st.session_state.get("_gs_history_df") is not None and now - st.session_state.get("_gs_history_ts", 0) < _CACHE_TTL_SEC:
        return st.session_state._gs_history_df
    conn = get_gsheets_connection()
    try:
        df = conn.read(worksheet=SHEET_HISTORY, ttl=0)
    except:
        df = pd.DataFrame(columns=HISTORY_COLS)
    df = _normalize_df(df, HISTORY_COLS)
    st.session_state._gs_history_df = df
    st.session_state._gs_history_ts = now
    return df

def history_df_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df is None or df.empty: return []
    return df.to_dict('records')

def invalidate_all_sheet_caches() -> None:
    st.session_state.pop("_gs_users_df", None)
    st.session_state.pop("_gs_history_df", None)

def update_teacher_feedback_in_sheet(record_id: str, feedback: str, updated_at: str) -> None:
    conn = _ensure_private_mode_for_write()
    df = conn.read(worksheet=SHEET_HISTORY, ttl=0)
    df = _normalize_df(df, HISTORY_COLS)
    mask = df["record_id"].astype(str) == str(record_id)
    if mask.any():
        df.loc[mask, "teacher_feedback"] = feedback
        df.loc[mask, "teacher_feedback_updated_at"] = updated_at
        conn.update(worksheet=SHEET_HISTORY, data=df)
        st.session_state.pop("_gs_history_df", None)