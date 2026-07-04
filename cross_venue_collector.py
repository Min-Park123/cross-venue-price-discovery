#!/usr/bin/env python3
"""
cross_venue_collector.py — synchronized Kalshi + Polymarket order-book recorder.

Collection layer for the cross-venue price discovery study:
which venue leads when the same World Cup outcome reprices?

DESIGN PRINCIPLE — ONE CLOCK:
Each cycle fetches Kalshi then Polymarket back-to-back and stamps every row
from the same local clock. Cross-venue lead/lag is only measurable if both
feeds share a timestamp source; two independent recorders would make the
core question (who moved first?) unanswerable. Intra-cycle skew between the
two fetches is recorded per-row (t_fetch) so it can be bounded in analysis.

NO AUTH NEEDED on either venue for market data:
  Kalshi     GET https://api.elections.kalshi.com/trade-api/v2/markets/{t}/orderbook
  Polymarket GET https://clob.polymarket.com/book?token_id={id}
  Polymarket discovery: Gamma API https://gamma-api.polymarket.com (public)

USAGE
  python3 cross_venue_collector.py selftest
      Offline check: parse synthetic books from both venues' real formats,
      confirm both normalize to the same (bid, ask, mid, spread) cents schema.

  python3 cross_venue_collector.py discover --query "world cup"
      Search Polymarket's Gamma API for matching events/markets and print
      each market's outcome names and CLOB token IDs. Use this to find the
      Polymarket token that corresponds to a Kalshi ticker.

  python3 cross_venue_collector.py peek --kalshi TICKER --poly TOKEN_ID
      One synchronized fetch of both books, printed side by side.
      The calibration gate: run this BEFORE any recording session.

  python3 cross_venue_collector.py record --pairs KALSHI_TICKER:POLY_TOKEN_ID ... \
                                     --minutes 180 --outfile cross_venue.jsonl
      Poll all pairs each cycle. One row per venue per pair per cycle.

OUTPUT SCHEMA (one JSON object per line)
  ts        local wall-clock ms at cycle start (shared across the cycle)
  t_fetch   local wall-clock ms just before THIS venue's HTTP request
  venue     "kalshi" | "polymarket"
  pair      the KALSHI_TICKER:POLY_TOKEN_ID string (join key across venues)
  bid, ask, mid, spread   in CENTS (float, subpenny preserved)
  bid_sz, ask_sz          size at touch, venue-native units
  venue_ts  venue-reported book timestamp, if provided (Polymarket has one)

Everything downstream (alignment, VECM, information shares) reads this file.
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.parse
import urllib.error

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
POLY_CLOB = "https://clob.polymarket.com"
POLY_GAMMA = "https://gamma-api.polymarket.com"

POLL_SECONDS = 3
REQUEST_TIMEOUT = 10
DEFAULT_OUTFILE = "cross_venue.jsonl"


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _get(url, params=None):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "xvenue-study/1.0"})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# KALSHI SIDE — bid-only book, reconstruct the ask from NO bids.
# Same parsing as kalshi_mm_probe.py (orderbook_fp / *_dollars, subpenny).
# ---------------------------------------------------------------------------
def _k_norm(p):
    if p is None:
        return None
    v = float(p)
    cents = v * 100.0 if v <= 1.0 else v
    return round(cents, 4)


def _k_best(levels):
    best_p, best_sz = None, None
    for lvl in levels or []:
        p = _k_norm(lvl[0])
        if p is None:
            continue
        if best_p is None or p > best_p:
            best_p, best_sz = p, (lvl[1] if len(lvl) > 1 else None)
    return best_p, best_sz


def parse_kalshi_book(raw):
    """raw = the API response for /markets/{t}/orderbook. Returns cents TOB."""
    ob = raw.get("orderbook_fp") or raw.get("orderbook") or raw
    yes_bid, bid_sz = _k_best(ob.get("yes_dollars") or ob.get("yes"))
    no_bid, ask_sz = _k_best(ob.get("no_dollars") or ob.get("no"))
    ask = round(100 - no_bid, 4) if no_bid is not None else None
    mid = spread = None
    if yes_bid is not None and ask is not None:
        mid = round((yes_bid + ask) / 2.0, 4)
        spread = round(ask - yes_bid, 4)
    return {"bid": yes_bid, "ask": ask, "mid": mid, "spread": spread,
            "bid_sz": bid_sz, "ask_sz": ask_sz, "venue_ts": None}


def fetch_kalshi(ticker):
    return parse_kalshi_book(_get(f"{KALSHI_BASE}/markets/{ticker}/orderbook"))


# ---------------------------------------------------------------------------
# POLYMARKET SIDE — natively two-sided book, dollar-string prices in [0,1].
# Levels arrive as {"price": "0.45", "size": "100"} dicts.
# NOTE (verify at peek time): docs' examples show bids in descending order,
# but we take max(bids)/min(asks) rather than trusting ordering.
# ---------------------------------------------------------------------------
def _p_cents(p):
    if p is None:
        return None
    return round(float(p) * 100.0, 4)


def parse_poly_book(raw):
    """raw = /book response. Returns cents TOB in the same schema as Kalshi."""
    best_bid, bid_sz = None, None
    for lvl in raw.get("bids") or []:
        p = _p_cents(lvl.get("price"))
        if p is not None and (best_bid is None or p > best_bid):
            best_bid, bid_sz = p, lvl.get("size")
    best_ask, ask_sz = None, None
    for lvl in raw.get("asks") or []:
        p = _p_cents(lvl.get("price"))
        if p is not None and (best_ask is None or p < best_ask):
            best_ask, ask_sz = p, lvl.get("size")
    mid = spread = None
    if best_bid is not None and best_ask is not None:
        mid = round((best_bid + best_ask) / 2.0, 4)
        spread = round(best_ask - best_bid, 4)
    return {"bid": best_bid, "ask": best_ask, "mid": mid, "spread": spread,
            "bid_sz": bid_sz, "ask_sz": ask_sz,
            "venue_ts": raw.get("timestamp")}


def fetch_poly(token_id):
    return parse_poly_book(_get(f"{POLY_CLOB}/book", {"token_id": token_id}))


# ---------------------------------------------------------------------------
# DISCOVER — Polymarket Gamma API, public text search over events/markets.
# ---------------------------------------------------------------------------
def discover(query, limit=20):
    data = _get(f"{POLY_GAMMA}/events",
                {"active": "true", "closed": "false", "limit": limit,
                 "title": query})
    events = data if isinstance(data, list) else data.get("events", data.get("data", []))
    if not events:
        print("No active events matched. Try a broader --query.")
        return
    for ev in events:
        print("=" * 70)
        print(f"EVENT: {ev.get('title', '?')}   slug={ev.get('slug', '?')}")
        for m in ev.get("markets", []):
            outcomes = m.get("outcomes")
            tokens = m.get("clobTokenIds")
            # Gamma sometimes serializes these as JSON strings
            if isinstance(outcomes, str):
                try: outcomes = json.loads(outcomes)
                except Exception: pass
            if isinstance(tokens, str):
                try: tokens = json.loads(tokens)
                except Exception: pass
            print(f"  MARKET: {m.get('question', m.get('slug', '?'))}")
            if outcomes and tokens and len(outcomes) == len(tokens):
                for o, t in zip(outcomes, tokens):
                    print(f"    {o:<12} token_id={t}")
            else:
                print(f"    outcomes={outcomes}")
                print(f"    clobTokenIds={tokens}")


# ---------------------------------------------------------------------------
# PEEK — one synchronized cycle, printed. The calibration gate.
# ---------------------------------------------------------------------------
def peek(kalshi_ticker, poly_token):
    t0 = int(time.time() * 1000)
    tk = int(time.time() * 1000)
    k = fetch_kalshi(kalshi_ticker)
    tp = int(time.time() * 1000)
    p = fetch_poly(poly_token)
    t1 = int(time.time() * 1000)
    print(f"cycle start {t0} | kalshi fetch @+{tk - t0}ms | poly fetch @+{tp - t0}ms "
          f"| cycle {t1 - t0}ms total")
    print(f"{'':12}{'bid':>10}{'ask':>10}{'mid':>10}{'spread':>10}")
    for name, b in (("KALSHI", k), ("POLYMARKET", p)):
        f = lambda x: f"{x:.2f}" if isinstance(x, (int, float)) else "None"
        print(f"{name:<12}{f(b['bid']):>10}{f(b['ask']):>10}{f(b['mid']):>10}{f(b['spread']):>10}")
    if k["mid"] is not None and p["mid"] is not None:
        print(f"\ncross-venue mid gap: {k['mid'] - p['mid']:+.2f} cents "
              "(should be small if these are truly the same outcome)")
    else:
        print("\n[!] one venue returned an incomplete book — check the IDs.")


# ---------------------------------------------------------------------------
# RECORD — the synchronized loop.
# ---------------------------------------------------------------------------
def record(pairs, minutes, outfile=DEFAULT_OUTFILE):
    parsed = []
    for pr in pairs:
        k, _, p = pr.partition(":")
        if not k or not p:
            sys.exit(f"Bad --pairs entry '{pr}' (need KALSHI_TICKER:POLY_TOKEN_ID)")
        parsed.append((pr, k, p))
    deadline = time.time() + minutes * 60
    n = 0
    print(f"Recording {len(parsed)} pair(s) for {minutes} min "
          f"every {POLL_SECONDS}s -> {outfile}", flush=True)
    with open(outfile, "a") as f:
        while time.time() < deadline:
            ts = int(time.time() * 1000)
            for pair, ktick, ptok in parsed:
                for venue, fetch, ident in (("kalshi", fetch_kalshi, ktick),
                                            ("polymarket", fetch_poly, ptok)):
                    t_fetch = int(time.time() * 1000)
                    try:
                        tob = fetch(ident)
                    except Exception as e:
                        print(f"  [warn] {venue}:{ident}: {e}",
                              file=sys.stderr, flush=True)
                        continue
                    row = {"ts": ts, "t_fetch": t_fetch, "venue": venue,
                           "pair": pair, **tob}
                    f.write(json.dumps(row) + "\n")
                    n += 1
            f.flush()
            time.sleep(POLL_SECONDS)
    print(f"Done. Wrote {n} rows to {outfile}.", flush=True)


# ---------------------------------------------------------------------------
# SELF-TEST — both venues' real response shapes, offline.
# ---------------------------------------------------------------------------
def selftest():
    print("Offline self-test: parsing both venues' documented formats...\n")

    # Kalshi fixed-point shape (verified live on 2 July)
    kalshi_raw = {"orderbook_fp": {
        "yes_dollars": [["0.3430", "93.00"], ["0.3400", "500.00"]],
        "no_dollars":  [["0.6500", "69023.07"], ["0.6000", "100.00"]]}}
    k = parse_kalshi_book(kalshi_raw)
    k_ok = (k["bid"] == 34.30 and k["ask"] == 35.00
            and k["mid"] == 34.65 and k["spread"] == 0.70)
    print(f"KALSHI      -> {k}")
    print(f"  expect bid 34.30 / ask 35.00 / mid 34.65 / spread 0.70 : "
          f"{'PASS' if k_ok else 'FAIL'}\n")

    # Polymarket documented shape (deliberately shuffled level order,
    # since we must not trust venue-side sorting)
    poly_raw = {"timestamp": "1234567890",
                "bids": [{"price": "0.44", "size": "200"},
                         {"price": "0.45", "size": "100"}],
                "asks": [{"price": "0.47", "size": "250"},
                         {"price": "0.46", "size": "150"}]}
    p = parse_poly_book(poly_raw)
    p_ok = (p["bid"] == 45.0 and p["ask"] == 46.0
            and p["mid"] == 45.5 and p["spread"] == 1.0)
    print(f"POLYMARKET  -> {p}")
    print(f"  expect bid 45.00 / ask 46.00 / mid 45.50 / spread 1.00 : "
          f"{'PASS' if p_ok else 'FAIL'}\n")

    ok = k_ok and p_ok
    print("SELF-TEST", "PASS ✔" if ok else "FAIL ✗",
          "— both venues normalize to one comparable cents schema.")
    return ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="Synchronized Kalshi+Polymarket order-book recorder (read-only).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("selftest")

    d = sub.add_parser("discover")
    d.add_argument("--query", required=True)
    d.add_argument("--limit", type=int, default=20)

    pk = sub.add_parser("peek")
    pk.add_argument("--kalshi", required=True)
    pk.add_argument("--poly", required=True)

    r = sub.add_parser("record")
    r.add_argument("--pairs", nargs="+", required=True,
                   help="KALSHI_TICKER:POLY_TOKEN_ID (one or more)")
    r.add_argument("--minutes", type=float, default=180)
    r.add_argument("--outfile", default=DEFAULT_OUTFILE)

    args = ap.parse_args()
    if args.cmd == "selftest":
        sys.exit(0 if selftest() else 1)
    if args.cmd == "discover":
        discover(args.query, args.limit)
        return
    if args.cmd == "peek":
        peek(args.kalshi, args.poly)
        return
    if args.cmd == "record":
        record(args.pairs, args.minutes, args.outfile)
        return


if __name__ == "__main__":
    main()
