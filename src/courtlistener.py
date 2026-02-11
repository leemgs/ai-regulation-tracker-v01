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


# =====================================================
# 🔥 데이터 클래스 (court_short_name 추가)
# =====================================================
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
# 🔥 Court short_name 수집 (역할 분리 핵심)
# =====================================================
def fetch_court_metadata(court_id: str) -> tuple[str, str]:
    """
    court_id 예: flsd
    반환: (short_name, api_url)
    """
    if not court_id:
        return "미확인", ""

    url = COURT_URL.format(id=court_id)
    try:
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            return court_id, url
        data = r.json()
        short_name = data.get("short_name") or court_id
        return short_name, url
    except Exception:
        return court_id, url


# =====================================================
# 🔥 build_case_summary 수정 (court short_name 저장)
# =====================================================
def build_case_summary_from_docket_id(docket_id: int) -> Optional[CLCaseSummary]:
    docket = requests.get(DOCKET_URL.format(id=docket_id)).json()

    case_name = docket.get("case_name") or "미확인"
    docket_number = docket.get("docket_number") or "미확인"
    court_id = docket.get("court") or docket.get("court_id") or ""

    court_short_name, court_api_url = fetch_court_metadata(court_id)

    return CLCaseSummary(
        docket_id=docket_id,
        case_name=case_name,
        docket_number=docket_number,
        court=court_id,
        court_short_name=court_short_name,
        court_api_url=court_api_url,
        date_filed=(docket.get("date_filed") or "")[:10] or "미확인",
        status="진행중/미확인",
        judge=docket.get("assigned_to_str") or "미확인",
        magistrate=docket.get("referred_to_str") or "미확인",
        nature_of_suit=docket.get("nature_of_suit") or "미확인",
        cause=docket.get("cause") or "미확인",
        parties="미확인",
        complaint_doc_no="미확인",
        complaint_link="",
        recent_updates="미확인",
        extracted_causes="미확인",
        extracted_ai_snippet="",
    )
