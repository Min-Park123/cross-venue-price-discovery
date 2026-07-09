#!/usr/bin/env python3
"""
coverage_map.py — read-only cross-reference of detect_events.py episodes
against logged match events.

STRICTLY READ-ONLY: only reads collector JSONL files, PREREGISTRATIONS.md,
match_events_*.txt, and PRELIMINARY.md. Prints to stdout only; never writes,
appends, or otherwise modifies any file.

Reuses detect_events.py's episode detection (same rule/threshold/sustain
logic, same merged basis series) rather than reimplementing it — see that
module for the authoritative definitions.

For each of the four match datasets (mexico_england_main, portugal_spain_v3,
usa_belgium_v2, paraguay_france) this prints three sections:
  (a) MATCHED        — episodes within +/-3 minutes of a logged event
  (b) UNEXPLAINED     — episodes with no logged event nearby, classified
                        pre-match / in-play / post-final-whistle
  (c) UNDETECTED      — logged goals/penalty-kicks/red cards with no nearby
                        episode, showing how close the basis came (max
                        |basis-anchor| and max sustained duration above
                        threshold in a +/-3 minute window around the event)

Usage:
  python3 coverage_map.py
"""

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from detect_events import (
    parse_prereg, analyze_dataset, find_episodes, fmt_ts, SUSTAIN_S,
)

MATCH_WINDOW_S = 180.0  # +/-3 minutes

# dataset -> event log (None => no txt log; handled via PRELIMINARY.md)
DATASETS = [
    ("cross_venue_mexico_england_main.jsonl", "match_events_mexico_england.txt"),
    ("cross_venue_portugal_spain_v3.jsonl", "match_events_portugal_spain.txt"),
    ("cross_venue_usa_belgium_v2.jsonl", "match_events_usa_belgium.txt"),
    ("cross_venue_paraguay_france.jsonl", None),
]

HEADER_DATE_RE = re.compile(r"([A-Z][a-z]{2})\s+(\d{1,2})\s+\d{2}:\d{2}:\d{2}\s+\S+\s+(\d{4})")
NON_MATCHABLE_LABELS = {"CORRECTION", "REFINE"}
WINDOW_LABELS = {"HT", "2H", "FT"}
SUBSTANTIVE_RE = re.compile(r"\bgoal\b|\bred card\b|\bpenalty kick\b", re.IGNORECASE)
VAR_RE = re.compile(r"\bVAR\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Event log parsing (handles both "HH:MM:SS" and "~HH:MM phone/approx" logs)
# ---------------------------------------------------------------------------
def parse_event_log(path):
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()
    m = HEADER_DATE_RE.search(lines[0])
    if not m:
        sys.exit(f"Could not find a header date in {path}")
    month_str, day_str, year_str = m.groups()
    base_date = datetime.strptime(f"{month_str} {day_str} {year_str}", "%b %d %Y").date()

    events = []
    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) != 3:
            continue
        label = parts[0].strip()
        timefield = parts[1].strip()
        desc = parts[2].strip()
        approx = timefield.startswith("~") or "approx" in timefield.lower()
        clean = timefield.lstrip("~").replace("phone/approx", "").strip()
        tm = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", clean)
        if not tm:
            continue
        h, mi, s = int(tm.group(1)), int(tm.group(2)), int(tm.group(3) or 0)
        approx = approx or tm.group(3) is None
        dt = datetime(base_date.year, base_date.month, base_date.day, h, mi, s)
        events.append({"label": label, "time": dt, "desc": desc, "approx": approx})
    return events


def merge_duplicate_sequences(events):
    """PRELIMINARY-adjacent log correction: mexico_england's CORRECTION note
    states the 67' Penalty Kick for Mexico and 68' Mexico Goal lines are one
    kick logged twice, not two events. Fold them into a single entry at the
    earlier (67') time so it isn't double-counted as two substantive events."""
    out = []
    skip_desc = None
    for e in events:
        if e["label"] == "67'" and "Penalty Kick for Mexico" in e["desc"]:
            skip_desc = "Mexico Goal"
            e = dict(e, desc=e["desc"] + " (67'->68' penalty converted, one sequence per log CORRECTION)")
        elif skip_desc and e["label"] == "68'" and skip_desc in e["desc"]:
            skip_desc = None
            continue
        out.append(e)
    return out


def is_substantive(e):
    if e["label"] in WINDOW_LABELS or e["label"] in NON_MATCHABLE_LABELS:
        return False
    if VAR_RE.search(e["desc"]):
        return False
    return bool(SUBSTANTIVE_RE.search(e["desc"]))


def matchable_events(events):
    return [e for e in events if e["label"] not in NON_MATCHABLE_LABELS]


def fmt_event_time(e):
    t = e["time"].strftime("%H:%M:%S")
    return f"~{t} (approx, minute precision)" if e["approx"] else t


# ---------------------------------------------------------------------------
# PRELIMINARY.md — the single Paraguay-France logged event (Mbappe penalty)
# ---------------------------------------------------------------------------
TABLE_ROW_RE = re.compile(
    r"\|\s*(\d{2}:\d{2}:\d{2}\.\d+)\s*\|\s*(\w+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|"
)
TITLE_DATE_RE = re.compile(r"(\d{1,2})\s+(\w+)\s+(\d{4})")


def parse_preliminary_event(path="PRELIMINARY.md", move_threshold=0.5):
    """Derives the Mbappe-penalty event time from PRELIMINARY.md's own
    Observation-1 table: the first row where a venue's mid changes by more
    than move_threshold cents versus that same venue's previous row in the
    table (i.e. the first visible repricing tick, read straight off the
    table rather than assumed)."""
    text = Path(path).read_text(encoding="utf-8")
    date_m = TITLE_DATE_RE.search(text.splitlines()[0])
    day, month_name, year = date_m.groups()
    base_date = datetime.strptime(f"{day} {month_name} {year}", "%d %B %Y").date()
    rows = TABLE_ROW_RE.findall(text)
    last_mid = {}
    for time_str, venue, mid_str, _spread in rows:
        mid = float(mid_str)
        if venue in last_mid and abs(mid - last_mid[venue]) > move_threshold:
            h, mi, s = time_str.split(":")
            sec, ms = s.split(".")
            dt = datetime(base_date.year, base_date.month, base_date.day,
                           int(h), int(mi), int(sec), int(ms) * 1000)
            return {"label": "penalty", "time": dt,
                    "desc": f"Mbappe penalty converted (~69'-70'); first >{move_threshold:.1f}c "
                            f"reprice per PRELIMINARY.md Observation 1 ({venue} {last_mid[venue]:+.2f}"
                            f"->{mid:+.2f})",
                    "approx": False}
        last_mid[venue] = mid
    sys.exit("Could not derive an event time from PRELIMINARY.md's table")


# ---------------------------------------------------------------------------
# Window classification (pre-match / in-play / post-final-whistle)
# ---------------------------------------------------------------------------
def classify_window(start_dt, events, fallback_cutoff=None):
    matchable = matchable_events(events)
    if not matchable:
        if fallback_cutoff is not None:
            return ("pre-match" if start_dt < fallback_cutoff else
                    "in-play/post-match (no event log available to split these)")
        return "unclassified (no event log)"
    inplay_start = min(e["time"] for e in matchable)
    ft = next((e["time"] for e in matchable if e["label"] == "FT"), None)
    if start_dt < inplay_start:
        return "pre-match"
    if ft is not None and start_dt > ft:
        return "post-final-whistle/settlement"
    return "in-play"


# ---------------------------------------------------------------------------
# Per-event basis stats in a +/-window around a wall-clock time
# ---------------------------------------------------------------------------
def event_window_stats(pinfo, event_dt, window_s=MATCH_WINDOW_S):
    merged = pinfo["merged"]
    anchor, threshold = pinfo["anchor"], pinfo["threshold"]
    event_ts = int(event_dt.timestamp() * 1000)
    lo, hi = event_ts - window_s * 1000, event_ts + window_s * 1000
    sub = merged[(merged["ts"] >= lo) & (merged["ts"] <= hi)]
    if sub.empty:
        return {"pair_label": pinfo["label"], "n": 0, "max_abs_dev": None, "max_sustained_s": 0.0}
    ts_arr = sub["ts"].to_numpy()
    signed_dev = (sub["basis"] - anchor).to_numpy()
    max_abs_idx = int(np.argmax(np.abs(signed_dev)))
    runs = find_episodes(ts_arr, signed_dev, threshold, sustain_s=0.0)
    max_sustained = max((r["duration_s"] for r in runs), default=0.0)
    return {
        "pair_label": pinfo["label"], "n": len(sub),
        "max_abs_dev": float(signed_dev[max_abs_idx]), "max_sustained_s": max_sustained,
        "threshold": threshold,
    }


def print_event_stats_table(pinfos, event_dt, indent="      "):
    header = f"{indent}{'Pair':<6} {'max |basis-anchor|(c)':>22} {'max sustained>thr(s)':>21} {'threshold(c)':>13}"
    print(header)
    for pinfo in pinfos:
        stats = event_window_stats(pinfo, event_dt)
        if stats["max_abs_dev"] is None:
            print(f"{indent}{stats['pair_label']:<6} {'no data in window':>22}")
            continue
        print(f"{indent}{stats['pair_label']:<6} {stats['max_abs_dev']:>22.3f} "
              f"{stats['max_sustained_s']:>21.1f} {stats['threshold']:>13.2f}")


# ---------------------------------------------------------------------------
# Main per-match report
# ---------------------------------------------------------------------------
def analyze_match(dataset_path, events_path, prereg_rules):
    result = analyze_dataset(dataset_path, prereg_rules)
    pinfos = [p for p in result["pairs"] if not p.get("skipped")]
    all_episodes = sorted(
        (ep for p in pinfos for ep in p["episodes"]), key=lambda e: e["start_ts"])

    if events_path is not None:
        raw_events = merge_duplicate_sequences(parse_event_log(events_path))
        fallback_cutoff = None
    else:
        raw_events = [parse_preliminary_event()]
        cutoff_date = raw_events[0]["time"].date()
        fallback_cutoff = datetime.combine(cutoff_date, datetime.min.time().replace(hour=18))

    matchable = matchable_events(raw_events)
    substantive = [e for e in raw_events if is_substantive(e)] if events_path else raw_events

    print("=" * 100)
    print(f"MATCH: {dataset_path}" + (f"  (events: {events_path})" if events_path else
                                        "  (event: PRELIMINARY.md, Mbappe penalty -- sole logged event)"))
    print("=" * 100)

    # --- (a) MATCHED -------------------------------------------------------
    print("(a) MATCHED  (episode start within +/-3 min of a logged event)")
    matched_episode_ids = set()
    any_matched = False
    for ep in all_episodes:
        ep_dt = datetime.fromtimestamp(ep["start_ts"] / 1000.0)
        # signed_off > 0 means the episode started AFTER the logged event; < 0 means before it
        hits = [(e, (ep_dt - e["time"]).total_seconds()) for e in matchable]
        hits = [(e, off) for e, off in hits if abs(off) <= MATCH_WINDOW_S]
        if hits:
            any_matched = True
            matched_episode_ids.add(id(ep))
            hits.sort(key=lambda x: abs(x[1]))
            desc = "; ".join(
                f"{e['label']} {fmt_event_time(e)} '{e['desc']}' "
                f"(episode {off:+.0f}s vs event)"
                for e, off in hits)
            print(f"    {ep['pair_label']:<4} {fmt_ts(ep['start_ts']):<24} "
                  f"dur={ep['duration_s']:>6.1f}s peak={ep['peak_dev']:>+7.3f}c  <-> {desc}")
    if not any_matched:
        print("    (none)")
    print()

    # --- (b) UNEXPLAINED EPISODES -------------------------------------------
    print("(b) UNEXPLAINED EPISODES  (no logged event within +/-3 min)")
    unexplained = [ep for ep in all_episodes if id(ep) not in matched_episode_ids]
    if not all_episodes:
        print("    0 episodes detected in this dataset.")
        if "usa_belgium" in dataset_path:
            goal_events = [e for e in substantive if "goal" in e["desc"].lower()]
            n_be = sum(1 for e in goal_events if "belgium" in e["desc"].lower())
            n_us = sum(1 for e in goal_events if "usa" in e["desc"].lower())
            print(f"    {len(goal_events)} logged goals ({n_be} Belgium + {n_us} USA, matching the "
                  f"final 1-4 score), but the committed-rule basis never sustained a >threshold "
                  f"deviation for >={SUSTAIN_S:.0f}s. Max |basis-anchor| and max sustained-above-"
                  f"threshold span in a +/-3min window around each goal:")
            for e in goal_events:
                print(f"      goal {e['label']} {fmt_event_time(e)} '{e['desc']}':")
                print_event_stats_table(pinfos, e["time"])
    elif not unexplained:
        print("    (none -- every episode matched a logged event)")
    else:
        for ep in unexplained:
            ep_dt = datetime.fromtimestamp(ep["start_ts"] / 1000.0)
            window = classify_window(ep_dt, raw_events, fallback_cutoff)
            print(f"    {ep['pair_label']:<4} {fmt_ts(ep['start_ts']):<24} "
                  f"dur={ep['duration_s']:>7.1f}s peak={ep['peak_dev']:>+7.3f}c  window={window}")
    print()

    # --- (c) UNDETECTED EVENTS ----------------------------------------------
    print("(c) UNDETECTED EVENTS  (logged goal/penalty-kick/red-card with no episode within +/-3 min)")
    undetected = []
    for e in substantive:
        hit = any(abs((datetime.fromtimestamp(ep["start_ts"] / 1000.0) - e["time"]).total_seconds())
                  <= MATCH_WINDOW_S for ep in all_episodes)
        if not hit:
            undetected.append(e)
    if not undetected:
        print("    (none -- every logged goal/penalty-kick/red-card had a matching episode)")
    else:
        for e in undetected:
            print(f"    {e['label']:<5} {fmt_event_time(e)}  '{e['desc']}'")
            print_event_stats_table(pinfos, e["time"])
    print()
    return {"dataset": dataset_path, "n_episodes": len(all_episodes),
            "n_matched": len(matched_episode_ids), "n_unexplained": len(unexplained),
            "n_substantive": len(substantive), "n_undetected": len(undetected)}


def main():
    prereg_rules = parse_prereg()
    summaries = [analyze_match(ds, ev, prereg_rules) for ds, ev in DATASETS]

    print("=" * 100)
    print("CROSS-MATCH SUMMARY")
    print("=" * 100)
    header = (f"  {'Match':<38} {'Episodes':>9} {'Matched':>8} {'Unexplained':>12} "
              f"{'Logged evts':>12} {'Undetected':>11}")
    print(header)
    print("  " + "-" * (len(header) - 2))
    for s in summaries:
        print(f"  {Path(s['dataset']).name:<38} {s['n_episodes']:>9} {s['n_matched']:>8} "
              f"{s['n_unexplained']:>12} {s['n_substantive']:>12} {s['n_undetected']:>11}")


if __name__ == "__main__":
    main()
