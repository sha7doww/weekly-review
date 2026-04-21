"""Shared helpers for the collector scripts.

Keep this stdlib-only. Python 3.9+.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        print(f"[error] config not found: {config_path}", file=sys.stderr)
        sys.exit(2)
    return json.loads(config_path.read_text())


def parse_iso_week(s: str) -> tuple[date, date]:
    """Parse YYYY-Www into (monday, sunday) dates."""
    if "W" not in s.upper():
        raise ValueError(f"not an ISO week: {s!r}")
    year_s, wk_s = s.upper().split("W")
    year = int(year_s.rstrip("-"))
    wk = int(wk_s)
    monday = date.fromisocalendar(year, wk, 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def last_complete_iso_week(today: Optional[date] = None) -> tuple[date, date]:
    today = today or date.today()
    iso_year, iso_wk, _ = today.isocalendar()
    this_monday = date.fromisocalendar(iso_year, iso_wk, 1)
    prev_monday = this_monday - timedelta(days=7)
    prev_sunday = prev_monday + timedelta(days=6)
    return prev_monday, prev_sunday


def resolve_range(args_ns: argparse.Namespace) -> tuple[date, date]:
    """Given parsed args with --from/--to/--week, return (start_date, end_date) inclusive."""
    if args_ns.week:
        return parse_iso_week(args_ns.week)
    if args_ns.date_from and args_ns.date_to:
        return (
            date.fromisoformat(args_ns.date_from),
            date.fromisoformat(args_ns.date_to),
        )
    return last_complete_iso_week()


def range_to_utc(start: date, end: date, tz_name: str) -> tuple[datetime, datetime]:
    """Convert inclusive local-date range to UTC datetime bounds.

    start_utc = start 00:00 local -> UTC
    end_utc   = (end + 1 day) 00:00 local -> UTC (exclusive upper bound)
    """
    tz = ZoneInfo(tz_name)
    start_local = datetime.combine(start, time(0, 0), tzinfo=tz)
    end_local = datetime.combine(end + timedelta(days=1), time(0, 0), tzinfo=tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def add_range_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--from", dest="date_from", help="start date YYYY-MM-DD (local tz)")
    p.add_argument("--to", dest="date_to", help="end date YYYY-MM-DD inclusive (local tz)")
    p.add_argument("--week", help="ISO week e.g. 2026-W15 (takes precedence over --from/--to)")
    p.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parent.parent / "config.json"),
        help="path to config.json",
    )
    p.add_argument("--output", required=True, help="output file path (.json or .md)")


def print_range(start: date, end: date, start_utc: datetime, end_utc: datetime, tz_name: str) -> None:
    print(
        f"[range] {start.isoformat()} .. {end.isoformat()} "
        f"({tz_name}) -> {start_utc.isoformat()} .. {end_utc.isoformat()} (UTC)",
        file=sys.stderr,
    )


def ensure_parent(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def parse_ts_utc(s: str) -> Optional[datetime]:
    """Parse ISO-8601 timestamp to aware UTC datetime. Returns None on failure."""
    if not s:
        return None
    try:
        # handle trailing Z
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def truncate(s: str, n: int) -> str:
    if s is None:
        return ""
    s = s.strip()
    if len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"
