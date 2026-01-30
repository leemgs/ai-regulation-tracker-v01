from __future__ import annotations
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .fetch import fetch_news
from .extract import load_known_cases, build_lawsuits_from_news
from .render import render_markdown
from .github_issue import find_or_create_issue, create_comment, close_other_daily_issues
from .slack import post_to_slack
from .courtlistener import search_recent_documents, build_complaint_documents_from_hits, build_case_summaries_from_hits
from .queries import COURTLISTENER_QUERIES

def main() -> None:
    # 0) 환경 변수 로드 (들여쓰기 수정)
    owner = os.environ["GITHUB_OWNER"]
    repo = os.environ["GITHUB_REPO"]
    gh_token = os.environ["GITHUB_TOKEN"]
    slack_webhook = os.environ["SLACK_WEBHOOK_URL"]

    base_title = os.environ.get("ISSUE_TITLE_BASE", "AI 불법/무단 학습데이터 소송 모니터링")
    
    # KST(Asia/Seoul) 기준 날짜 생성 (들여쓰기 수정)
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    run_ts_kst = now_kst.strftime("%Y-%m-%d %H:%M")
    issue_day_kst = now_kst.strftime("%Y-%m-%d")
    issue_title = f"{base_title} ({issue_day_kst})"
    print(f"KST 기준 실행시각: {run_ts_kst}")
    
    issue_label = os.environ.get("ISSUE_LABEL", "ai-lawsuit-monitor")

    # 1) CourtListener 검색 + RECAP Complaint 문서 수집
    hits = []
    for q in COURTLISTENER_QUERIES:
        hits.extend(search_recent_documents(q, days=3, max_results=20))
    
    # 중복 완화
    dedup = {}
    for h in hits:
        key = (h.get("absolute_url") or h.get("url") or "") + "|" + (h.get("caseName") or h.get("title") or "")
        dedup[key] = h
    hits = list(dedup.values())

    cl_docs = build_complaint_documents_from_hits(hits, days=3)

    # 2) 뉴스 수집(보강)
    news = fetch_news()
    known = load_known_cases()
    lawsuits = build_lawsuits_from_news(news, known)

    # 3) 렌더링
    cl_cases = build_case_summaries_from_hits(hits)

    md = render_markdown(lawsuits, cl_docs, cl_cases)
    md = f"### 실행 시각(KST): {run_ts_kst}\n\n" + md
    
    print("===== REPORT BEGIN =====")
    print(md[:8000])
    print("===== REPORT END =====")

    # 4) GitHub Issue 댓글 업로드
    # token 변수명 gh_token으로 통일 및 들여쓰기 수정
    issue_no = find_or_create_issue(owner, repo, gh_token, issue_title, issue_label)
    issue_url = f"https://github.com/{owner}/{repo}/issues/{issue_no}"
    
    closed_nums = close_other_daily_issues(owner, repo, gh_token, issue_label, base_title, issue_title, issue_no, issue_url)
    
    if closed_nums:
        print(f"이전 날짜 이슈 자동 Close: {closed_nums}")
    
    print(f"Issue #{issue_no} 준비 완료")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    comment_body = f"### 실행 결과 ({timestamp})\n\n{md}"
    create_comment(owner, repo, gh_token, issue_no, comment_body)
    print("GitHub Issue 댓글 업로드 완료")

    # 5) Slack 요약
    # cl_docs 데이터 구조에 따른 변수 할당 (기존 코드에서 정의되지 않은 변수 참조 수정)
    # build_complaint_documents_from_hits가 반환하는 리스트 형태에 맞춰 조정이 필요합니다.
    summary_lines = [
        f"*AI 소송 모니터링 업데이트* ({timestamp})",
        f"- 뉴스 보강 건수: {len(lawsuits)}건",
        f"- 수집된 법원 문서 건수: {len(cl_docs)}건",
        f"- GitHub Issue: #{issue_no}",
    ]
    
    if cl_docs:
        # date_filed 속성이 있다고 가정 (cl_docs 객체 설계에 따름)
        top = sorted(cl_docs, key=lambda x: getattr(x, 'date_filed', ''), reverse=True)[:3]
        summary_lines.append("- 최신 RECAP 문서:")
        for d in top:
            # 객체 속성 접근 방식 확인 필요 (d.date_filed 또는 d['date_filed'])
            summary_lines.append(f"  • {getattr(d, 'date_filed', 'N/A')} | {getattr(d, 'case_name', 'Unknown Case')}")
    
    post_to_slack(slack_webhook, "\n".join(summary_lines))
    print("Slack 전송 완료")

if __name__ == "__main__":
    main()
