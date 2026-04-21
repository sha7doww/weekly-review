#!/usr/bin/env python3
"""Collect GitHub activity for the configured user within a date range.

Uses `gh` CLI (must be authenticated). Gathers:
  - PRs authored by the user (via search API, type ISSUE covers PRs + issues)
  - Issues authored by the user
  - Recent events (pushes, releases, comments) within the window
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from _common import (
    add_range_args,
    load_config,
    parse_ts_utc,
    print_range,
    range_to_utc,
    resolve_range,
    write_json,
)


def run_gh(args: list[str], input_text: Optional[str] = None) -> dict:
    try:
        result = subprocess.run(
            ["gh", *args],
            input=input_text,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        print("[error] `gh` CLI not found in PATH", file=sys.stderr)
        sys.exit(2)
    except subprocess.CalledProcessError as e:
        print(f"[error] gh {' '.join(args)} failed: {e.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    if not result.stdout.strip():
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"[error] gh returned non-JSON: {e}\n{result.stdout[:300]}", file=sys.stderr)
        sys.exit(2)


GRAPHQL_SEARCH = """
query($q: String!, $after: String) {
  search(first: 100, type: ISSUE, query: $q, after: $after) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes {
      __typename
      ... on PullRequest {
        number
        title
        url
        state
        isDraft
        merged
        mergedAt
        createdAt
        closedAt
        additions
        deletions
        changedFiles
        repository { nameWithOwner isPrivate }
        commits(first: 1) { totalCount }
        body
      }
      ... on Issue {
        number
        title
        url
        state
        createdAt
        closedAt
        repository { nameWithOwner isPrivate }
        body
      }
    }
  }
}
"""


def search_issues(query: str) -> list[dict]:
    """Paginate through search results."""
    nodes: list[dict] = []
    after: Optional[str] = None
    while True:
        args = [
            "api", "graphql",
            "-f", f"query={GRAPHQL_SEARCH}",
            "-f", f"q={query}",
        ]
        if after:
            args.extend(["-f", f"after={after}"])
        else:
            args.extend(["-F", "after=null"])
        data = run_gh(args)
        search = (data.get("data") or {}).get("search") or {}
        nodes.extend(search.get("nodes") or [])
        info = search.get("pageInfo") or {}
        if not info.get("hasNextPage") or len(nodes) >= 1000:
            break
        after = info.get("endCursor")
    return nodes


def fetch_events(username: str, start_utc: datetime, end_utc: datetime) -> list[dict]:
    """Fetch recent events; GitHub exposes up to ~300 events / 90 days."""
    events: list[dict] = []
    page = 1
    while page <= 10:
        try:
            result = subprocess.run(
                ["gh", "api", f"/users/{username}/events?per_page=100&page={page}"],
                capture_output=True, text=True, check=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"[warn] events page {page} failed: {e.stderr.strip()}", file=sys.stderr)
            break
        try:
            batch = json.loads(result.stdout) if result.stdout.strip() else []
        except json.JSONDecodeError:
            break
        if not batch:
            break
        any_in_range = False
        all_older = True
        for ev in batch:
            ts = parse_ts_utc(ev.get("created_at", ""))
            if ts is None:
                continue
            if ts < start_utc:
                continue
            all_older = False
            if ts >= end_utc:
                continue
            events.append(ev)
            any_in_range = True
        if all_older:
            break
        page += 1
    return events


def summarize_event(ev: dict) -> dict:
    etype = ev.get("type")
    repo = (ev.get("repo") or {}).get("name")
    payload = ev.get("payload") or {}
    created_at = ev.get("created_at")
    summary: dict = {
        "type": etype,
        "repo": repo,
        "created_at": created_at,
        "public": ev.get("public"),
    }
    if etype == "PushEvent":
        commits = payload.get("commits") or []
        summary["ref"] = payload.get("ref")
        summary["commit_count"] = len(commits)
        summary["commit_messages"] = [c.get("message", "").splitlines()[0][:160] for c in commits[:10]]
    elif etype == "PullRequestEvent":
        pr = payload.get("pull_request") or {}
        summary["action"] = payload.get("action")
        summary["number"] = payload.get("number")
        summary["title"] = pr.get("title")
        summary["url"] = pr.get("html_url")
    elif etype == "IssuesEvent":
        issue = payload.get("issue") or {}
        summary["action"] = payload.get("action")
        summary["number"] = issue.get("number")
        summary["title"] = issue.get("title")
        summary["url"] = issue.get("html_url")
    elif etype in ("CreateEvent", "DeleteEvent"):
        summary["ref_type"] = payload.get("ref_type")
        summary["ref"] = payload.get("ref")
    elif etype == "ReleaseEvent":
        rel = payload.get("release") or {}
        summary["action"] = payload.get("action")
        summary["tag_name"] = rel.get("tag_name")
        summary["url"] = rel.get("html_url")
    elif etype in ("IssueCommentEvent", "PullRequestReviewCommentEvent", "PullRequestReviewEvent"):
        summary["action"] = payload.get("action")
        summary["issue_number"] = (payload.get("issue") or {}).get("number") or (payload.get("pull_request") or {}).get("number")
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    add_range_args(p)
    args = p.parse_args()

    config = load_config(Path(args.config))
    tz_name = config.get("timezone", "Asia/Shanghai")
    username = config.get("github_username", "").strip()
    if not username:
        print("[error] config.github_username is empty", file=sys.stderr)
        return 2

    start_date, end_date = resolve_range(args)
    start_utc, end_utc = range_to_utc(start_date, end_date, tz_name)
    print_range(start_date, end_date, start_utc, end_utc, tz_name)

    # GitHub search's `created:` uses dates without timezone -> interpreted as UTC.
    # The user's local-tz dates approximate reasonably; events API provides exact UTC for fine filtering.
    date_qual = f"{start_date.isoformat()}..{end_date.isoformat()}"

    prs_authored = search_issues(f"author:{username} is:pr created:{date_qual}")
    prs_updated = search_issues(f"author:{username} is:pr updated:{date_qual}")
    issues_authored = search_issues(f"author:{username} is:issue created:{date_qual}")

    # Deduplicate PRs by url
    pr_by_url: dict[str, dict] = {}
    for node in prs_authored + prs_updated:
        if node.get("__typename") != "PullRequest":
            continue
        url = node.get("url")
        if url and url not in pr_by_url:
            pr_by_url[url] = node
    prs = list(pr_by_url.values())
    issues = [n for n in issues_authored if n.get("__typename") == "Issue"]

    events_raw = fetch_events(username, start_utc, end_utc)
    events = [summarize_event(ev) for ev in events_raw]

    output = {
        "range": {
            "from": start_date.isoformat(),
            "to": end_date.isoformat(),
            "timezone": tz_name,
            "from_utc": start_utc.isoformat(),
            "to_utc": end_utc.isoformat(),
        },
        "github_username": username,
        "pull_requests": prs,
        "issues": issues,
        "events": events,
        "stats": {
            "pr_count": len(prs),
            "issue_count": len(issues),
            "event_count": len(events),
        },
    }

    write_json(Path(args.output), output)
    print(
        f"[github] prs={len(prs)} issues={len(issues)} events={len(events)} -> {args.output}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
