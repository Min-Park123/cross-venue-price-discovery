# Cross-Venue Price Discovery: Kalshi vs. Polymarket

Which venue leads price discovery when the same 2026 World Cup outcome trades
simultaneously on a CFTC-regulated exchange (Kalshi) and a decentralized
prediction market (Polymarket)?

Method: synchronized order-book collection from both venues (single-clock
recorder), cointegration testing, VECM estimation, and Hasbrouck information
shares / Gonzalo-Granger decomposition of price discovery.

**Status: data collection in progress** (World Cup knockout rounds, July 2026).
Collection window closes with the final on July 19.

Prequel: [kalshi-mm-study](https://github.com/Min-Park123/kalshi-mm-study) —
established that market-making within Kalshi is fee-bound on liquid books;
this study asks where the information that moves those books arrives first.

## Files
- `cross_venue_collector.py` — synchronized two-venue recorder (offline
  self-test: `python3 cross_venue_collector.py selftest`)
- `cross_venue_paraguay_france.jsonl` — synchronized two-venue session,
  Paraguay–France R16 (10,672 rows, clean collection)
- `PRELIMINARY.md` — first event-window observation (n=1)
