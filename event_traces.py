#!/usr/bin/env python3
"""
event_traces.py — raw row-level traces for manual adjudication. No lead
heuristic, no onset detection, no conclusions of any kind.

STRICTLY READ-ONLY: only reads collector JSONL files and match_events_*.txt.
Prints to stdout only; never writes, appends, or otherwise modifies any file.

Same row-level trace format as mbappe_trace.py (wall-clock by t_fetch,
venue, mid, a delta column, running basis), except:
  - the delta column is versus each venue's own pre-window level (its mid
    at/just before event_time - 120s) rather than a rolling 60s-prior
    lookback
  - the window is +/-120s around the logged event time (symmetric)
  - nothing is flagged, thresholded, or concluded -- purely descriptive

Reuses detect_events.py's loading conventions and coverage_map.py's event-log
parsing rather than reimplementing them.

Events traced (both pairs, per match):
  - Mexico-England:  36' England Goal, 37' England Goal, 43' Mexico Goal
  - Portugal-Spain:  90' GOAL Spain (Merino)

Usage:
  python3 event_traces.py
"""

import numpy as np
import pandas as pd
from datetime import datetime

from detect_events import load_rows, build_frame
from coverage_map import parse_event_log, merge_duplicate_sequences

WINDOW_S = 120

EVENTS = [
    ("cross_venue_mexico_england_main.jsonl", "match_events_mexico_england.txt", "36'"),
    ("cross_venue_mexico_england_main.jsonl", "match_events_mexico_england.txt", "37'"),
    ("cross_venue_mexico_england_main.jsonl", "match_events_mexico_england.txt", "43'"),
    ("cross_venue_portugal_spain_v3.jsonl", "match_events_portugal_spain.txt", "90'"),
]


def fmt_hms(ms):
    return datetime.fromtimestamp(ms / 1000.0).strftime("%H:%M:%S.%f")[:-3]


def fmt_baseline(b):
    return f"{b:.2f}" if b is not None else "n/a"


def load_pairs(dataset_path):
    rows = load_rows(dataset_path)
    df = build_frame(rows)
    pairs = {}
    for pair, g in df.groupby("pair"):
        ticker = pair.split(":", 1)[0]
        label = ticker.rsplit("-", 1)[-1]
        pairs[label] = g
    return pairs


def build_trace(g, event_ts, window_s=WINDOW_S):
    lo, hi = event_ts - window_s * 1000, event_ts + window_s * 1000

    per_venue = {}
    baselines = {}
    for venue in ("kalshi", "polymarket"):
        v = g[g["venue"] == venue].sort_values("t_fetch").reset_index(drop=True)
        ts_arr = v["t_fetch"].to_numpy()
        base_idx = np.searchsorted(ts_arr, lo, side="right") - 1
        baseline = float(v["mid"].iloc[base_idx]) if base_idx >= 0 else None
        baselines[venue] = baseline
        v["delta_prewindow"] = (v["mid"] - baseline) if baseline is not None else np.nan
        per_venue[venue] = v

    combined = pd.concat(per_venue.values(), ignore_index=True).sort_values("t_fetch").reset_index(drop=True)

    # Running basis: kalshi_mid - poly_mid using the last-known mid from each
    # venue as of this tick (same convention as mbappe_trace.py).
    last_mid = {"kalshi": None, "polymarket": None}
    running_basis = []
    for _, row in combined.iterrows():
        last_mid[row["venue"]] = row["mid"]
        if last_mid["kalshi"] is not None and last_mid["polymarket"] is not None:
            running_basis.append(last_mid["kalshi"] - last_mid["polymarket"])
        else:
            running_basis.append(np.nan)
    combined["running_basis"] = running_basis

    window = combined[(combined["t_fetch"] >= lo) & (combined["t_fetch"] <= hi)].reset_index(drop=True)
    return window, baselines, lo, hi


def print_trace(pair_label, window, baselines, lo, hi):
    print(f"  pair {pair_label}:  pre-window baseline -- kalshi={fmt_baseline(baselines['kalshi'])}c, "
          f"polymarket={fmt_baseline(baselines['polymarket'])}c")
    print(f"  window {fmt_hms(lo)} -> {fmt_hms(hi)} local")
    header = (f"  {'wall-clock':<16} {'venue':<11} {'mid(c)':>8} "
              f"{'chg-vs-pre-window(c)':>21} {'running basis(c)':>17}")
    print(header)
    print("  " + "-" * (len(header) - 2))
    if window.empty:
        print("  (no rows in window)")
    for _, row in window.iterrows():
        d = row["delta_prewindow"]
        d_s = f"{d:+.2f}" if pd.notna(d) else "n/a"
        rb = row["running_basis"]
        rb_s = f"{rb:+.2f}" if pd.notna(rb) else "n/a"
        print(f"  {fmt_hms(row['t_fetch']):<16} {row['venue']:<11} {row['mid']:>8.2f} "
              f"{d_s:>21} {rb_s:>17}")
    print()


def main():
    print("Raw row-level traces only -- no lead heuristic, no conclusions. For manual adjudication.")
    print()
    for dataset_path, events_path, label in EVENTS:
        events = merge_duplicate_sequences(parse_event_log(events_path))
        e = next(ev for ev in events if ev["label"] == label)
        event_ts = int(e["time"].timestamp() * 1000)
        pairs = load_pairs(dataset_path)

        print("=" * 100)
        print(f"EVENT: {dataset_path}  {label}  {e['time'].strftime('%Y-%m-%d %H:%M:%S')} local  "
              f"'{e['desc']}'")
        print("=" * 100)
        for pair_label, g in pairs.items():
            window, baselines, lo, hi = build_trace(g, event_ts)
            print_trace(pair_label, window, baselines, lo, hi)


if __name__ == "__main__":
    main()
