"""
Google Sheets 연동 (streamlit_gsheets.GSheetsConnection + gspread append).
시트 탭 이름: users, history — 스프레드시트는 st.secrets [connections.gsheets] spreadsheet 에 설정.
비밀번호는 시트에 평문으로 저장하지 않고 SHA-256 해시(password_hash 열)만 저장한다.
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
    GSheetsConnection = None  # type: ignore[misc, assignment]

SHEET_USERS = "users"
SHEET_HISTORY = "history"

USERS_COLS = ["student_id", "name", "password_hash"]
HISTORY_COLS = [
    "datetime",
    "student_id",
    "name",
    "subject",
    "unit",
    "diagnosis_result",
    "ncs_score",
    "mode",
    "record_id",
    "symptom",
    "reasoning",
    "teacher_feedback",
    "teacher_feedback_updated_at",
]

_CACHE_TTL_SEC = 90.0


def _pepper() -> str:
    try:
        p = st.secrets.get("GSHEETS_PASSWORD_PEPPER")
        if p:
            return str(p)
    except Exception:
        pass
    return "dev-only-pepper-change-in-secrets"


def hash_student_password(student_id: str, plain_password: str) -> str:
    raw = f"{_pepper()}|{student_id}|{plain_password}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_sha256_hex(s: str) -> bool:
    s = (s or "").strip()
    if len(s) != 64:
        return False
    try:
        int(s, 16)
        return True
    except ValueError:
        return False


def verify_student_password(student_id: str, plain_password: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False
    stored_hash = str(stored_hash).strip()
    if _is_sha256_hex(stored_hash):
        return hash_student_password(student_id, plain_password) == stored_hash.lower()
    return plain_password == stored_hash


def gsheets_available() -> bool:
    return GSheetsConnection is not None


def get_gsheets_connection() -> Any:
    if not gsheets_available():
        raise RuntimeError("st-gsheets-connection 미설치: pip install st-gsheets-connection")
    return st.connection("gsheets", type=GSheetsConnection)


def _invalidate_users_cache() -> None:
    st.session_state.pop("_gs_users_df", None)
    st.session_state.pop("_gs_users_ts", None)


def _invalidate_history_cache() -> None:
    st.session_state.pop("_gs_history_df", None)
    st.session_state.pop("_gs_history_ts", None)


def invalidate_all_sheet_caches() -> None:
    _invalidate_users_cache()
    _invalidate_history_cache()


def read_users_df() -> pd.DataFrame:
    now = time.time()
    ts = float(st.session_state.get("_gs_users_ts") or 0.0)
    if st.session_state.get("_gs_users_df") is not None and now - ts < _CACHE_TTL_SEC:
        return st.session_state._gs_users_df
    conn = get_gsheets_connection()
    try:
        df = conn.read(worksheet=SHEET_USERS, ttl=0)
    except Exception:
        df = pd.DataFrame(columns=USERS_COLS)
    if df is None or df.empty:
        df = pd.DataFrame(columns=USERS_COLS)
    else:
        df = df.rename(columns={c: c.strip() for c in df.columns})
        for c in USERS_COLS:
            if c not in df.columns:
                df[c] = ""
    st.session_state._gs_users_df = df
    st.session_state._gs_users_ts = now
    return df


def read_history_df() -> pd.DataFrame:
    now = time.time()
    ts = float(st.session_state.get("_gs_history_ts") or 0.0)
    if st.session_state.get("_gs_history_df") is not None and now - ts < _CACHE_TTL_SEC:
        return st.session_state._gs_history_df
    conn = get_gsheets_connection()
    try:
        df = conn.read(worksheet=SHEET_HISTORY, ttl=0)
    except Exception:
        df = pd.DataFrame(columns=HISTORY_COLS)
    if df is None or df.empty:
        df = pd.DataFrame(columns=HISTORY_COLS)
    else:
        df = df.rename(columns={c: c.strip() for c in df.columns})
        for c in HISTORY_COLS:
            if c not in df.columns:
                df[c] = ""
    st.session_state._gs_history_df = df
    st.session_state._gs_history_ts = now
    return df


def get_user_row(student_id: str) -> Optional[dict[str, Any]]:
    sid = (student_id or "").strip()
    if not sid:
        return None
    df = read_users_df()
    if df.empty or "student_id" not in df.columns:
        return None
    m = df[df["student_id"].astype(str).str.strip() == sid]
    if m.empty:
        return None
    row = m.iloc[0]
    return {
        "student_id": str(row.get("student_id", "")).strip(),
        "name": str(row.get("name", "")).strip(),
        "password_hash": str(row.get("password_hash", "")).strip(),
    }


def append_user_row(student_id: str, name: str, plain_password: str) -> None:
    conn = get_gsheets_connection()
    h = hash_student_password(student_id, plain_password)
    sh = conn.client._open_spreadsheet()  # type: ignore[attr-defined]
    ws = sh.worksheet(SHEET_USERS)
    rows = ws.get_all_values()
    if not rows:
        ws.append_row(USERS_COLS)
    ws.append_row([student_id, name, h])
    _invalidate_users_cache()


def _append_history_row_values(values: list[Any]) -> None:
    conn = get_gsheets_connection()
    sh = conn.client._open_spreadsheet()  # type: ignore[attr-defined]
    ws = sh.worksheet(SHEET_HISTORY)
    rows = ws.get_all_values()
    if not rows:
        ws.append_row(HISTORY_COLS)
    ws.append_row(values)
    _invalidate_history_cache()


def append_history_from_record(record: dict[str, Any], ncs_score: float) -> None:
    values = [
        record.get("submitted_at") or "",
        record.get("student_id") or "",
        record.get("student_display_name") or record.get("student_id") or "",
        record.get("subject") or "",
        record.get("unit") or "",
        record.get("result") or "",
        round(float(ncs_score), 2),
        record.get("mode") or "",
        record.get("record_id") or "",
        record.get("symptom") or "",
        record.get("reasoning") or "",
        record.get("teacher_feedback") or "",
        record.get("teacher_feedback_updated_at") or "",
    ]
    _append_history_row_values(values)


def _cell_str(row: pd.Series, key: str) -> str:
    if key not in row.index:
        return ""
    v = row[key]
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    return str(v) if v is not None else ""


def history_df_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if df is None or df.empty:
        return out
    for _, row in df.iterrows():
        out.append(
            {
                "record_id": _cell_str(row, "record_id"),
                "submitted_at": _cell_str(row, "datetime"),
                "student_id": _cell_str(row, "student_id"),
                "student_display_name": _cell_str(row, "name"),
                "subject": _cell_str(row, "subject"),
                "unit": _cell_str(row, "unit"),
                "mode": _cell_str(row, "mode"),
                "symptom": _cell_str(row, "symptom"),
                "reasoning": _cell_str(row, "reasoning"),
                "result": _cell_str(row, "diagnosis_result"),
                "teacher_feedback": _cell_str(row, "teacher_feedback"),
                "teacher_feedback_updated_at": _cell_str(row, "teacher_feedback_updated_at"),
            }
        )
    return out


def update_teacher_feedback_in_sheet(record_id: str, feedback: str, updated_at: str) -> None:
    if not record_id:
        return
    conn = get_gsheets_connection()
    df = conn.read(worksheet=SHEET_HISTORY, ttl=0)
    if df is None or df.empty:
        return
    df = df.rename(columns={c: c.strip() for c in df.columns})
    for c in HISTORY_COLS:
        if c not in df.columns:
            df[c] = ""
    if "record_id" not in df.columns:
        return
    mask = df["record_id"].astype(str) == str(record_id)
    if not mask.any():
        return
    df.loc[mask, "teacher_feedback"] = feedback
    df.loc[mask, "teacher_feedback_updated_at"] = updated_at
    conn.update(worksheet=SHEET_HISTORY, data=df)
    _invalidate_history_cache()


def clear_history_worksheet() -> None:
    conn = get_gsheets_connection()
    conn.clear(worksheet=SHEET_HISTORY)
    _invalidate_history_cache()


def maybe_upgrade_plaintext_password(student_id: str, plain_password: str, stored: str) -> None:
    """시트에 평문 비밀번호가 남아 있으면 해시로 교체한다."""
    stored = (stored or "").strip()
    if _is_sha256_hex(stored):
        return
    conn = get_gsheets_connection()
    df = conn.read(worksheet=SHEET_USERS, ttl=0)
    if df is None or df.empty:
        return
    df = df.rename(columns={c: c.strip() for c in df.columns})
    mask = df["student_id"].astype(str).str.strip() == str(student_id).strip()
    if not mask.any():
        return
    df.loc[mask, "password_hash"] = hash_student_password(student_id, plain_password)
    conn.update(worksheet=SHEET_USERS, data=df)
    _invalidate_users_cache()
