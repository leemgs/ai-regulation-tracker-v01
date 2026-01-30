from __future__ import annotations
import requests
from typing import Dict

def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

def find_or_create_issue(owner: str, repo: str, token: str, title: str, label: str) -> int:
    url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    r = requests.get(url, headers=_headers(token), params={"state": "open", "labels": label, "per_page": 50}, timeout=20)
    r.raise_for_status()
    issues = r.json()
    for it in issues:
        if it.get("title") == title:
            return int(it["number"])

    payload = {"title": title, "body": "자동 수집 리포트가 댓글로 누적됩니다.", "labels": [label]}
    r2 = requests.post(url, headers=_headers(token), json=payload, timeout=20)
    r2.raise_for_status()
    return int(r2.json()["number"])

def create_comment(owner: str, repo: str, token: str, issue_number: int, body: str) -> None:
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/comments"
    r = requests.post(url, headers=_headers(token), json={"body": body}, timeout=20)
    r.raise_for_status()
