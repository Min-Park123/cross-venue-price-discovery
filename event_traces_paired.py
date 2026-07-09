#!/usr/bin/env python3
"""
event_traces_paired.py — the same 8 traces as event_traces.py, reformatted
for manual review: one row per paired sample (both venues side by side,
matched on the collector's shared per-cycle "ts"), with the logged event
time marked and a blank line every 30s of trace time.

STRICTLY READ-ONLY: only reads collector JSONL files and match_events_*.txt.
Prints to stdout only; never writes, appends, or otherwise modifies any file.

No thresholds, no onset detection, no lead calls, no annotations beyond the
event marker -- purely descriptive, for a human to read and judge.

Reuses detect_events.py's loading conventions and coverage_map.py's event-log
parsing rather than reimplementing them.

Events traced (both pairs, per match), window +/-120s around each:
  - Mexico-England:  36' England Goal, 37' England Goal, 43' Mexico Goal
  - Portugal-Spain:  90' GOAL Spain (Merino)

Usage:
  python3 event_traces_paired.py
"""

import numpy as np
import pandas as pd
from datetime import datetime

from detect_events import load_rows, build_frame
from coverage_map import parse_event_log, merge_duplicate_sequences

WINDOW_S = 120
BLANK_EVERY_S = 30

EVENTS = [
    ("cross_venue_mexico_england_main.jsonl", "match_events_mexico_england.txt", "36'"),
    ("cross_venue_mexico_england_main.jsonl", "match_events_mexico_england.txt", "37'"),
    ("cross_venue_mexico_england_main.jsonl", "match_events_mexico_england.txt", "43'"),
    ("cross_venue_portugal_spain_v3.jsonl", "match_events_portugal_spain.txt", "90'"),
]


def fmt_hms(ms):
    return datetime.fromtimestamp(ms / 1000.0).strftime("%H:%M:%S.%f")[:-3]


def fmt_val(v):
    return f"{v:.2f}" if v is not None and pd.notna(v) else "n/a"


def fmt_delta(v):
    return f"{v:+.2f}" if v is not None and pd.notna(v) else "n/a"


def load_pairs(dataset_path):
    rows = load_rows(dataset_path)
    df = build_frame(rows)
    pairs = {}
    for pair, g in df.groupby("pair"):
        ticker = pair.split(":", 1)[0]
        label = ticker.rsplit("-", 1)[-1]
        pairs[label] = g
    return pairs


def prewindow_baseline(g, venue, lo):
    v = g[g["venue"] == venue].sort_values("ts")
    ts_arr = v["ts"].to_numpy()
    idx = np.searchsorted(ts_arr, lo, side="right") - 1
    return float(v["mid"].iloc[idx]) if idx >= 0 else None


def build_paired_rows(g, event_ts, window_s=WINDOW_S):
    lo, hi = event_ts - window_s * 1000, event_ts + window_s * 1000
    baselines = {v: prewindow_baseline(g, v, lo) for v in ("kalshi", "polymarket")}

    sub = g[(g["ts"] >= lo) & (g["ts"] <= hi)]
    piv = sub.pivot_table(index="ts", columns="venue", values="mid", aggfunc="first")
    piv = piv.reindex(columns=["kalshi", "polymarket"]).sort_index()
    return piv, baselines, lo, hi


def print_paired_trace(pair_label, piv, baselines, lo, hi, event_ts, event_label, event_desc, event_dt):
    print(f"  pair {pair_label}:  pre-window baseline -- kalshi={fmt_val(baselines['kalshi'])}c, "
          f"polymarket={fmt_val(baselines['polymarket'])}c")
    print(f"  window {fmt_hms(lo)} -> {fmt_hms(hi)} local")
    header = (f"  {'wall-clock':<16} {'kalshi_mid':>10} {'kalshi_delta':>12} "
              f"{'poly_mid':>9} {'poly_delta':>10} {'basis':>8}")
    print(header)
    print("  " + "-" * (len(header) - 2))

    if piv.empty:
        print("  (no rows in window)")
        print()
        return

    next_blank_boundary = lo + BLANK_EVERY_S * 1000
    event_printed = False
    ts_values = piv.index.to_numpy()

    for ts in ts_values:
        # blank line(s) for elapsed 30s trace-time boundaries crossed
        while ts >= next_blank_boundary:
            print()
            next_blank_boundary += BLANK_EVERY_S * 1000

        # event marker, placed just before the first row at/after the event time
        if not event_printed and ts >= event_ts:
            print(f"  <<< EVENT: {event_label} {event_dt} '{event_desc}' >>>")
            event_printed = True

        k_mid = piv.loc[ts, "kalshi"] if "kalshi" in piv.columns else np.nan
        p_mid = piv.loc[ts, "polymarket"] if "polymarket" in piv.columns else np.nan
        k_delta = (k_mid - baselines["kalshi"]) if pd.notna(k_mid) and baselines["kalshi"] is not None else np.nan
        p_delta = (p_mid - baselines["polymarket"]) if pd.notna(p_mid) and baselines["polymarket"] is not None else np.nan
        basis = (k_mid - p_mid) if pd.notna(k_mid) and pd.notna(p_mid) else np.nan

        print(f"  {fmt_hms(ts):<16} {fmt_val(k_mid):>10} {fmt_delta(k_delta):>12} "
              f"{fmt_val(p_mid):>9} {fmt_delta(p_delta):>10} {fmt_delta(basis):>8}")

    if not event_printed:
        print(f"  <<< EVENT: {event_label} {event_dt} '{event_desc}' >>> (falls after last row in window)")
    print()


def main():
    print("Raw paired row-level traces only -- no thresholds, no onset detection, no lead calls.")
    print("One row per shared cycle timestamp (both venues), for manual review.")
    print()
    for dataset_path, events_path, label in EVENTS:
        events = merge_duplicate_sequences(parse_event_log(events_path))
        e = next(ev for ev in events if ev["label"] == label)
        event_ts = int(e["time"].timestamp() * 1000)
        event_dt_str = e["time"].strftime("%H:%M:%S")
        pairs = load_pairs(dataset_path)

        print("=" * 100)
        print(f"EVENT: {dataset_path}  {label}  {e['time'].strftime('%Y-%m-%d %H:%M:%S')} local  "
              f"'{e['desc']}'")
        print("=" * 100)
        for pair_label, g in pairs.items():
            piv, baselines, lo, hi = build_paired_rows(g, event_ts)
            print_paired_trace(pair_label, piv, baselines, lo, hi, event_ts, label, e["desc"], event_dt_str)


if __name__ == "__main__":
    main()
