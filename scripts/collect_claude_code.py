#!/usr/bin/env python3
"""Collect Claude Code conversation summaries for a date range.

Reads ~/.claude/projects/<encoded-cwd>/<session-id>.jsonl, filters by timestamp,
aggregates per-session statistics, and writes a compact JSON summary.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from _common import (
    add_range_args,
    load_config,
    parse_ts_utc,
    print_range,
    range_to_utc,
    resolve_range,
    truncate,
    write_json,
)

PROJECTS_DIR = Path.home() / ".claude" / "projects"
SKIP_SUBDIRS = {"subagents", "tool-results", "memory"}
SKIP_TYPES = {"file-history-snapshot", "permission-mode", "attachment"}

# Synthetic wrappers that are not substantive user input (slash commands, caveats, hooks).
SYNTHETIC_PREFIXES = (
    "<command-name>",
    "<command-message>",
    "<command-args>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<local-command-caveat>",
    "<user-prompt-submit-hook>",
    "<bash-input>",
    "<bash-stdout>",
    "<bash-stderr>",
    "<system-reminder>",
)


def decode_cwd(dir_name: str) -> str:
    """Reverse the /-to-- encoding Claude Code uses for project paths."""
    return dir_name.replace("-", "/")


def extract_text(content) -> str:
    """Claude content can be string or list of blocks. Pull out plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif "text" in block:
                    parts.append(block["text"])
        return "\n".join(parts)
    return ""


def is_synthetic(text: str) -> bool:
    """True if the text is a slash-command / hook / caveat wrapper, not real user input."""
    if not text:
        return True
    s = text.lstrip()
    return s.startswith(SYNTHETIC_PREFIXES)


def iter_session_files(projects_dir: Path, exclude_cwds: set[str]):
    """Yield (jsonl_path, encoded_cwd) for each candidate session file.

    Skips project dirs whose decoded cwd is in exclude_cwds and skips dirs starting
    with `-sessions-` (Cowork subprocess artifacts).
    """
    if not projects_dir.exists():
        return
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        name = project_dir.name
        if name.startswith("-sessions-"):
            continue
        decoded = decode_cwd(name)
        if decoded in exclude_cwds:
            continue
        for entry in project_dir.iterdir():
            if entry.is_file() and entry.suffix == ".jsonl":
                yield entry, name


def summarize_session(
    jsonl_path: Path,
    encoded_cwd: str,
    start_utc: datetime,
    end_utc: datetime,
    min_messages: int,
    min_duration: int,
) -> Optional[dict]:
    """Return a summary dict, or None if no activity in range."""
    user_msgs_in_range: list[tuple[datetime, str]] = []
    assistant_count_in_range = 0
    first_ts_in_range: Optional[datetime] = None
    last_ts_in_range: Optional[datetime] = None
    session_id_seen: Optional[str] = None
    cwd_seen: Optional[str] = None
    git_branch_seen: Optional[str] = None

    total_bytes = 0
    try:
        with jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                total_bytes += len(line)
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                rec_type = rec.get("type")
                if rec_type in SKIP_TYPES:
                    continue
                if rec.get("isMeta"):
                    continue
                if rec_type not in ("user", "assistant"):
                    continue
                ts = parse_ts_utc(rec.get("timestamp", ""))
                if ts is None:
                    continue
                if not (start_utc <= ts < end_utc):
                    continue

                if session_id_seen is None:
                    session_id_seen = rec.get("sessionId")
                if cwd_seen is None:
                    cwd_seen = rec.get("cwd")
                if git_branch_seen is None:
                    git_branch_seen = rec.get("gitBranch")

                if first_ts_in_range is None or ts < first_ts_in_range:
                    first_ts_in_range = ts
                if last_ts_in_range is None or ts > last_ts_in_range:
                    last_ts_in_range = ts

                if rec_type == "user":
                    msg = rec.get("message") or {}
                    content = msg.get("content")
                    text = extract_text(content).strip()
                    if text and not is_synthetic(text):
                        user_msgs_in_range.append((ts, text))
                else:
                    assistant_count_in_range += 1
    except (OSError, UnicodeDecodeError) as e:
        print(f"[warn] unreadable {jsonl_path}: {e}", file=sys.stderr)
        return None

    if not user_msgs_in_range and assistant_count_in_range == 0:
        return None

    user_msgs_in_range.sort(key=lambda x: x[0])
    first_user = user_msgs_in_range[0][1] if user_msgs_in_range else ""
    last_user = user_msgs_in_range[-1][1] if user_msgs_in_range else ""
    user_count = len(user_msgs_in_range)
    duration = int((last_ts_in_range - first_ts_in_range).total_seconds()) if first_ts_in_range and last_ts_in_range else 0
    exploratory = user_count < min_messages or duration < min_duration

    return {
        "session_id": session_id_seen or jsonl_path.stem,
        "cwd": cwd_seen or decode_cwd(encoded_cwd),
        "encoded_cwd": encoded_cwd,
        "jsonl_path": str(jsonl_path),
        "git_branch": git_branch_seen,
        "start_utc": first_ts_in_range.isoformat() if first_ts_in_range else None,
        "end_utc": last_ts_in_range.isoformat() if last_ts_in_range else None,
        "duration_seconds": duration,
        "user_messages": user_count,
        "assistant_messages": assistant_count_in_range,
        "first_user_message": truncate(first_user, 500),
        "last_user_message": truncate(last_user, 300),
        "user_message_snippets": [truncate(m[1], 100) for m in user_msgs_in_range[:40]],
        "exploratory": exploratory,
        "file_bytes": total_bytes,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    add_range_args(p)
    args = p.parse_args()

    config = load_config(Path(args.config))
    tz_name = config.get("timezone", "Asia/Shanghai")
    min_messages = int(config.get("session_min_messages", 3))
    min_duration = int(config.get("session_min_duration_seconds", 120))
    exclude_cwds = set(config.get("exclude_project_cwds", []))

    start_date, end_date = resolve_range(args)
    start_utc, end_utc = range_to_utc(start_date, end_date, tz_name)
    print_range(start_date, end_date, start_utc, end_utc, tz_name)

    # mtime prefilter: any file whose mtime is before start_utc or after end_utc + 1d can't have in-range records
    # (the jsonl is append-only, so last mtime is >= last record timestamp)
    mtime_floor = start_utc.timestamp()

    sessions: list[dict] = []
    exploratory: list[dict] = []
    scanned = 0
    skipped_mtime = 0

    for jsonl_path, encoded_cwd in iter_session_files(PROJECTS_DIR, exclude_cwds):
        scanned += 1
        try:
            mtime = jsonl_path.stat().st_mtime
        except OSError:
            continue
        # append-only: if last write is before start, skip
        if mtime < mtime_floor:
            skipped_mtime += 1
            continue
        summary = summarize_session(
            jsonl_path, encoded_cwd, start_utc, end_utc, min_messages, min_duration
        )
        if summary is None:
            continue
        (exploratory if summary["exploratory"] else sessions).append(summary)

    sessions.sort(key=lambda s: s["start_utc"] or "")
    exploratory.sort(key=lambda s: s["start_utc"] or "")

    total_user = sum(s["user_messages"] for s in sessions) + sum(s["user_messages"] for s in exploratory)
    by_project: dict[str, int] = {}
    for s in sessions + exploratory:
        by_project[s["cwd"]] = by_project.get(s["cwd"], 0) + s["user_messages"]

    output = {
        "range": {
            "from": start_date.isoformat(),
            "to": end_date.isoformat(),
            "timezone": tz_name,
            "from_utc": start_utc.isoformat(),
            "to_utc": end_utc.isoformat(),
        },
        "stats": {
            "files_scanned": scanned,
            "files_skipped_by_mtime": skipped_mtime,
            "substantive_sessions": len(sessions),
            "exploratory_sessions": len(exploratory),
            "total_user_messages": total_user,
            "user_messages_by_project": dict(
                sorted(by_project.items(), key=lambda kv: -kv[1])
            ),
        },
        "sessions": sessions,
        "exploratory_sessions": exploratory,
    }

    write_json(Path(args.output), output)
    print(
        f"[claude-code] scanned={scanned} kept={len(sessions)} exploratory={len(exploratory)} "
        f"user_msgs={total_user} -> {args.output}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
