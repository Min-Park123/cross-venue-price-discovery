#!/usr/bin/env python3
"""
event_lead_trace.py — EXPLORATORY, read-only venue-lead estimator.

*** EXPLORATORY (post-hoc estimator, not pre-registered). ***
This uses a different, independently-defined rule from detect_events.py's
committed-rule/lead heuristic: a fixed pre-window baseline (not a rolling
60s-prior lookback) and a 2-consecutive-sample confirmation (not a single
threshold cross). It is a second, deliberately different lens for sanity-
checking venue-lead calls, not a replacement rule and not pre-registered
anywhere. Treat all output here as exploratory.

STRICTLY READ-ONLY: only reads collector JSONL files, match_events_*.txt,
and PRELIMINARY.md. Prints to stdout only; never writes, appends, or
otherwise modifies any file.

Reuses detect_events.py's loading conventions and coverage_map.py's event-log
parsing / PRELIMINARY.md event derivation rather than reimplementing them.

Method, for each logged goal/penalty-kick/red-card (from the three event
logs) plus the Mbappe event from PRELIMINARY.md:
  - window = [event_time - 120s, event_time + 120s]
  - baseline[venue] = that venue's own mid at/just before window start
  - onset[venue] = first in-window timestamp where |mid - baseline| >= 1c
    for >=2 consecutive samples, same sign (a sustained, confirmed move)
  - lead venue = whichever onset is earlier; lead margin = the gap between
    the two onsets, in seconds
  - sampling interval = each venue's local median sample spacing near its
    own onset (the precision bound on that onset time)
  - flagged if either venue never reaches a confirmed move in the window

Usage:
  python3 event_lead_trace.py
"""

import numpy as np
from datetime import datetime
from pathlib import Path

from detect_events import load_rows, build_frame, fmt_ts
from coverage_map import (
    parse_event_log, merge_duplicate_sequences, is_substantive,
    parse_preliminary_event, fmt_event_time,
)

MOVE_THRESHOLD_C = 1.0
CONFIRM_SAMPLES = 2
WINDOW_S = 120

MATCHES = [
    ("cross_venue_mexico_england_main.jsonl", "match_events_mexico_england.txt"),
    ("cross_venue_portugal_spain_v3.jsonl", "match_events_portugal_spain.txt"),
    ("cross_venue_usa_belgium_v2.jsonl", "match_events_usa_belgium.txt"),
]


# ---------------------------------------------------------------------------
# Data loading: per-pair, per-venue (ts, mid) arrays
# ---------------------------------------------------------------------------
def load_pairs(dataset_path):
    rows = load_rows(dataset_path)
    df = build_frame(rows)
    pairs = {}
    for pair, g in df.groupby("pair"):
        ticker = pair.split(":", 1)[0]
        label = ticker.rsplit("-", 1)[-1]
        venues = {}
        for venue in ("kalshi", "polymarket"):
            v = g[g["venue"] == venue].sort_values("ts")
            venues[venue] = (v["ts"].to_numpy(), v["mid"].to_numpy())
        pairs[label] = venues
    return pairs


# ---------------------------------------------------------------------------
# Onset detection: fixed pre-window baseline, >=1c, >=2 consecutive samples
# ---------------------------------------------------------------------------
def find_onset(ts_arr, mid_arr, lo_ms, hi_ms, threshold=MOVE_THRESHOLD_C, confirm=CONFIRM_SAMPLES):
    """Returns (onset_ts, baseline, sampling_interval_s) or (None, baseline,
    sampling_interval_s) if the venue never confirms a move in-window.
    baseline is None if no pre-window sample exists at all."""
    base_idx = np.searchsorted(ts_arr, lo_ms, side="right") - 1
    if base_idx < 0:
        return None, None, None
    baseline = mid_arr[base_idx]

    idx_window = np.where((ts_arr >= lo_ms) & (ts_arr <= hi_ms))[0]
    if len(idx_window) == 0:
        return None, baseline, None
    diffs = np.diff(ts_arr[idx_window])
    sampling_interval_s = float(np.median(diffs)) / 1000.0 if len(diffs) else float("nan")

    dev = mid_arr[idx_window] - baseline
    for pos in range(len(idx_window) - confirm + 1):
        chunk = dev[pos:pos + confirm]
        if all(abs(d) >= threshold for d in chunk) and (all(d > 0 for d in chunk) or all(d < 0 for d in chunk)):
            onset_ts = int(ts_arr[idx_window[pos]])
            return onset_ts, baseline, sampling_interval_s
    return None, baseline, sampling_interval_s


# ---------------------------------------------------------------------------
# Per-event, per-pair report row
# ---------------------------------------------------------------------------
def analyze_event_pair(label, venues, event_dt):
    event_ts = int(event_dt.timestamp() * 1000)
    lo, hi = event_ts - WINDOW_S * 1000, event_ts + WINDOW_S * 1000
    onsets = {}
    for venue, (ts_arr, mid_arr) in venues.items():
        onset_ts, baseline, interval_s = find_onset(ts_arr, mid_arr, lo, hi)
        onsets[venue] = {"onset_ts": onset_ts, "baseline": baseline, "interval_s": interval_s}

    k, p = onsets["kalshi"], onsets["polymarket"]
    flagged = k["onset_ts"] is None or p["onset_ts"] is None
    lead_venue = lead_margin_s = None
    if not flagged:
        if k["onset_ts"] <= p["onset_ts"]:
            lead_venue, lead_margin_s = "kalshi", (p["onset_ts"] - k["onset_ts"]) / 1000.0
        else:
            lead_venue, lead_margin_s = "polymarket", (k["onset_ts"] - p["onset_ts"]) / 1000.0

    return {
        "pair_label": label, "kalshi": k, "polymarket": p,
        "lead_venue": lead_venue, "lead_margin_s": lead_margin_s, "flagged": flagged,
    }


def fmt_onset(o):
    if o["onset_ts"] is None:
        if o["baseline"] is None:
            return "NEVER QUALIFIES (no pre-window baseline sample)"
        return "NEVER QUALIFIES (no confirmed >=1c/2-sample move in window)"
    return fmt_ts(o["onset_ts"])


def print_row(row):
    print(f"    pair {row['pair_label']:<4} "
          f"kalshi_onset={fmt_onset(row['kalshi']):<45} "
          f"poly_onset={fmt_onset(row['polymarket']):<45}")
    ki = row["kalshi"]["interval_s"]
    pi = row["polymarket"]["interval_s"]
    ki_s = f"{ki:.1f}s" if ki is not None and not np.isnan(ki) else "n/a"
    pi_s = f"{pi:.1f}s" if pi is not None and not np.isnan(pi) else "n/a"
    print(f"      sampling interval near onset: kalshi~{ki_s}, polymarket~{pi_s}")
    if row["flagged"]:
        print("      >>> FLAGGED: at least one venue never confirms a qualifying move in this window <<<")
    else:
        print(f"      lead venue: {row['lead_venue']}   lead margin: {row['lead_margin_s']:.1f}s")
    print()


def main():
    print("*" * 100)
    print("EXPLORATORY (post-hoc estimator, not pre-registered)")
    print(f"Rule: within +/-{WINDOW_S}s of each logged event, per venue: baseline = own mid at/before "
          f"window start; onset = first time |mid-baseline| >= {MOVE_THRESHOLD_C:.1f}c for "
          f">= {CONFIRM_SAMPLES} consecutive samples (same sign). Independent of, and not directly "
          f"comparable to, detect_events.py's committed-rule/lead heuristic (different baseline, "
          f"threshold, and confirmation logic).")
    print("*" * 100)
    print()

    flagged_rows = []

    for dataset_path, events_path in MATCHES:
        pairs = load_pairs(dataset_path)
        events = merge_duplicate_sequences(parse_event_log(events_path))
        substantive = [e for e in events if is_substantive(e)]

        print("=" * 100)
        print(f"[EXPLORATORY] MATCH: {dataset_path}  (events: {events_path})")
        print("=" * 100)
        for e in substantive:
            print(f"  event {e['label']:<6} {fmt_event_time(e)}  '{e['desc']}'")
            for label, venues in pairs.items():
                row = analyze_event_pair(label, venues, e["time"])
                print_row(row)
                if row["flagged"]:
                    flagged_rows.append((dataset_path, e, row))
        print()

    # --- Mbappe event from PRELIMINARY.md (Paraguay-France, FR pair) ---
    print("=" * 100)
    print("[EXPLORATORY] MATCH: cross_venue_paraguay_france.jsonl  (event: PRELIMINARY.md, Mbappe penalty)")
    print("=" * 100)
    event = parse_preliminary_event()
    pairs = load_pairs("cross_venue_paraguay_france.jsonl")
    print(f"  event penalty {fmt_event_time(event)}  '{event['desc']}'")
    fr_venues = pairs.get("FR")
    if fr_venues is None:
        print("    [FR pair not found in dataset]")
    else:
        row = analyze_event_pair("FR", fr_venues, event["time"])
        print_row(row)
        if row["flagged"]:
            flagged_rows.append(("cross_venue_paraguay_france.jsonl", event, row))
    print()

    # --- Flag summary ---
    print("=" * 100)
    print("[EXPLORATORY] FLAGGED EVENTS (either venue never confirmed a qualifying move)")
    print("=" * 100)
    if not flagged_rows:
        print("  (none -- every event/pair had a confirmed onset for both venues)")
    else:
        for dataset_path, e, row in flagged_rows:
            print(f"  {Path(dataset_path).name:<38} event {e['label']:<6} {fmt_event_time(e)} "
                  f"pair {row['pair_label']}: kalshi={fmt_onset(row['kalshi'])} | "
                  f"polymarket={fmt_onset(row['polymarket'])}")


if __name__ == "__main__":
    main()
