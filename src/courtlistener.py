from __future__ import annotations

import os
import requests
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta

from .pdf_text import extract_pdf_text
from .complaint_parse import detect_causes, extract_ai_training_snippet, extract_parties_from_caption

BASE = "https://www.courtlistener.com"
SEARCH_URL = BASE + "/api/rest/v4/search/"
DOCKET_URL = BASE + "/api/rest/v4/dockets/{id}/"
RECAP_DOCS_URL = BASE + "/api/rest/v4/recap-documents/"
DOCKET_ENTRIES_URL = BASE + "/api/rest/v4/docket-entries/"

COMPLAINT_KEYWORDS = [
    "complaint",
    "amended complaint",
    "petition",
    "class action complaint",
]

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

def search_recent_documents(query: str, days: int = 3, max_results: int = 20) -> List[dict]:
    data = _get(SEARCH_URL, params={"q": query, "type": "r", "available_only": "on", "order_by": "entry_date_filed desc", "page_size": max_results})
    if not data:
        return []
    results = data.get("results", []) or []
    # 최근 3일 필터 (가능한 날짜 필드 활용)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    filtered = []
    for it in results:
        date_val = it.get("dateFiled") or it.get("date_filed") or it.get("dateCreated") or it.get("date_created")
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

def _pick_docket_id(hit: dict) -> Optional[int]:
    # search hit 구조는 케이스/도켓/문서에 따라 달라질 수 있어 최대한 유연하게 시도
    for key in ["docket_id", "docketId", "docket"]:
        v = hit.get(key)
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.isdigit():
            return int(v)
        if isinstance(v, dict) and "id" in v:
            try:
                return int(v["id"])
            except Exception:
                pass
    # 어떤 결과는 absolute_url이 docket을 가리킬 수 있음
    return None

def _safe_str(x) -> str:
    return (str(x).strip() if x is not None else "")

def fetch_docket(docket_id: int) -> Optional[dict]:
    return _get(DOCKET_URL.format(id=docket_id))

def list_recap_documents(docket_id: int, page_size: int = 50) -> List[dict]:
    data = _get(RECAP_DOCS_URL, params={"docket": docket_id, "page_size": page_size})
    if not data:
        return []
    return data.get("results", []) or []

def list_docket_entries(docket_id: int, page_size: int = 50) -> List[dict]:
    data = _get(DOCKET_ENTRIES_URL, params={"docket": docket_id, "page_size": page_size, "order_by": "-date_filed"})
    if not data:
        return []
    return data.get("results", []) or []

def _is_complaint(doc: dict) -> bool:
    hay = " ".join([_safe_str(doc.get("description")), _safe_str(doc.get("document_type"))]).lower()
    return any(k in hay for k in COMPLAINT_KEYWORDS)

def _extract_pdf_url(doc: dict) -> str:
    # CourtListener의 recap-documents 응답에서 PDF 링크 필드는 다양할 수 있어 후보를 넓게 둠
    for key in ["filepath_local", "filepathLocal", "download_url", "downloadUrl", "file", "pdf_url", "pdfUrl"]:
        v = doc.get(key)
        if isinstance(v, str) and v:
            return _abs_url(v)
    # 어떤 경우 document_url 자체가 PDF일 수 있음
    u = doc.get("absolute_url") or doc.get("url") or ""
    u = _abs_url(u)
    return u

def build_complaint_documents_from_hits(hits: List[dict], days: int = 3) -> List[CLDocument]:
    docs_out: List[CLDocument] = []
    for hit in hits:
        docket_id = _pick_docket_id(hit)
        if not docket_id:
            continue

        docket = fetch_docket(docket_id) or {}
        case_name = _safe_str(docket.get("case_name") or docket.get("caseName") or hit.get("caseName") or hit.get("title"))
        docket_number = _safe_str(docket.get("docket_number") or docket.get("docketNumber") or "")
        court = _safe_str(docket.get("court") or docket.get("court_id") or docket.get("courtId") or "")

        recap_docs = list_recap_documents(docket_id)
        if not recap_docs:
            continue

        # complaint 우선 + 없으면 최근 문서 1~2개라도 힌트로 남기기
        complaint_docs = [d for d in recap_docs if _is_complaint(d)]
        if not complaint_docs:
            complaint_docs = sorted(recap_docs, key=lambda x: _safe_str(x.get("date_filed") or x.get("dateFiled")), reverse=True)[:2]

        for d in complaint_docs[:3]:
            doc_type = _safe_str(d.get("document_type") or d.get("documentType") or "")
            doc_number = _safe_str(d.get("document_number") or d.get("documentNumber") or d.get("document_num") or "")
            desc = _safe_str(d.get("description") or "")
            date_filed = _safe_str(d.get("date_filed") or d.get("dateFiled") or "")[:10] or datetime.now(timezone.utc).date().isoformat()

            document_url = _abs_url(d.get("absolute_url") or d.get("absoluteUrl") or d.get("url") or "")
            pdf_url = _extract_pdf_url(d)

            snippet = ""
            # PDF가 실제 PDF URL처럼 보일 때만 텍스트 추출 시도
            if pdf_url and (pdf_url.lower().endswith(".pdf") or "pdf" in pdf_url.lower()):
                snippet = extract_pdf_text(pdf_url, max_chars=3500)

            # Complaint 텍스트 기반 정밀 추출(원고/피고/청구원인/AI학습 관련 핵심문장)
            p_ex, d_ex = extract_parties_from_caption(snippet) if snippet else ("미확인", "미확인")
            causes = detect_causes(snippet) if snippet else []
            ai_snip = extract_ai_training_snippet(snippet) if snippet else ""

            docs_out.append(CLDocument(
                docket_id=docket_id,
                docket_number=docket_number or "미확인",
                case_name=case_name or "미확인",
                court=court or "미확인",
                date_filed=date_filed,
                doc_type=doc_type or ("Complaint" if _is_complaint(d) else "Document"),
                doc_number=doc_number or "미확인",
                description=desc or "미확인",
                document_url=document_url or pdf_url or "",
                pdf_url=pdf_url or "",
                pdf_text_snippet=snippet,
                extracted_plaintiff=p_ex,
                extracted_defendant=d_ex,
                extracted_causes=", ".join(causes) if causes else "미확인",
                extracted_ai_snippet=ai_snip or "",
            ))
    # 중복 제거
    uniq = {}
    for x in docs_out:
        key = (x.docket_id, x.doc_number, x.date_filed, x.document_url)
        uniq[key] = x
    return list(uniq.values())
