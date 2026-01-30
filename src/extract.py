from __future__ import annotations
import re
import requests
import yaml
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List, Dict, Any
from datetime import datetime, timezone

CASE_NO_PATTERNS = [
    re.compile(r"\b\d:\d{2}-cv-\d{5}\b", re.IGNORECASE),
    re.compile(r"\b\d{1,2}:\d{2}-cv-\d{5}\b", re.IGNORECASE),
    re.compile(r"\b\d{4}-cv-\d{4,6}\b", re.IGNORECASE),
]

@dataclass
class Lawsuit:
    update_or_filed_date: str
    case_title: str
    case_number: str
    reason: str
    plaintiff: str
    defendant: str
    country: str
    court: str
    history: str
    article_urls: List[str]

def fetch_page_text(url: str, timeout: int = 15) -> str:
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text("\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:20000]
    except Exception:
        return ""

def load_known_cases(path: str = "data/known_cases.yml") -> List[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or []
    except FileNotFoundError:
        return []

def enrich_from_known(text: str, title: str, known: List[Dict[str, Any]]) -> Dict[str, str]:
    hay = (title + "\n" + text).lower()
    for entry in known:
        any_terms = [t.lower() for t in entry.get("match", {}).get("any", [])]
        if any_terms and any(term in hay for term in any_terms):
            return entry.get("enrich", {}) or {}
    return {}

def extract_case_number(text: str) -> str:
    for pat in CASE_NO_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(0)
    return "미확인"

def extract_parties_simple(text: str) -> tuple[str, str]:
    m = re.search(r"([A-Z][A-Za-z0-9 ,.&'\-]{2,})\s+v\.?\s+([A-Z][A-Za-z0-9 ,.&'\-]{2,})", text)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "미확인", "미확인"

def reason_heuristic(hay: str) -> str:
    h = hay.lower()
    if "shadow library" in h or "pirat" in h:
        return "불법 유통본/해적판 등으로 추정되는 데이터 활용 의혹에 따른 저작권 침해."
    if "youtube" in h and ("dmca" in h or "circumvent" in h or "technical protection" in h):
        return "유튜브 콘텐츠를 무단 수집해 AI 학습에 사용하고 기술적 보호조치를 우회했다는 취지(저작권/DMCA 등)."
    if "lyrics" in h or "music publisher" in h:
        return "저작권 보호 음악/가사 등을 무단으로 학습에 사용했다는 취지(음악 출판사/권리자 저작권 침해)."
    return "AI 모델 학습을 위해 허가되지 않은(무단/불법) 데이터 사용 의혹(저작권/DMCA/무단 수집 등)."

def build_lawsuits_from_news(news_items, known_cases) -> List[Lawsuit]:
    results: List[Lawsuit] = []
    for item in news_items:
        text = fetch_page_text(item.url)
        if not text:
            continue

        hay = (item.title + " " + text)
        lower = hay.lower()
        if not any(k in lower for k in ["lawsuit", "sued", "litigation", "copyright", "dmca", "pirat", "unauthoriz", "training data", "dataset"]):
            continue

        enrich = enrich_from_known(text, item.title, known_cases)

        case_number = enrich.get("case_number") or extract_case_number(text)
        case_title = enrich.get("case_title") or item.title

        pl, df = extract_parties_simple(case_title)
        plaintiff = enrich.get("plaintiff", pl)
        defendant = enrich.get("defendant", df)

        country = enrich.get("country", "미확인")
        court = enrich.get("court", "미확인")

        published = item.published_at or datetime.now(timezone.utc)
        update_date = published.date().isoformat()

        results.append(
            Lawsuit(
                update_or_filed_date=update_date,
                case_title=case_title,
                case_number=case_number,
                reason=enrich.get("reason", reason_heuristic(hay)),
                plaintiff=plaintiff,
                defendant=defendant,
                country=country,
                court=court,
                history="최근 3일 이내 기사/RSS 기반 자동 수집(소장/도켓 확인 전 일부 항목은 미확인 가능).",
                article_urls=[item.url],
            )
        )

    # 병합
    merged: Dict[str, Lawsuit] = {}
    for r in results:
        key = (r.case_number, r.case_title)
        if key not in merged:
            merged[key] = r
        else:
            merged[key].article_urls = sorted(list(set(merged[key].article_urls + r.article_urls)))
            if r.update_or_filed_date > merged[key].update_or_filed_date:
                merged[key].update_or_filed_date = r.update_or_filed_date

    return list(merged.values())
