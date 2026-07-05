# Preliminary Observation — Paraguay vs. France (R16, 4 July 2026)

**Status: n=1. One event, one match, one venue pair. This is an anecdote, not an
information share. It motivates the VECM / Hasbrouck analysis; it does not
replace it.**

## Event

Mbappé penalty (awarded ~69', converted 70'), the match's only goal. Both
venues' France tournament-winner books were recorded on a single clock at
~3.7s per cycle, with intra-cycle fetch skew of ~125ms (recorded per row).

## Observation 1 — Polymarket led the reprice by ~4–11 seconds

| time (local)  | venue      | mid   | spread |
|---------------|------------|-------|--------|
| 15:30:03.231  | polymarket | 32.15 | 0.10   |
| 15:30:06.799  | kalshi     | 30.85 | 0.10   |
| 15:30:06.924  | polymarket | 33.65 | 0.30   |
| 15:30:10.493  | kalshi     | 31.25 | 0.10   |
| 15:30:14.212  | kalshi     | 31.95 | 1.50   |
| 15:30:17.954  | kalshi     | 32.70 | 0.20   |

At 15:30:06.799 Kalshi still shows the pre-event price; 125ms later Polymarket
has fully repriced (+1.50c in one snapshot). Kalshi's first partial move comes
3.7s after Polymarket's jump and full convergence takes ~11s. The lead exceeds
the recorded fetch skew by two orders of magnitude.

## Observation 2 — Jump vs. staircase

Polymarket incorporated the event in a single discrete jump. Kalshi adjusted in
a staircase (30.85 → 31.25 → 31.95 → 32.70) with its quoted spread widening to
1.50c mid-transition — consistent with the diffusion/withdrawal behavior
documented on Kalshi in the prequel study (kalshi-mm-study).

## Observation 3 — Live-play basis

During live play preceding the event, a persistent ~1.3–1.5c cross-venue basis
held (Polymarket pinned at 32.35 for >2 minutes while Kalshi oscillated
30.5–32.35), versus a −0.30c gap measured pre-match. The cross-venue arbitrage
tether appears looser during live play, and Kalshi's top-of-book is the noisier
of the two.

## Caveats

- Single event; no statistical claim is made or should be inferred.
- Mid-move detection on Kalshi's thin book is contaminated by quote flicker
  (single resting orders pulling/restoring move the mid >1c); event windows
  were verified by raw inspection, not scanner output alone.
- Tournament-winner contracts attenuate match-level information; magnitudes
  understate what a matched moneyline pair would show.

Next: replicate on Portugal–Spain (6 July), then alignment layer, cointegration
tests, VECM, and Hasbrouck / Gonzalo–Granger information shares across the full
sessions.
