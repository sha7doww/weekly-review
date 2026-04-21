#!/usr/bin/env python3
"""Extract braindump entries whose date falls within the range.

Supports two conventions:
  1. Date headings: `## YYYY-MM-DD ...` (H2 or H3). Everything under the heading
     until the next same-or-higher heading is one entry.
  2. Date bullets:  lines starting with `- YYYY-MM-DD ...` or `* YYYY-MM-DD ...`.

If no braindump_path is configured, writes an empty placeholder. If the file
doesn't exist, creates an empty one so the user has a target to edit.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

from _common import (
    add_range_args,
    ensure_parent,
    load_config,
    resolve_range,
)

HEADING_RE = re.compile(r"^(#{1,6})\s+(\d{4}-\d{2}-\d{2})\b(.*)$")
BULLET_DATE_RE = re.compile(r"^([\-\*])\s+(\d{4}-\d{2}-\d{2})\b(.*)$")


def extract_sections(text: str, start: date, end: date) -> list[dict]:
    lines = text.splitlines()
    sections: list[dict] = []

    current: list[str] = []
    current_date: date = None
    current_heading_level: int = None

    def flush():
        nonlocal current, current_date, current_heading_level
        if current_date is not None and start <= current_date <= end:
            sections.append({
                "date": current_date.isoformat(),
                "kind": "heading",
                "heading_level": current_heading_level,
                "body": "\n".join(current).strip(),
            })
        current = []
        current_date = None
        current_heading_level = None

    for ln in lines:
        m = HEADING_RE.match(ln)
        if m:
            flush()
            try:
                current_date = date.fromisoformat(m.group(2))
                current_heading_level = len(m.group(1))
                current.append(ln)
            except ValueError:
                current_date = None
        else:
            if current_date is not None:
                current.append(ln)
    flush()

    # also extract date-prefixed bullets outside of any matched heading
    for ln in lines:
        m = BULLET_DATE_RE.match(ln)
        if not m:
            continue
        try:
            d = date.fromisoformat(m.group(2))
        except ValueError:
            continue
        if start <= d <= end:
            sections.append({
                "date": d.isoformat(),
                "kind": "bullet",
                "heading_level": None,
                "body": ln.strip(),
            })
    sections.sort(key=lambda s: (s["date"], s["kind"]))
    return sections


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    add_range_args(p)
    args = p.parse_args()

    config = load_config(Path(args.config))
    path_s = (config.get("braindump_path") or "").strip()

    start_date, end_date = resolve_range(args)

    output = Path(args.output)
    ensure_parent(output)

    if not path_s:
        output.write_text(f"<!-- no braindump_path configured; range {start_date}..{end_date} -->\n")
        print("[braindump] no braindump_path configured, wrote empty placeholder", file=sys.stderr)
        return 0

    braindump = Path(path_s).expanduser()
    if not braindump.exists():
        braindump.parent.mkdir(parents=True, exist_ok=True)
        braindump.write_text("# Braindump\n\nAdd dated entries like:\n\n## 2026-04-13\n- note\n")
        output.write_text(f"<!-- braindump file created at {braindump}; no entries yet -->\n")
        print(f"[braindump] created empty braindump at {braindump}", file=sys.stderr)
        return 0

    try:
        text = braindump.read_text()
    except (OSError, UnicodeDecodeError) as e:
        print(f"[error] cannot read {braindump}: {e}", file=sys.stderr)
        output.write_text(f"<!-- error reading {braindump}: {e} -->\n")
        return 0

    sections = extract_sections(text, start_date, end_date)
    if not sections:
        output.write_text(
            f"<!-- braindump: {braindump}; no entries in {start_date}..{end_date} -->\n"
        )
        print("[braindump] no in-range entries", file=sys.stderr)
        return 0

    lines_out: list[str] = [
        f"<!-- braindump: {braindump}; {len(sections)} entries in {start_date}..{end_date} -->",
        "",
    ]
    for sec in sections:
        lines_out.append(sec["body"])
        lines_out.append("")
    output.write_text("\n".join(lines_out))
    print(f"[braindump] {len(sections)} entries -> {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
