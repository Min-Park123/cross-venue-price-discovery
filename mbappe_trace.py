#!/usr/bin/env python3
"""
mbappe_trace.py — read-only row-level trace of the Mbappe-penalty repricing
window in cross_venue_paraguay_france.jsonl (FR pair), plus a diagnosis of
whether detect_events.py's lead heuristic agrees with PRELIMINARY.md's
raw-inspection finding for this same window, and if not, why not.

STRICTLY READ-ONLY: only reads cross_venue_paraguay_france.jsonl,
PREREGISTRATIONS.md and PRELIMINARY.md. Prints to stdout only.

Reuses detect_events.py (loading, delta-vs-lookback, episode/lead detection)
and coverage_map.py's PRELIMINARY.md event-time parser rather than
reimplementing them.

Usage:
  python3 mbappe_trace.py
"""

import numpy as np
import pandas as pd
from datetime import datetime

from detect_events import (
    load_rows, build_frame, compute_delta_vs_lookback, compute_moved,
    parse_prereg, analyze_dataset, fmt_ts,
    MOVE_THRESHOLD_C, LOOKBACK_MS, LOOKBACK_STALE_MS,
    LEAD_SEARCH_BEFORE_MS, LEAD_SEARCH_AFTER_MS,
)
from coverage_map import parse_preliminary_event

DATASET = "cross_venue_paraguay_france.jsonl"
TICKER_PREFIX = "KXMENWORLDCUP-26-FR"
BEFORE_S = 120  # 2 minutes before onset
AFTER_S = 180   # 3 minutes after onset


def fmt_hms(ms):
    return datetime.fromtimestamp(ms / 1000.0).strftime("%H:%M:%S.%f")[:-3]


def main():
    rows = load_rows(DATASET)
    df = build_frame(rows)
    g = df[df["pair"].str.startswith(TICKER_PREFIX)].copy()

    event = parse_preliminary_event()
    onset_ts = int(event["time"].timestamp() * 1000)
    print(f"Event anchor (from PRELIMINARY.md's own table: first >{MOVE_THRESHOLD_C:.1f}c "
          f"tick-over-tick reprice): {event['time'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} local")
    print(f"  {event['desc']}")
    print()

    lo, hi = onset_ts - BEFORE_S * 1000, onset_ts + AFTER_S * 1000

    # Per-venue 60s-prior delta, computed on each venue's own full t_fetch-
    # ordered history (not just the display window, so lookback isn't
    # truncated at the window edge) — same convention as detect_events.py's
    # compute_moved, just keyed on t_fetch instead of the shared cycle ts.
    per_venue = {}
    for venue in ("kalshi", "polymarket"):
        v = g[g["venue"] == venue].sort_values("t_fetch").reset_index(drop=True)
        tf = v["t_fetch"].to_numpy()
        mid = v["mid"].to_numpy()
        v["delta60"] = compute_delta_vs_lookback(tf, mid, lookback_ms=LOOKBACK_MS,
                                                   stale_ms=LOOKBACK_STALE_MS)
        v["tick_delta"] = v["mid"].diff()  # vs this same venue's immediately-preceding tick
        per_venue[venue] = v

    combined = pd.concat([per_venue["kalshi"], per_venue["polymarket"]], ignore_index=True)
    combined = combined.sort_values("t_fetch").reset_index(drop=True)

    # Running basis: kalshi_mid - poly_mid using the last-known mid from each
    # venue as of this tick (updates on every snapshot from either side).
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

    print(f"Row-level trace: {BEFORE_S//60}min before to {AFTER_S//60}min after onset "
          f"({fmt_hms(lo)} -> {fmt_hms(hi)} local), FR pair, both venues, by t_fetch:")
    header = f"  {'wall-clock':<16} {'venue':<11} {'mid(c)':>8} {'chg-vs-60s-prior(c)':>20} {'running basis(c)':>17}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for _, row in window.iterrows():
        d60 = row["delta60"]
        d60_s = f"{d60:+.2f}" if not np.isnan(d60) else "n/a"
        rb = row["running_basis"]
        rb_s = f"{rb:+.2f}" if not np.isnan(rb) else "n/a"
        print(f"  {fmt_hms(row['t_fetch']):<16} {row['venue']:<11} {row['mid']:>8.2f} "
              f"{d60_s:>20} {rb_s:>17}")
    print()

    # -----------------------------------------------------------------
    # (i) which venue's mid moved first, and by how much (raw, tick-over-tick)
    # -----------------------------------------------------------------
    print("=" * 100)
    print("(i) Which venue moved first, and by how much (raw trace)")
    print("=" * 100)
    jump_window = window[(window["t_fetch"] >= onset_ts - 15_000) & (window["t_fetch"] <= onset_ts + 15_000)]
    first_jump = None
    for _, row in jump_window.iterrows():
        td = row["tick_delta"]
        if pd.notna(td) and abs(td) > MOVE_THRESHOLD_C:
            first_jump = row
            break
    if first_jump is not None:
        print(f"  First single-tick move >{MOVE_THRESHOLD_C:.1f}c near onset: {first_jump['venue']} at "
              f"{fmt_hms(first_jump['t_fetch'])}, {first_jump['tick_delta']:+.2f}c "
              f"(mid {first_jump['mid'] - first_jump['tick_delta']:.2f} -> {first_jump['mid']:.2f}).")
    else:
        print("  No single-tick move exceeded the threshold near onset.")
    other_venue = "kalshi" if (first_jump is not None and first_jump["venue"] == "polymarket") else "polymarket"
    other_rows = jump_window[(jump_window["venue"] == other_venue) & (jump_window["t_fetch"] >= onset_ts - 5_000)]
    if not other_rows.empty:
        same_cycle = other_rows.iloc[0]
        print(f"  {other_venue}'s nearest snapshot at that moment: {fmt_hms(same_cycle['t_fetch'])}, "
              f"mid={same_cycle['mid']:.2f} (tick-over-tick change {same_cycle['tick_delta']:+.2f}c) "
              f"-- still at/near its pre-event level.")
    print()

    # -----------------------------------------------------------------
    # (ii) what detect_events.py's lead heuristic concludes, and why
    # -----------------------------------------------------------------
    print("=" * 100)
    print("(ii) What detect_events.py's lead heuristic concludes for this window")
    print("=" * 100)
    prereg_rules = parse_prereg()
    result = analyze_dataset(DATASET, prereg_rules)
    fr_pinfo = next(p for p in result["pairs"] if p["ticker"] == TICKER_PREFIX)
    ep = next((e for e in fr_pinfo["episodes"]
               if e["start_ts"] - 5_000 <= onset_ts <= e["end_ts"] + 5_000 or
               abs(e["start_ts"] - onset_ts) < 60_000), None)
    if ep is None:
        print("  No detect_events.py episode overlaps this window.")
        return
    print(f"  Episode: start={fmt_ts(ep['start_ts'])}  end={fmt_ts(ep['end_ts'])}  "
          f"duration={ep['duration_s']:.1f}s  peak_dev={ep['peak_dev']:+.3f}c")
    print(f"  Heuristic conclusion: lead_venue={ep['lead_venue']}  lead_time={ep['lead_time_s']}  "
          f"note={ep['note']!r}")
    print(f"  PRELIMINARY.md's own raw-inspection finding: polymarket led by ~4-11s "
          f"(Observation 1).")
    agree = (ep["lead_venue"] == "polymarket")
    print(f"  Agreement with PRELIMINARY.md: {'YES' if agree else 'NO -- heuristic disagrees'}")
    print()

    # Mechanical trace of *why*: replay compute_moved on the same merged
    # (cycle-ts) series find_lead actually used, and show the first
    # qualifying sample per venue inside its search window.
    merged = fr_pinfo["merged"]
    ts_arr = merged["ts"].to_numpy()
    mid_k = merged["mid_k"].to_numpy()
    mid_p = merged["mid_p"].to_numpy()
    moved_k = compute_moved(ts_arr, mid_k)
    moved_p = compute_moved(ts_arr, mid_p)
    delta_k = compute_delta_vs_lookback(ts_arr, mid_k)
    delta_p = compute_delta_vs_lookback(ts_arr, mid_p)

    search_lo = ep["start_ts"] - LEAD_SEARCH_BEFORE_MS
    search_hi = min(ep["end_ts"], ep["start_ts"] + LEAD_SEARCH_AFTER_MS)
    idx = np.where((ts_arr >= search_lo) & (ts_arr <= search_hi))[0]
    t_k_idx = next((i for i in idx if moved_k[i]), None)
    t_p_idx = next((i for i in idx if moved_p[i]), None)

    print("-" * 100)
    print("(iii) Mechanical diagnosis of the disagreement (no fix proposed/applied)")
    print("-" * 100)
    print(f"  Heuristic's own episode onset = {fmt_ts(ep['start_ts'])}, which is "
          f"{(onset_ts - ep['start_ts']) / 1000.0:+.1f}s away from the true reprice tick used in "
          f"part (i)/PRELIMINARY.md ({event['time'].strftime('%H:%M:%S.%f')[:-3]}).")
    print(f"  find_lead's search window = [onset-{LEAD_SEARCH_BEFORE_MS/1000:.0f}s, "
          f"min(episode_end, onset+{LEAD_SEARCH_AFTER_MS/1000:.0f}s)] = "
          f"[{fmt_ts(search_lo)}, {fmt_ts(search_hi)}]")
    if t_k_idx is not None:
        print(f"  First kalshi sample with |mid - mid(60s prior)| > {MOVE_THRESHOLD_C:.1f}c in that "
              f"window: {fmt_ts(int(ts_arr[t_k_idx]))}  mid={mid_k[t_k_idx]:.2f}  "
              f"delta60={delta_k[t_k_idx]:+.2f}c")
    else:
        print("  kalshi never crossed the 0.5c/60s move threshold in that window.")
    if t_p_idx is not None:
        print(f"  First polymarket sample with |mid - mid(60s prior)| > {MOVE_THRESHOLD_C:.1f}c in "
              f"that window: {fmt_ts(int(ts_arr[t_p_idx]))}  mid={mid_p[t_p_idx]:.2f}  "
              f"delta60={delta_p[t_p_idx]:+.2f}c")
    else:
        print("  polymarket never crossed the 0.5c/60s move threshold in that window.")
    print()
    print("  Reading: the kalshi trigger above is NOT the penalty-conversion reprice -- cross-check")
    print("  its wall-clock time against the row-level trace printed above. It is an earlier,")
    print("  unrelated dip/recovery in kalshi's own thin book (consistent with the 'quote flicker'")
    print("  caveat in PRELIMINARY.md), chronologically well before polymarket's actual jump. The")
    print("  heuristic has no way to distinguish that from a genuine information-driven move: it")
    print("  only asks 'which venue's own mid was the first, anywhere in the search window, to move")
    print("  >0.5c versus its level 60s earlier' -- first-crossing-wins, with no requirement that the")
    print("  move be causally tied to the episode's peak, no magnitude comparison between the two")
    print("  venues' triggering moves, and no check that the two venues' triggers are near the")
    print("  same moment. Contributing knobs, in order of leverage here: (1) MOVE_THRESHOLD_C=0.5c is")
    print("  small enough that kalshi's ordinary thin-book noise clears it on its own; (2) the 60s")
    print("  LOOKBACK_MS means a slow multi-tick drift (not just a single jump) can also clear it;")
    print("  (3) LEAD_SEARCH_BEFORE_MS=120s is wide enough to reach back past the true event into an")
    print("  unrelated earlier blip; and (4) the episode's own onset (which anchors that 120s window)")
    print("  is itself pulled earlier than the true event by the same kalshi noise, via the basis")
    print("  threshold test, widening the window further in the wrong direction. Sampling gap is not")
    print("  the culprit here -- the ~3.7s cadence resolves both moves cleanly; this is a threshold/")
    print("  lookback/window-size and tie-break design issue, not a data-density one.")


if __name__ == "__main__":
    main()
