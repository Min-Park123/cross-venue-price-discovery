#!/usr/bin/env python3
"""
prematch_baseline.py — pre-match cross-venue basis baseline from a collector
JSONL file (see cross_venue_collector.py for the schema this reads).

For each contract pair present in the file, pairs up the nearest Kalshi and
Polymarket snapshots by timestamp, computes basis = kalshi_mid - poly_mid in
cents, and reports summary stats plus a suggested 3/4/5-sigma event-detection
threshold. The threshold is also appended to PREREG_MEXICO_ENGLAND.md with a
wall-clock timestamp, so it's committed to the repo before kickoff.

Usage:
  python3 prematch_baseline.py [path/to/collector_output.jsonl]
"""

import json
import os
import sys
from datetime import datetime

import pandas as pd

DEFAULT_INFILE = "cross_venue_mexico_england.jsonl"
PREREG_FILE = "PREREG_MEXICO_ENGLAND.md"


def load_rows(path):
    rows = []
    skipped = 0
    with open(path) as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                # last line of a live-written file is often a partial write
                skipped += 1
    if skipped:
        print(f"[warn] skipped {skipped} malformed/partial line(s) in {path}")
    return rows


def build_frame(rows):
    df = pd.DataFrame(rows)
    needed = {"ts", "venue", "pair", "bid", "ask"}
    missing = needed - set(df.columns)
    if missing:
        sys.exit(f"Input is missing expected field(s): {sorted(missing)}")
    df = df.dropna(subset=["bid", "ask"])
    df["mid"] = (df["bid"] + df["ask"]) / 2.0
    return df


def fmt_ts(ms):
    return datetime.fromtimestamp(ms / 1000.0).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def pair_label(pair):
    ticker = pair.split(":", 1)[0]
    return ticker.rsplit("-", 1)[-1]


def pair_stats(df):
    results = []
    for pair, g in df.groupby("pair"):
        k = g[g["venue"] == "kalshi"].sort_values("ts")
        p = g[g["venue"] == "polymarket"].sort_values("ts")
        if k.empty or p.empty:
            print(f"[warn] {pair}: missing one venue's snapshots, skipping")
            continue
        merged = pd.merge_asof(k, p, on="ts", direction="nearest",
                                suffixes=("_k", "_p"))
        merged["basis"] = merged["mid_k"] - merged["mid_p"]
        merged = merged.dropna(subset=["basis"])
        if merged.empty:
            print(f"[warn] {pair}: no valid paired snapshots, skipping")
            continue
        mean = merged["basis"].mean()
        std = merged["basis"].std()
        four_sigma = 4 * std
        threshold = max(four_sigma, 1.0)
        branch = "4-sigma" if four_sigma >= 1.0 else "1-cent floor"
        results.append({
            "pair": pair,
            "label": pair_label(pair),
            "n": len(merged),
            "mean": mean,
            "std": std,
            "min": merged["basis"].min(),
            "max": merged["basis"].max(),
            "ts_start": merged["ts"].min(),
            "ts_end": merged["ts"].max(),
            "threshold": threshold,
            "branch": branch,
        })
    return results


def format_report(results, infile):
    lines = []
    lines.append(f"Pre-match basis baseline — {infile}")
    lines.append(f"generated {fmt_ts(int(datetime.now().timestamp() * 1000))} local")
    lines.append("")
    for r in results:
        lines.append(f"pair: {r['pair']}")
        lines.append(f"  n snapshots     : {r['n']}")
        lines.append(f"  basis mean/std  : {r['mean']:+.3f} / {r['std']:.3f} cents")
        lines.append(f"  basis min/max   : {r['min']:+.3f} / {r['max']:+.3f} cents")
        lines.append(f"  timestamp range : {fmt_ts(r['ts_start'])} -> {fmt_ts(r['ts_end'])}")
        lines.append("  suggested event-detection threshold (mean +/- k*std):")
        for k in (3, 4, 5):
            lo = r["mean"] - k * r["std"]
            hi = r["mean"] + k * r["std"]
            lines.append(f"    {k}-sigma: [{lo:+.3f}, {hi:+.3f}] cents")
        lines.append(
            f"  COMMITTED RULE ({r['label']}): event = |basis - ({r['mean']:+.2f}¢)| "
            f"> {r['threshold']:.2f}¢, sustained >=30s  [branch: {r['branch']}]"
        )
        lines.append("")
    return "\n".join(lines)


def append_prereg(report, path=PREREG_FILE):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = f"\n## Pre-match baseline — recorded {stamp} local\n\n```\n"
    footer = "\n```\n"
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write("# Pre-registration — Mexico vs. England\n")
    with open(path, "a") as f:
        f.write(header)
        f.write(report)
        f.write(footer)
    print(f"\nAppended baseline to {path}")


def main():
    infile = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INFILE
    rows = load_rows(infile)
    if not rows:
        sys.exit(f"No parseable rows in {infile}")
    df = build_frame(rows)
    results = pair_stats(df)
    if not results:
        sys.exit("No contract pair had snapshots from both venues.")
    report = format_report(results, infile)
    print(report)
    append_prereg(report)


if __name__ == "__main__":
    main()
