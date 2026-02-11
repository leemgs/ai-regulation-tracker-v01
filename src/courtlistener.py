from __future__ import annotations

import os
import re
import requests
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta

from .pdf_text import extract_pdf_text
from .complaint_parse import detect_causes, extract_ai_training_snippet, extract_parties_from_caption

BASE = "https://www.courtlistener.com"
SEARCH_URL = BASE + "/api/rest/v4/search/"
DOCKET_URL = BASE + "/api/rest/v4/dockets/{id}/"
COURT_URL = BASE + "/api/rest/v4/courts/{id}/"
DOCKETS_LIST_URL = BASE + "/api/rest/v4/dockets/"
RECAP_DOCS_URL = BASE + "/api/rest/v4/recap-documents/"
PARTIES_URL = BASE + "/api/rest/v4/parties/"
DOCKET_ENTRIES_URL = BASE + "/api/rest/v4/docket-entries/"

COMPLAINT_KEYWORDS = [
    "complaint",
    "amended complaint",
    "petition",
    "class action complaint",
]

# =====================================================
# 데이터 클래스
# =====================================================

@dataclass
class CLDocument:
    docket_id: Optional[int]
    docket_number: str
    case_name: str
    court: str
    date_filed: str
    doc_type: str
    doc_number: str
    description: str
    document_url: str
    pdf_url: str
    pdf_text_snippet: str
    extracted_plaintiff: str
    extracted_defendant: str
    extracted_causes: str
    extracted_ai_snippet: str


@dataclass
class CLCaseSummary:
    docket_id: int
    case_name: str
    docket_number: str
    court: str
    court_short_name: str
    court_api_url: str
    date_filed: str
    status: str
    judge: str
    magistrate: str
    nature_of_suit: str
    cause: str
    parties: str
    complaint_doc_no: str
    complaint_link: str
    recent_updates: str
    extracted_causes: str
    extracted_ai_snippet: str
    docket_candidates: str = ""


# =====================================================
# 내부 유틸
# =====================================================

def _headers() -> Dict[str, str]:
    token = os.getenv("COURTLISTENER_TOKEN", "").strip()
    headers = {
        "Accept": "application/json",
        "User-Agent": "ai-lawsuit-monitor/1.1",
    }
    if token:
        headers["Authorization"] = f"Token {token}"
    return headers


def _get(url: str, params: Optional[dict] = None) -> Optional[dict]:
    try:
        r = requests.get(url, params=params, headers=_headers(), timeout=25)
        if r.status_code in (401, 403):
            return None
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _abs_url(u: str) -> str:
    if not u:
        return ""
    if u.startswith("http"):
        return u
    if u.startswith("/"):
        return BASE + u
    return u


def _safe_str(x) -> str:
    return str(x).strip() if x is not None else ""


# =====================================================
# Court 메타데이터 수집
# =====================================================

def fetch_court_metadata(court_id: str) -> tuple[str, str]:
    if not court_id:
        return "미확인", ""
    data = _get(COURT_URL.format(id=court_id))
    if not data:
        return court_id, COURT_URL.format(id=court_id)
    short_name = data.get("short_name") or court_id
    return short_name, COURT_URL.format(id=court_id)


# =====================================================
# Docket / Search
# =====================================================

def fetch_docket(docket_id: int) -> Optional[dict]:
    return _get(DOCKET_URL.format(id=docket_id))


def search_recent_documents(query: str, days: int = 3, max_results: int = 20) -> List[dict]:
    data = _get(
        SEARCH_URL,
        params={
            "q": query,
            "type": "r",
            "available_only": "on",
            "order_by": "entry_date_filed desc",
            "page_size": max_results,
        },
    )
    if not data:
        return []

    results = data.get("results", []) or []
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    filtered = []
    for it in results:
        date_val = (
            it.get("dateFiled")
            or it.get("date_filed")
            or it.get("dateCreated")
            or it.get("date_created")
        )
        if date_val:
            try:
                iso = str(date_val)[:10]
                dt = datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)
                if dt < cutoff:
                    continue
            except Exception:
                pass
        filtered.append(it)
    return filtered


# =====================================================
# Case Summary (🔥 확장 완료)
# =====================================================

def _status_from_docket(docket: dict) -> str:
    term = _safe_str(docket.get("date_terminated") or docket.get("dateTerminated"))
    if term:
        return f"종결({term[:10]})"
    return "진행중/미확인"


def build_case_summary_from_docket_id(docket_id: int) -> Optional[CLCaseSummary]:
    if not docket_id:
        return None

    docket = fetch_docket(int(docket_id)) or {}

    case_name = _safe_str(docket.get("case_name") or docket.get("caseName")) or "미확인"
    docket_number = _safe_str(docket.get("docket_number") or docket.get("docketNumber")) or "미확인"

    court_id = _safe_str(
        docket.get("court") or docket.get("court_id") or docket.get("courtId")
    ) or "미확인"

    court_short_name, court_api_url = fetch_court_metadata(court_id)

    date_filed = _safe_str(docket.get("date_filed") or docket.get("dateFiled"))[:10] or "미확인"
    status = _status_from_docket(docket)

    judge = _safe_str(
        docket.get("assigned_to_str")
        or docket.get("assignedToStr")
        or docket.get("assigned_to")
        or docket.get("assignedTo")
    ) or "미확인"

    magistrate = _safe_str(
        docket.get("referred_to_str")
        or docket.get("referredToStr")
        or docket.get("referred_to")
        or docket.get("referredTo")
    ) or "미확인"

    nature_of_suit = _safe_str(docket.get("nature_of_suit") or docket.get("natureOfSuit")) or "미확인"
    cause = _safe_str(docket.get("cause")) or "미확인"

    return CLCaseSummary(
        docket_id=int(docket_id),
        case_name=case_name,
        docket_number=docket_number,
        court=court_id,
        court_short_name=court_short_name,
        court_api_url=court_api_url,
        date_filed=date_filed,
        status=status,
        judge=judge,
        magistrate=magistrate,
        nature_of_suit=nature_of_suit,
        cause=cause,
        parties="미확인",
        complaint_doc_no="미확인",
        complaint_link="",
        recent_updates="미확인",
        extracted_causes="미확인",
        extracted_ai_snippet="",
    )
