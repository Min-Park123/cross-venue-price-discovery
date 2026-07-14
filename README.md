# Cross-Venue Price Discovery in World Cup Prediction Markets

**Research question:** When new match information changes the value of a World Cup tournament-outright contract, which venue—Kalshi or Polymarket—incorporates it first?

The evidence does not identify one platform as universally faster. Instead, price discovery depends on the market regime. When both order books were active and the event was large enough to move the contract, Polymarket moved first in both cleanly adjudicated lead-follow cases (**n = 2**). In a thin longshot market, Kalshi repriced the Mexico contract while Polymarket remained stale for roughly four minutes. In event-insensitive longshot contracts, the information was worth less than the one-cent tick, so neither venue repriced and there was no lead to assign.

Data were collected from both public order-book APIs on a single local clock at an approximately 3.7-second cycle. Cross-venue divergence thresholds and baseline windows were publicly pre-registered before kickoff. Final lead verdicts were re-derived from raw bid, ask, midpoint, and spread traces rather than accepted from automated first-crossing estimators.

## Project status

**Complete.** The repository contains five recording sessions covering four World Cup Round of 16 matches and one quiet-window control.

## Read the study

- [Full writeup](WRITEUP.md)
- [Pre-registrations](PREREGISTRATIONS.md)
- [Preliminary n=1 observation](PRELIMINARY.md)
