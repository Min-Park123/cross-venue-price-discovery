#!/usr/bin/env python3
"""
event_trace_usa_belgium_56.py — the event_traces_paired.py format, applied
to one additional event: USA-Belgium 56' Belgium goal (1-3).

STRICTLY READ-ONLY: only reads cross_venue_usa_belgium_v2.jsonl and
match_events_usa_belgium.txt. Prints to stdout only.

No thresholds, no onset detection, no lead calls, no annotations beyond the
event marker -- purely descriptive, for a human to read and judge.

Reuses event_traces_paired.py's loading/formatting/pairing functions rather
than reimplementing them. Note the event log for this match is phone-logged
and approximate (minute precision, no seconds; see match_events_usa_belgium.txt).

Usage:
  python3 event_trace_usa_belgium_56.py
"""

from coverage_map import parse_event_log, merge_duplicate_sequences
from event_traces_paired import load_pairs, build_paired_rows, print_paired_trace

DATASET = "cross_venue_usa_belgium_v2.jsonl"
EVENTS_PATH = "match_events_usa_belgium.txt"
LABEL = "56'"


def main():
    print("Raw paired row-level trace only -- no thresholds, no onset detection, no lead calls.")
    print("One row per shared cycle timestamp (both venues), for manual review.")
    print("Note: this match's event log is phone-logged/approximate (minute precision, no seconds).")
    print()

    events = merge_duplicate_sequences(parse_event_log(EVENTS_PATH))
    e = next(ev for ev in events if ev["label"] == LABEL)
    event_ts = int(e["time"].timestamp() * 1000)
    event_dt_str = e["time"].strftime("%H:%M:%S") + ("~" if e["approx"] else "")
    pairs = load_pairs(DATASET)

    print("=" * 100)
    print(f"EVENT: {DATASET}  {LABEL}  {e['time'].strftime('%Y-%m-%d %H:%M:%S')}"
          f"{'~' if e['approx'] else ''} local  '{e['desc']}'")
    print("=" * 100)
    for pair_label, g in pairs.items():
        piv, baselines, lo, hi = build_paired_rows(g, event_ts)
        print_paired_trace(pair_label, piv, baselines, lo, hi, event_ts, LABEL, e["desc"], event_dt_str)


if __name__ == "__main__":
    main()
