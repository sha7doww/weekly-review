#!/usr/bin/env python3
"""Extract Tencent Meeting minutes whose timestamps fall within the range.

Source: config.tencent_meeting_dir (empty string disables this collector).
Expects files named `<YYYYMMDDHHMMSS>-<room>-纪要文本-<N>.txt` — Tencent Meeting's
AI-generated transcript export. Body format is:

    会议主题：<topic>
    <blank>
    发言人：<name1>、<name2>
    <blank>
    会议摘要：<one-paragraph summary>
    <blank>
    ------------------------------------------------------------------------
    <rest of the structured transcript>

Multi-part transcripts (`-2.txt`, `-3.txt` ...) are grouped with their `-1`
sibling by (timestamp, room) and their bodies concatenated in part order.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from _common import (
    add_range_args,
    load_config,
    print_range,
    range_to_utc,
    resolve_range,
    write_json,
)

FILENAME_RE = re.compile(r"^(\d{14})-(.+?)-纪要文本-(\d+)\.txt$")
TOPIC_RE = re.compile(r"^会议主题[：:]\s*(.+)$")
SPEAKERS_RE = re.compile(r"^发言人[：:]\s*(.+)$")
SUMMARY_RE = re.compile(r"^会议摘要[：:]\s*(.+)$")
SPLIT_NAMES_RE = re.compile(r"[、,，;；]")


def parse_filename(name: str):
    m = FILENAME_RE.match(name)
    if not m:
        return None
    ts_raw, room, part = m.group(1), m.group(2), int(m.group(3))
    try:
        ts = datetime.strptime(ts_raw, "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return {"timestamp_naive": ts, "room": room, "part": part}


def parse_body(text: str) -> tuple[str, list[str], str, str]:
    """Return (topic, speakers, summary, body_after_separator)."""
    topic = ""
    speakers: list[str] = []
    summary = ""
    lines = text.splitlines()
    header_end = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if m := TOPIC_RE.match(s):
            topic = m.group(1).strip()
        elif m := SPEAKERS_RE.match(s):
            raw = m.group(1).strip()
            speakers = [n.strip() for n in SPLIT_NAMES_RE.split(raw) if n.strip()]
        elif m := SUMMARY_RE.match(s):
            summary = m.group(1).strip()
        elif s and set(s) == {"-"} and len(s) >= 10:
            header_end = i + 1
            break
    body_rest = "\n".join(lines[header_end:]).strip() if header_end else ""
    return topic, speakers, summary, body_rest


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    add_range_args(p)
    args = p.parse_args()

    config = load_config(Path(args.config))
    tz_name = config.get("timezone") or "Asia/Shanghai"
    tz = ZoneInfo(tz_name)

    start_date, end_date = resolve_range(args)
    start_utc, end_utc = range_to_utc(start_date, end_date, tz_name)
    print_range(start_date, end_date, start_utc, end_utc, tz_name)

    output = Path(args.output)
    meeting_dir_s = (config.get("tencent_meeting_dir") or "").strip()

    result = {
        "range": {
            "from": start_date.isoformat(),
            "to": end_date.isoformat(),
            "timezone": tz_name,
            "from_utc": start_utc.isoformat(),
            "to_utc": end_utc.isoformat(),
        },
        "tencent_meeting_dir": meeting_dir_s,
        "stats": {
            "dir_exists": False,
            "files_scanned": 0,
            "files_unparseable": 0,
            "meetings_in_range": 0,
            "total_body_chars": 0,
        },
        "meetings": [],
    }

    if not meeting_dir_s:
        write_json(output, result)
        print(
            "[tencent-meeting] no tencent_meeting_dir configured, wrote empty",
            file=sys.stderr,
        )
        return 0

    meeting_dir = Path(meeting_dir_s).expanduser()
    if not meeting_dir.is_dir():
        write_json(output, result)
        print(
            f"[tencent-meeting] dir does not exist: {meeting_dir}",
            file=sys.stderr,
        )
        return 0

    result["stats"]["dir_exists"] = True

    grouped: dict[tuple[datetime, str], list[tuple[int, Path]]] = defaultdict(list)
    scanned = 0
    unparseable = 0
    for f in sorted(meeting_dir.iterdir()):
        if not f.is_file() or f.suffix.lower() != ".txt":
            continue
        scanned += 1
        parsed = parse_filename(f.name)
        if not parsed:
            unparseable += 1
            continue
        ts_local = parsed["timestamp_naive"].replace(tzinfo=tz)
        ts_utc = ts_local.astimezone(timezone.utc)
        if not (start_utc <= ts_utc < end_utc):
            continue
        grouped[(ts_utc, parsed["room"])].append((parsed["part"], f))

    result["stats"]["files_scanned"] = scanned
    result["stats"]["files_unparseable"] = unparseable

    meetings: list[dict] = []
    total_chars = 0
    for (ts_utc, room), parts in sorted(grouped.items()):
        parts.sort(key=lambda x: x[0])
        ts_local = ts_utc.astimezone(tz)
        primary_part, primary_file = parts[0]
        try:
            primary_text = primary_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(
                f"[tencent-meeting] failed to read {primary_file}: {e}",
                file=sys.stderr,
            )
            continue
        topic, speakers, summary, body = parse_body(primary_text)
        for _, f in parts[1:]:
            try:
                t = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                print(f"[tencent-meeting] failed to read {f}: {e}", file=sys.stderr)
                continue
            _, _, _, extra_body = parse_body(t)
            body = body + "\n\n" + extra_body
        total_chars += len(body)
        meetings.append(
            {
                "timestamp_utc": ts_utc.isoformat(),
                "timestamp_local": ts_local.isoformat(),
                "file_paths": [str(f) for _, f in parts],
                "room_name": room,
                "part_count": len(parts),
                "topic": topic,
                "participants": speakers,
                "summary": summary,
                "body_char_count": len(body),
                "body": body,
            }
        )

    result["stats"]["meetings_in_range"] = len(meetings)
    result["stats"]["total_body_chars"] = total_chars
    result["meetings"] = meetings

    write_json(output, result)
    print(
        f"[tencent-meeting] scanned={scanned} unparseable={unparseable} "
        f"meetings_in_range={len(meetings)} total_body_chars={total_chars} "
        f"-> {args.output}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
