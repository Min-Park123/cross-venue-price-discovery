#!/usr/bin/env python3
"""
check_integrity_mexico_england.py — quick integrity check on a collector
JSONL session, cross-referenced against a plain-text match event log.

Checks:
  1. every line parses as JSON (report malformed count)
  2. total rows per venue per pair
  3. max gap between consecutive timestamps per venue
  4. any gap > 30s, with wall-clock start/end
  5. whether any such gap falls within 60s of a logged match event

Usage:
  python3 check_integrity_mexico_england.py [jsonl_path] [events_path]
"""

import json
import re
import sys
from datetime import datetime, timedelta

import pandas as pd

DEFAULT_JSONL = "cross_venue_mexico_england_main.jsonl"
DEFAULT_EVENTS = "match_events_mexico_england.txt"

GAP_THRESHOLD_S = 30
EVENT_PROXIMITY_S = 60

EVENT_LINE_RE = re.compile(r"^(\S+)\s*\|\s*(\d{1,2}:\d{2}:\d{2})\s*\|\s*(.+)$")
HEADER_DATE_RE = re.compile(r"([A-Z][a-z]{2})\s+(\d{1,2})\s+\d{2}:\d{2}:\d{2}\s+\S+\s+(\d{4})")


def fmt_ts(ms):
    return datetime.fromtimestamp(ms / 1000.0).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def load_rows(path):
    rows, malformed = [], 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                malformed += 1
    return rows, malformed


def load_events(path):
    with open(path) as f:
        text = f.read()
    m = HEADER_DATE_RE.search(text)
    if not m:
        sys.exit(f"Could not find a header date in {path}")
    month_str, day_str, year_str = m.groups()
    base_date = datetime.strptime(f"{month_str} {day_str} {year_str}", "%b %d %Y").date()

    events = []
    for line in text.splitlines():
        m = EVENT_LINE_RE.match(line.strip())
        if not m:
            continue
        label, hms, desc = m.groups()
        h, mi, s = (int(x) for x in hms.split(":"))
        events.append({
            "label": label,
            "time": datetime(base_date.year, base_date.month, base_date.day, h, mi, s),
            "desc": desc.strip(),
        })
    return events


def find_gaps(ts_series):
    ts_sorted = sorted(set(ts_series))
    gaps = []
    for a, b in zip(ts_sorted, ts_sorted[1:]):
        gaps.append((a, b, (b - a) / 1000.0))
    return gaps


def main():
    jsonl_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_JSONL
    events_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_EVENTS

    rows, malformed = load_rows(jsonl_path)
    print(f"=== Parse check: {jsonl_path} ===")
    print(f"total lines parsed OK : {len(rows)}")
    print(f"malformed lines       : {malformed}")
    print()

    df = pd.DataFrame(rows)

    print("=== Rows per venue per pair ===")
    counts = df.groupby(["venue", "pair"]).size()
    for (venue, pair), n in counts.items():
        print(f"  {venue:<10} {pair:<90} n={n}")
    print()

    print(f"=== Max gap between consecutive timestamps per venue (threshold {GAP_THRESHOLD_S}s) ===")
    all_long_gaps = []  # (venue, start_ms, end_ms, gap_s)
    for venue, g in df.groupby("venue"):
        gaps = find_gaps(g["ts"])
        max_gap = max(gaps, key=lambda x: x[2]) if gaps else None
        if max_gap:
            print(f"  {venue:<10} max gap = {max_gap[2]:.1f}s "
                  f"({fmt_ts(max_gap[0])} -> {fmt_ts(max_gap[1])})")
        else:
            print(f"  {venue:<10} not enough rows to compute a gap")
        for a, b, gap_s in gaps:
            if gap_s > GAP_THRESHOLD_S:
                all_long_gaps.append((venue, a, b, gap_s))
    print()

    print(f"=== Gaps longer than {GAP_THRESHOLD_S}s ===")
    if not all_long_gaps:
        print("  none")
    else:
        for venue, a, b, gap_s in sorted(all_long_gaps, key=lambda x: x[1]):
            print(f"  {venue:<10} {gap_s:7.1f}s   {fmt_ts(a)} -> {fmt_ts(b)}")
    print()

    events = load_events(events_path)
    print(f"=== Cross-referencing against {events_path} ({len(events)} logged events) ===")
    any_overlap = False
    if not all_long_gaps:
        print("  no gaps to check")
    else:
        for venue, a, b, gap_s in sorted(all_long_gaps, key=lambda x: x[1]):
            gap_start = datetime.fromtimestamp(a / 1000.0)
            gap_end = datetime.fromtimestamp(b / 1000.0)
            window_start = gap_start - timedelta(seconds=EVENT_PROXIMITY_S)
            window_end = gap_end + timedelta(seconds=EVENT_PROXIMITY_S)
            hits = [e for e in events if window_start <= e["time"] <= window_end]
            gap_label = f"{venue} gap {fmt_ts(a)} -> {fmt_ts(b)} ({gap_s:.1f}s)"
            if hits:
                any_overlap = True
                for e in hits:
                    print(f"  [OVERLAP] {gap_label} <-> {e['label']} {e['time'].strftime('%H:%M:%S')} "
                          f"{e['desc']!r} (within {EVENT_PROXIMITY_S}s)")
            else:
                print(f"  [clear]   {gap_label} — no logged event within {EVENT_PROXIMITY_S}s")
    print()

    ok = (malformed == 0) and not any_overlap
    print("=== SUMMARY ===")
    print(f"  malformed lines           : {malformed}")
    print(f"  gaps > {GAP_THRESHOLD_S}s               : {len(all_long_gaps)}")
    print(f"  gaps overlapping an event : {'yes' if any_overlap else 'no'}")
    print()
    print("INTEGRITY CHECK:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
