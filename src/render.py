from __future__ import annotations
from typing import List
from .extract import Lawsuit
from .courtlistener import CLDocument

def render_markdown(lawsuits: List[Lawsuit], cl_docs: List[CLDocument]) -> str:
    lines: List[str] = []
    lines.append("## 최근 3일: AI 학습용 무단/불법 데이터 사용 관련 소송/업데이트\n")

    if lawsuits:
        lines.append("### 요약 테이블 (뉴스/RSS 기반 정규화)")
        lines.append("| 소송/업데이트 일자 | 소송제목 | 소송번호 | 소송이유 | 원고 | 피고 | 국가 | 법원명 | 히스토리 |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for s in lawsuits:
            lines.append(
                f"| {s.update_or_filed_date} | {s.case_title} | {s.case_number} | {s.reason} | {s.plaintiff} | {s.defendant} | {s.country} | {s.court} | {s.history} |"
            )
    else:
        lines.append("정규화된 소송 테이블을 생성하지 못했습니다(뉴스/문서에서 필요한 필드가 부족할 수 있음).")

    lines.append("\n---\n")

    if cl_docs:
        lines.append("### RECAP 문서 기반 (Complaint/Petition 우선, **정밀 추출**)")
        lines.append("| 문서 제출일 | 케이스명 | 도켓번호 | 법원 | 문서유형 | 원고(추출) | 피고(추출) | 청구원인(추출) | AI학습 관련 핵심문장(추출) | 문서 링크 |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for d in sorted(cl_docs, key=lambda x: x.date_filed, reverse=True)[:20]:
            link = d.document_url or d.pdf_url
            ai = (d.extracted_ai_snippet or "").replace("|", "\|")
            causes = (d.extracted_causes or "미확인").replace("|", "\|")
            p = (d.extracted_plaintiff or "미확인").replace("|", "\|")
            df = (d.extracted_defendant or "미확인").replace("|", "\|")
            lines.append(
                f"| {d.date_filed} | {d.case_name} | {d.docket_number} | {d.court} | {d.doc_type} | {p} | {df} | {causes} | {ai} | {link} |"
            )
        lines.append("\n")

    lines.append("## 기사 주소\n")
    if lawsuits:
        for s in lawsuits:
            lines.append(f"### {s.case_title} ({s.case_number})")
            for u in s.article_urls:
                lines.append(f"- {u}")
            lines.append("")
    else:
        lines.append("- (기사 주소 출력 실패)")

    return "\n".join(lines)
