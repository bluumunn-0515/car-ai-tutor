"""
Google Sheets 연동 (streamlit_gsheets.GSheetsConnection 공식 API 기반).

- 시트 탭 이름: users, history
- 스프레드시트는 st.secrets [connections.gsheets] 의 spreadsheet 값으로 지정
- 읽기: conn.read(worksheet=...)
- 쓰기: conn.update(worksheet=..., data=DataFrame) (행 추가는 read → concat → update 패턴)
- 서비스 계정(Private) 모드에서만 쓰기가 허용된다. Public(읽기 전용) 모드에서는 명확한 에러를 발생시킨다.
- 비밀번호는 시트에 평문으로 저장하지 않고 SHA-256 해시(password_hash 열)만 저장한다.
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


# ---------------------------------------------------------------------------
# 비밀번호 해시 유틸
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Connection (공식 API)
# ---------------------------------------------------------------------------
def gsheets_available() -> bool:
    return GSheetsConnection is not None


def _gsheets_secrets_dict() -> dict[str, Any]:
    try:
        raw = st.secrets["connections"]["gsheets"]
    except Exception as exc:
        raise RuntimeError(
            "secrets.toml 에 [connections.gsheets] 설정이 없습니다. "
            "spreadsheet URL과 서비스 계정 정보를 채워 주세요."
        ) from exc
    try:
        return dict(raw)
    except Exception:
        return {k: raw[k] for k in raw}  # type: ignore[index]


def get_gsheets_connection() -> Any:
    """st.connection('gsheets', type=GSheetsConnection) 래퍼."""
    if not gsheets_available():
        raise RuntimeError(
            "st-gsheets-connection 미설치입니다. `pip install st-gsheets-connection` 후 다시 시도해 주세요."
        )
    return st.connection("gsheets", type=GSheetsConnection)


def _is_private_connection(conn: Any) -> bool:
    """현재 connection 이 서비스 계정(Private) 클라이언트를 사용 중인지 판단."""
    client = getattr(conn, "client", None)
    if client is None:
        return False
    class_name = type(client).__name__
    if "Public" in class_name:
        return False
    if "Service" in class_name or "Private" in class_name:
        return True
    return hasattr(client, "_open_spreadsheet") or hasattr(client, "open_spreadsheet")


def _ensure_private_mode_for_write() -> Any:
    """쓰기 직전에 서비스 계정(Private) 모드로 연결되어 있는지 확인한다.

    - secrets 에 `type = "service_account"` 와 `private_key`, `client_email` 이 모두 설정되어 있어야 함.
    - connection.client 가 Public 클라이언트면 에러.
    """
    secrets = _gsheets_secrets_dict()
    if not str(secrets.get("spreadsheet") or "").strip():
        raise RuntimeError(
            "secrets.toml [connections.gsheets] 에 spreadsheet (스프레드시트 URL) 값이 없습니다."
        )
    if str(secrets.get("type") or "").strip() != "service_account":
        raise RuntimeError(
            "Google Sheets 쓰기는 Private(서비스 계정) 모드에서만 가능합니다. "
            "`.streamlit/secrets.toml` 의 [connections.gsheets] 에 `type = \"service_account\"` 를 지정해 주세요."
        )
    missing = [k for k in ("private_key", "client_email") if not str(secrets.get(k) or "").strip()]
    if missing:
        raise RuntimeError(
            "서비스 계정 자격 증명이 불완전합니다: " + ", ".join(missing) + ". "
            "secrets.toml 의 서비스 계정 JSON 필드를 모두 채워 주세요."
        )

    conn = get_gsheets_connection()
    if not _is_private_connection(conn):
        raise RuntimeError(
            "현재 연결이 Public(읽기 전용) 모드로 초기화되었습니다. "
            "secrets.toml [connections.gsheets] 의 서비스 계정 정보(type, private_key, client_email 등)를 "
            "올바르게 채우고 Streamlit 을 재시작해 주세요."
        )
    return conn


# ---------------------------------------------------------------------------
# 캐시 관리
# ---------------------------------------------------------------------------
def _invalidate_users_cache() -> None:
    st.session_state.pop("_gs_users_df", None)
    st.session_state.pop("_gs_users_ts", None)


def _invalidate_history_cache() -> None:
    st.session_state.pop("_gs_history_df", None)
    st.session_state.pop("_gs_history_ts", None)


def invalidate_all_sheet_caches() -> None:
    _invalidate_users_cache()
    _invalidate_history_cache()


# ---------------------------------------------------------------------------
# 읽기 (conn.read)
# ---------------------------------------------------------------------------
def _normalize_df(df: Optional[pd.DataFrame], cols: list[str]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=cols)
    df = df.rename(columns={c: str(c).strip() for c in df.columns})
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df


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
    df = _normalize_df(df, USERS_COLS)
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
    df = _normalize_df(df, HISTORY_COLS)
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


# ---------------------------------------------------------------------------
# 쓰기 (conn.update — read → concat → update 패턴)
# ---------------------------------------------------------------------------
def _read_fresh_df(conn: Any, worksheet: str, cols: list[str]) -> pd.DataFrame:
    try:
        df = conn.read(worksheet=worksheet, ttl=0)
    except Exception:
        df = pd.DataFrame(columns=cols)
    df = _normalize_df(df, cols)
    try:
        df = df[cols]
    except Exception:
        pass
    return df


def _append_rows_via_update(worksheet: str, cols: list[str], new_rows: list[dict[str, Any]]) -> None:
    """conn.update() 만 사용해 지정한 워크시트 끝에 행을 추가한다.

    - st-gsheets-connection 의 공식 쓰기 API 는 `conn.update(worksheet=..., data=df)` 이며
      전체 시트를 DataFrame 으로 덮어쓴다. 따라서 안전한 append 를 위해
      최신 시트를 다시 읽고 새 행을 이어 붙인 뒤 전체를 다시 업데이트한다.
    """
    if not new_rows:
        return
    conn = _ensure_private_mode_for_write()
    current = _read_fresh_df(conn, worksheet, cols)
    additions = pd.DataFrame(new_rows, columns=cols).astype(str)
    combined = pd.concat([current.astype(str), additions], ignore_index=True)
    try:
        conn.update(worksheet=worksheet, data=combined)
    except Exception as exc:
        raise RuntimeError(
            f"'{worksheet}' 워크시트 업데이트에 실패했습니다: {exc}. "
            "스프레드시트에 해당 탭이 존재하는지, 서비스 계정이 편집 권한으로 공유되었는지 확인해 주세요."
        ) from exc


def append_user_row(student_id: str, name: str, plain_password: str) -> None:
    h = hash_student_password(student_id, plain_password)
    _append_rows_via_update(
        SHEET_USERS,
        USERS_COLS,
        [{"student_id": student_id, "name": name, "password_hash": h}],
    )
    _invalidate_users_cache()


def append_history_from_record(record: dict[str, Any], ncs_score: float) -> None:
    row = {
        "datetime": record.get("submitted_at") or "",
        "student_id": record.get("student_id") or "",
        "name": record.get("student_display_name") or record.get("student_id") or "",
        "subject": record.get("subject") or "",
        "unit": record.get("unit") or "",
        "diagnosis_result": record.get("result") or "",
        "ncs_score": round(float(ncs_score), 2),
        "mode": record.get("mode") or "",
        "record_id": record.get("record_id") or "",
        "symptom": record.get("symptom") or "",
        "reasoning": record.get("reasoning") or "",
        "teacher_feedback": record.get("teacher_feedback") or "",
        "teacher_feedback_updated_at": record.get("teacher_feedback_updated_at") or "",
    }
    _append_rows_via_update(SHEET_HISTORY, HISTORY_COLS, [row])
    _invalidate_history_cache()


# ---------------------------------------------------------------------------
# History → records 변환 / 교사 피드백 업데이트 / 시트 초기화
# ---------------------------------------------------------------------------
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
    conn = _ensure_private_mode_for_write()
    df = _read_fresh_df(conn, SHEET_HISTORY, HISTORY_COLS)
    if df.empty or "record_id" not in df.columns:
        return
    mask = df["record_id"].astype(str) == str(record_id)
    if not mask.any():
        return
    df.loc[mask, "teacher_feedback"] = feedback
    df.loc[mask, "teacher_feedback_updated_at"] = updated_at
    try:
        conn.update(worksheet=SHEET_HISTORY, data=df)
    except Exception as exc:
        raise RuntimeError(f"'{SHEET_HISTORY}' 워크시트 업데이트에 실패했습니다: {exc}") from exc
    _invalidate_history_cache()


def clear_history_worksheet() -> None:
    conn = _ensure_private_mode_for_write()
    try:
        conn.clear(worksheet=SHEET_HISTORY)
    except Exception:
        empty = pd.DataFrame(columns=HISTORY_COLS)
        conn.update(worksheet=SHEET_HISTORY, data=empty)
    _invalidate_history_cache()


def maybe_upgrade_plaintext_password(student_id: str, plain_password: str, stored: str) -> None:
    """시트에 평문 비밀번호가 남아 있으면 해시로 교체한다."""
    stored = (stored or "").strip()
    if _is_sha256_hex(stored):
        return
    try:
        conn = _ensure_private_mode_for_write()
    except Exception:
        return
    df = _read_fresh_df(conn, SHEET_USERS, USERS_COLS)
    if df.empty or "student_id" not in df.columns:
        return
    mask = df["student_id"].astype(str).str.strip() == str(student_id).strip()
    if not mask.any():
        return
    df.loc[mask, "password_hash"] = hash_student_password(student_id, plain_password)
    try:
        conn.update(worksheet=SHEET_USERS, data=df)
    except Exception:
        return
    _invalidate_users_cache()
