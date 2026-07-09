#!/usr/bin/env python3
"""
detect_events.py — read-only cross-venue basis event detector.

STRICTLY READ-ONLY: this script only reads its input files (collector JSONL
files, PREREGISTRATIONS.md) and prints to stdout. It never writes, appends,
or otherwise modifies any file.

Schema and pairing/mid/basis conventions are reused as-is from
cross_venue_collector.py (row schema: ts, t_fetch, venue, pair, bid, ask,
mid, spread, ...) and prematch_baseline.py (nearest-timestamp venue pairing,
basis = kalshi_mid - poly_mid, pair label = ticker suffix after the last
"-"). See those files for the authoritative definitions.

For each dataset given on the command line:
  1. Parse the committed rule for each pair from PREREGISTRATIONS.md
     (matched by ticker). If no block exists for a ticker, fall back to the
     default retrospective rule: |basis - pre-match mean| > 1c sustained
     >=30s, with the mean computed from rows timestamped before 18:00 local
     on the date of that dataset's first row.
  2. Flag every episode where |basis - anchor| exceeds the threshold for a
     sustained run of >=30s (by wall-clock span of the contiguous exceeding
     samples, not sample count).
  3. For each episode, find which venue's own mid moved materially (>0.5c
     relative to its level 60s earlier) first, and report the lead venue
     and lead time in seconds, bounded by that pair's local sampling
     interval.
  4. Print a per-dataset episode table, then a combined summary table.

Usage:
  python3 detect_events.py FILE.jsonl [FILE2.jsonl ...]
"""

import argparse
import re
import statistics
import sys
from datetime import datetime, time as dtime, date
from pathlib import Path

import numpy as np
import pandas as pd

PREREG_FILE = "PREREGISTRATIONS.md"

DEFAULT_THRESHOLD_C = 1.0     # cents — default/retrospective rule
SUSTAIN_S = 30.0              # seconds — minimum sustained span to count as an episode
MOVE_THRESHOLD_C = 0.5        # cents — "materially moved" for lead detection
LOOKBACK_MS = 60_000          # own-mid lookback window for "moved" test
LOOKBACK_STALE_MS = 90_000    # don't use a lookback sample staler than this
LEAD_SEARCH_BEFORE_MS = 120_000  # how far before episode onset to look for a move
LEAD_SEARCH_AFTER_MS = 120_000   # how far after episode onset to look for a move


# ---------------------------------------------------------------------------
# Loading (mirrors prematch_baseline.py's load_rows/build_frame conventions)
# ---------------------------------------------------------------------------
def load_rows(path):
    rows, skipped = [], 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(__import__("json").loads(line))
            except ValueError:
                skipped += 1
    if skipped:
        print(f"[warn] {path}: skipped {skipped} malformed/partial line(s)", file=sys.stderr)
    return rows


def build_frame(rows):
    df = pd.DataFrame(rows)
    needed = {"ts", "venue", "pair", "bid", "ask"}
    missing = needed - set(df.columns)
    if missing:
        sys.exit(f"Input is missing expected field(s): {sorted(missing)}")
    df = df.dropna(subset=["bid", "ask"]).copy()
    df["mid"] = (df["bid"] + df["ask"]) / 2.0
    return df


def pair_ticker(pair):
    return pair.split(":", 1)[0]


def pair_label(pair):
    return pair_ticker(pair).rsplit("-", 1)[-1]


def fmt_ts(ms):
    return datetime.fromtimestamp(ms / 1000.0).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


# ---------------------------------------------------------------------------
# Pre-registration parsing (read-only)
# ---------------------------------------------------------------------------
PAIR_LINE_RE = re.compile(r"^pair:\s*([^:\s]+):")
RULE_LINE_RE = re.compile(
    r"COMMITTED RULE \(([^)]+)\):\s*event\s*=\s*\|basis\s*-\s*\(([+-][\d.]+)¢\)\|\s*>\s*"
    r"([\d.]+)¢,\s*sustained\s*>=30s"
)


def parse_prereg(path=PREREG_FILE):
    """Returns {ticker: {"label", "anchor", "threshold"}} parsed from the
    committed-rule lines in PREREGISTRATIONS.md. Read-only; never touches
    the file otherwise."""
    rules = {}
    p = Path(path)
    if not p.exists():
        return rules
    text = p.read_text(encoding="utf-8")
    current_ticker = None
    for line in text.splitlines():
        m_pair = PAIR_LINE_RE.match(line.strip())
        if m_pair:
            current_ticker = m_pair.group(1)
            continue
        m_rule = RULE_LINE_RE.search(line)
        if m_rule and current_ticker:
            label, anchor, threshold = m_rule.groups()
            rules[current_ticker] = {
                "label": label, "anchor": float(anchor), "threshold": float(threshold),
            }
            current_ticker = None
    return rules


# ---------------------------------------------------------------------------
# Episode detection
# ---------------------------------------------------------------------------
def find_episodes(ts_arr, signed_dev, threshold, sustain_s=SUSTAIN_S):
    """ts_arr: sorted ms epoch array. signed_dev: basis - anchor, same length.
    An episode is a maximal run of consecutive samples with |signed_dev| >
    threshold whose wall-clock span (last ts - first ts) is >= sustain_s."""
    episodes = []
    n = len(ts_arr)
    i = 0
    while i < n:
        if abs(signed_dev[i]) > threshold:
            j = i
            while j + 1 < n and abs(signed_dev[j + 1]) > threshold:
                j += 1
            duration_s = (ts_arr[j] - ts_arr[i]) / 1000.0
            if duration_s >= sustain_s:
                peak_idx = i + int(np.argmax(np.abs(signed_dev[i:j + 1])))
                episodes.append({
                    "start_ts": int(ts_arr[i]), "end_ts": int(ts_arr[j]),
                    "duration_s": duration_s,
                    "peak_dev": float(signed_dev[peak_idx]),
                    "peak_ts": int(ts_arr[peak_idx]),
                })
            i = j + 1
        else:
            i += 1
    return episodes


def compute_delta_vs_lookback(ts_arr, mid_arr, lookback_ms=LOOKBACK_MS, stale_ms=LOOKBACK_STALE_MS):
    """delta[i] = mid_arr[i] minus mid at the nearest sample at/before
    ts_arr[i] - lookback_ms. NaN where no such sample exists within stale_ms."""
    n = len(ts_arr)
    delta = np.full(n, np.nan)
    for i in range(n):
        target = ts_arr[i] - lookback_ms
        j = np.searchsorted(ts_arr, target, side="right") - 1
        if j < 0:
            continue
        if ts_arr[i] - ts_arr[j] > stale_ms:
            continue
        delta[i] = mid_arr[i] - mid_arr[j]
    return delta


def compute_moved(ts_arr, mid_arr, move_threshold=MOVE_THRESHOLD_C):
    """Boolean array: did mid move by more than move_threshold cents versus
    its ~60s-prior level (nearest sample at/before that lookback target)."""
    delta = compute_delta_vs_lookback(ts_arr, mid_arr)
    return np.abs(delta) > move_threshold


def find_lead(ts_arr, moved_k, moved_p, onset_ts, end_ts, sampling_interval_s):
    lo = onset_ts - LEAD_SEARCH_BEFORE_MS
    hi = min(end_ts, onset_ts + LEAD_SEARCH_AFTER_MS)
    idx = np.where((ts_arr >= lo) & (ts_arr <= hi))[0]
    t_k = next((int(ts_arr[i]) for i in idx if moved_k[i]), None)
    t_p = next((int(ts_arr[i]) for i in idx if moved_p[i]), None)
    precision = f"+/-{sampling_interval_s:.1f}s (local sampling interval)"
    if t_k is None and t_p is None:
        return {"lead_venue": None, "lead_time_s": None,
                "note": f"neither venue showed a >{MOVE_THRESHOLD_C:.1f}c move vs 60s-prior in window"}
    if t_k is not None and t_p is not None:
        if t_k <= t_p:
            lead_venue, lead_ts, lag_ts = "kalshi", t_k, t_p
        else:
            lead_venue, lead_ts, lag_ts = "polymarket", t_p, t_k
        return {"lead_venue": lead_venue, "lead_time_s": (lag_ts - lead_ts) / 1000.0,
                "note": precision}
    lead_venue = "kalshi" if t_k is not None else "polymarket"
    other = "polymarket" if lead_venue == "kalshi" else "kalshi"
    return {"lead_venue": lead_venue, "lead_time_s": None,
            "note": f"{other} showed no qualifying move in window; {precision}"}


# ---------------------------------------------------------------------------
# Per-pair analysis
# ---------------------------------------------------------------------------
def analyze_pair(pair, g, prereg_rules):
    ticker = pair_ticker(pair)
    label = pair_label(pair)
    k = g[g["venue"] == "kalshi"].sort_values("ts")
    p = g[g["venue"] == "polymarket"].sort_values("ts")
    if k.empty or p.empty:
        return {"ticker": ticker, "label": label, "skipped":
                 "missing one venue's snapshots"}

    merged = pd.merge_asof(k[["ts", "mid"]], p[["ts", "mid"]], on="ts",
                            direction="nearest", suffixes=("_k", "_p"))
    merged = merged.dropna(subset=["mid_k", "mid_p"]).sort_values("ts").reset_index(drop=True)
    if merged.empty:
        return {"ticker": ticker, "label": label, "skipped": "no valid paired snapshots"}
    merged["basis"] = merged["mid_k"] - merged["mid_p"]

    rule = prereg_rules.get(ticker)
    if rule:
        anchor = rule["anchor"]
        threshold = rule["threshold"]
        rule_source = f"committed rule (PREREGISTRATIONS.md, label {rule['label']})"
    else:
        cutoff_date = datetime.fromtimestamp(merged["ts"].iloc[0] / 1000.0).date()
        cutoff_ts = int(datetime.combine(cutoff_date, dtime(18, 0, 0)).timestamp() * 1000)
        pre = merged[merged["ts"] < cutoff_ts]
        used = pre if not pre.empty else merged
        anchor = float(used["basis"].mean())
        threshold = DEFAULT_THRESHOLD_C
        fallback_note = "" if not pre.empty else " (no rows before 18:00 found; used full file)"
        rule_source = (f"retrospective rule (default |basis-mean|>{DEFAULT_THRESHOLD_C:.2f}c, "
                        f"mean={anchor:+.3f}c from n={len(used)} rows before 18:00 local "
                        f"{cutoff_date.isoformat()}{fallback_note})")

    ts_arr = merged["ts"].to_numpy()
    mid_k_arr = merged["mid_k"].to_numpy()
    mid_p_arr = merged["mid_p"].to_numpy()
    signed_dev = (merged["basis"] - anchor).to_numpy()

    diffs = np.diff(ts_arr)
    sampling_interval_s = float(np.median(diffs)) / 1000.0 if len(diffs) else float("nan")

    episodes_raw = find_episodes(ts_arr, signed_dev, threshold)

    episodes = []
    if episodes_raw:
        moved_k = compute_moved(ts_arr, mid_k_arr)
        moved_p = compute_moved(ts_arr, mid_p_arr)
        for ep in episodes_raw:
            lead = find_lead(ts_arr, moved_k, moved_p, ep["start_ts"], ep["end_ts"],
                              sampling_interval_s)
            episodes.append({"pair_label": label, "ticker": ticker, **ep, **lead,
                              "sampling_interval_s": sampling_interval_s})

    return {
        "ticker": ticker, "label": label, "anchor": anchor, "threshold": threshold,
        "rule_source": rule_source, "n_merged": len(merged),
        "sampling_interval_s": sampling_interval_s, "episodes": episodes,
        "merged": merged,
    }


# ---------------------------------------------------------------------------
# Dataset-level analysis + printing
# ---------------------------------------------------------------------------
def analyze_dataset(path, prereg_rules):
    rows = load_rows(path)
    if not rows:
        return {"dataset": path, "n_rows": 0, "pairs": []}
    df = build_frame(rows)
    pairs = []
    for pair, g in df.groupby("pair"):
        pairs.append(analyze_pair(pair, g, prereg_rules))
    return {"dataset": path, "n_rows": len(df), "pairs": pairs}


def print_dataset_table(result):
    print("=" * 100)
    print(f"DATASET: {result['dataset']}  (n rows = {result['n_rows']})")
    print("=" * 100)
    if not result["pairs"]:
        print("  [no parseable rows]")
        return

    all_episodes = []
    for pinfo in result["pairs"]:
        if pinfo.get("skipped"):
            print(f"  pair {pinfo['label']} ({pinfo['ticker']}): skipped — {pinfo['skipped']}")
            continue
        print(f"  pair {pinfo['label']} ({pinfo['ticker']}): n paired snapshots = "
              f"{pinfo['n_merged']}, sampling interval ~= {pinfo['sampling_interval_s']:.1f}s")
        print(f"    rule: {pinfo['rule_source']}")
        print(f"    anchor = {pinfo['anchor']:+.3f}c, threshold = {pinfo['threshold']:.2f}c, "
              f"sustain >= {SUSTAIN_S:.0f}s")
        all_episodes.extend(pinfo["episodes"])

    print()
    if not all_episodes:
        print("  >>> No sustained episodes detected in this dataset. <<<")
        print()
        return

    all_episodes.sort(key=lambda e: e["start_ts"])
    header = (f"  {'Pair':<6} {'Start (local)':<24} {'Dur(s)':>7} {'Peak dev(c)':>12} "
              f"{'Lead venue':<11} {'Lead(s)':>8}  Notes")
    print(header)
    print("  " + "-" * (len(header) - 2))
    for ep in all_episodes:
        lead_time = f"{ep['lead_time_s']:.1f}" if ep["lead_time_s"] is not None else "n/a"
        lead_venue = ep["lead_venue"] or "none"
        print(f"  {ep['pair_label']:<6} {fmt_ts(ep['start_ts']):<24} {ep['duration_s']:>7.1f} "
              f"{ep['peak_dev']:>+12.3f} {lead_venue:<11} {lead_time:>8}  {ep['note']}")
    print()


def print_combined_summary(all_results):
    print("=" * 100)
    print("COMBINED SUMMARY (across all datasets)")
    print("=" * 100)
    header = (f"  {'Dataset':<38} {'Episodes':>9} {'Kalshi lead':>12} {'Poly lead':>10} "
              f"{'No lead':>8} {'Median lead(s)':>15}")
    print(header)
    print("  " + "-" * (len(header) - 2))

    grand_episodes = []
    for result in all_results:
        episodes = [ep for pinfo in result["pairs"] if not pinfo.get("skipped")
                    for ep in pinfo["episodes"]]
        grand_episodes.extend(episodes)
        k_leads = sum(1 for e in episodes if e["lead_venue"] == "kalshi")
        p_leads = sum(1 for e in episodes if e["lead_venue"] == "polymarket")
        no_lead = sum(1 for e in episodes if e["lead_venue"] is None)
        lead_times = [e["lead_time_s"] for e in episodes if e["lead_time_s"] is not None]
        median_lead = f"{statistics.median(lead_times):.1f}" if lead_times else "n/a"
        name = Path(result["dataset"]).name
        print(f"  {name:<38} {len(episodes):>9} {k_leads:>12} {p_leads:>10} "
              f"{no_lead:>8} {median_lead:>15}")

    k_leads = sum(1 for e in grand_episodes if e["lead_venue"] == "kalshi")
    p_leads = sum(1 for e in grand_episodes if e["lead_venue"] == "polymarket")
    no_lead = sum(1 for e in grand_episodes if e["lead_venue"] is None)
    lead_times = [e["lead_time_s"] for e in grand_episodes if e["lead_time_s"] is not None]
    median_lead = f"{statistics.median(lead_times):.1f}" if lead_times else "n/a"
    print("  " + "-" * (len(header) - 2))
    print(f"  {'TOTAL':<38} {len(grand_episodes):>9} {k_leads:>12} {p_leads:>10} "
          f"{no_lead:>8} {median_lead:>15}")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="Read-only cross-venue basis event detector (never writes to any file).")
    ap.add_argument("datasets", nargs="+", help="collector JSONL file(s) to analyze")
    ap.add_argument("--prereg", default=PREREG_FILE,
                    help=f"pre-registration markdown file, read-only (default: {PREREG_FILE})")
    args = ap.parse_args()

    prereg_rules = parse_prereg(args.prereg)

    all_results = []
    for path in args.datasets:
        result = analyze_dataset(path, prereg_rules)
        all_results.append(result)
        print_dataset_table(result)

    print_combined_summary(all_results)


if __name__ == "__main__":
    main()
