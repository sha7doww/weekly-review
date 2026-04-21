#!/usr/bin/env python3
"""Collect local git commits authored by configured users within a date range.

Walks configured directories for `.git` dirs, runs `git log` per author,
and dedupes across authors. Also runs `git status --porcelain` for WIP.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from _common import (
    add_range_args,
    load_config,
    print_range,
    range_to_utc,
    resolve_range,
    write_json,
)

MAX_DEPTH = 4
SKIP_DIR_NAMES = {"node_modules", ".venv", "venv", "vendor", "target", "dist", "build", ".next"}


def find_repos(root: Path, max_depth: int = MAX_DEPTH) -> list[Path]:
    """BFS for .git directories, skipping common vendored dirs."""
    repos: list[Path] = []
    if not root.exists():
        return repos
    stack = [(root, 0)]
    while stack:
        cur, depth = stack.pop()
        if cur.name in SKIP_DIR_NAMES:
            continue
        git_dir = cur / ".git"
        if git_dir.exists():
            repos.append(cur)
            continue
        if depth >= max_depth:
            continue
        try:
            for entry in cur.iterdir():
                if entry.is_dir() and not entry.is_symlink():
                    stack.append((entry, depth + 1))
        except (PermissionError, OSError):
            continue
    return repos


def git(repo: Path, args: list[str], quiet: bool = False) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        err = (e.stderr or "").strip()
        if err and not quiet:
            print(f"[warn] git {args[0]} failed in {repo}: {err[:200]}", file=sys.stderr)
        return None
    except FileNotFoundError:
        print("[error] git not found in PATH", file=sys.stderr)
        sys.exit(2)


# \x1e prefixes each commit record so splitting captures header + following shortstat together.
COMMIT_FORMAT = "%x1e%H%x1f%an%x1f%ae%x1f%aI%x1f%s"


def parse_shortstat(line: str) -> tuple[int, int, int]:
    """Parse ' 3 files changed, 12 insertions(+), 1 deletion(-)' -> (files, ins, dels)."""
    files_changed = insertions = deletions = 0
    for token in line.split(","):
        token = token.strip()
        parts = token.split()
        if not parts:
            continue
        try:
            n = int(parts[0])
        except ValueError:
            continue
        if "file" in token:
            files_changed = n
        elif "insertion" in token:
            insertions = n
        elif "deletion" in token:
            deletions = n
    return files_changed, insertions, deletions


def list_commits(repo: Path, authors: list[str], since: str, until: str) -> list[dict]:
    """Run one git log per author (git log only accepts one --author), merge by sha."""
    by_sha: dict[str, dict] = {}
    for author in authors:
        out = git(
            repo,
            [
                "log",
                "--no-merges",
                f"--since={since}",
                f"--until={until}",
                f"--author={author}",
                f"--format={COMMIT_FORMAT}",
                "--shortstat",
                "--all",
            ],
        )
        if not out:
            continue
        records = out.split("\x1e")
        for rec in records:
            if not rec.strip():
                continue
            lines = rec.split("\n")
            # lines[0] is the field line: HASH\x1fNAME\x1fEMAIL\x1fDATE\x1fSUBJECT
            fields = lines[0].split("\x1f")
            if len(fields) < 5:
                continue
            sha, an, ae, aiso, subj = fields[0], fields[1], fields[2], fields[3], fields[4]
            if sha in by_sha:
                continue
            # find the shortstat line (starts with " N file" / " N files")
            files_changed = insertions = deletions = 0
            for ln in lines[1:]:
                stripped = ln.strip()
                if "file" in stripped and ("change" in stripped or "changed" in stripped):
                    files_changed, insertions, deletions = parse_shortstat(stripped)
                    break
            by_sha[sha] = {
                "sha": sha,
                "author_name": an,
                "author_email": ae,
                "authored_at": aiso,
                "subject": subj,
                "files_changed": files_changed,
                "insertions": insertions,
                "deletions": deletions,
            }
    return sorted(by_sha.values(), key=lambda c: c["authored_at"])


def collect_repo(repo: Path, authors: list[str], since_utc: datetime, until_utc: datetime) -> dict:
    since = since_utc.isoformat()
    until = until_utc.isoformat()
    commits = list_commits(repo, authors, since, until)

    remote_out = git(repo, ["remote", "get-url", "origin"], quiet=True) or ""
    remote = remote_out.strip() or None

    branch_out = git(repo, ["rev-parse", "--abbrev-ref", "HEAD"]) or ""
    branch = branch_out.strip() or None

    status_out = git(repo, ["status", "--porcelain=v1"]) or ""
    wip_lines = [ln for ln in status_out.splitlines() if ln.strip()]

    return {
        "repo": str(repo),
        "remote": remote,
        "current_branch": branch,
        "commits": commits,
        "commit_count": len(commits),
        "insertions": sum(c["insertions"] for c in commits),
        "deletions": sum(c["deletions"] for c in commits),
        "wip_file_count": len(wip_lines),
        "wip_sample": wip_lines[:20],
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    add_range_args(p)
    args = p.parse_args()

    config = load_config(Path(args.config))
    tz_name = config.get("timezone", "Asia/Shanghai")
    authors = [a for a in config.get("git_authors", []) if a]
    if not authors:
        print("[error] config.git_authors is empty", file=sys.stderr)
        return 2
    dirs = [Path(d).expanduser() for d in config.get("local_git_dirs", [])]
    if not dirs:
        print("[error] config.local_git_dirs is empty", file=sys.stderr)
        return 2

    start_date, end_date = resolve_range(args)
    start_utc, end_utc = range_to_utc(start_date, end_date, tz_name)
    print_range(start_date, end_date, start_utc, end_utc, tz_name)

    all_repos: list[Path] = []
    seen: set[Path] = set()
    for root in dirs:
        for repo in find_repos(root):
            repo_resolved = repo.resolve()
            if repo_resolved in seen:
                continue
            seen.add(repo_resolved)
            all_repos.append(repo)

    repo_reports: list[dict] = []
    for repo in all_repos:
        rep = collect_repo(repo, authors, start_utc, end_utc)
        if rep["commit_count"] == 0 and rep["wip_file_count"] == 0:
            continue
        repo_reports.append(rep)

    repo_reports.sort(key=lambda r: -r["commit_count"])

    total_commits = sum(r["commit_count"] for r in repo_reports)
    total_ins = sum(r["insertions"] for r in repo_reports)
    total_del = sum(r["deletions"] for r in repo_reports)

    output = {
        "range": {
            "from": start_date.isoformat(),
            "to": end_date.isoformat(),
            "timezone": tz_name,
            "from_utc": start_utc.isoformat(),
            "to_utc": end_utc.isoformat(),
        },
        "authors": authors,
        "scanned_roots": [str(d) for d in dirs],
        "scanned_repo_count": len(all_repos),
        "stats": {
            "repos_with_activity": len(repo_reports),
            "total_commits": total_commits,
            "total_insertions": total_ins,
            "total_deletions": total_del,
        },
        "repos": repo_reports,
    }

    write_json(Path(args.output), output)
    print(
        f"[local-git] repos_scanned={len(all_repos)} repos_with_activity={len(repo_reports)} "
        f"commits={total_commits} -> {args.output}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
