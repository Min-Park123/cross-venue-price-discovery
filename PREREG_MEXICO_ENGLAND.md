# Pre-registration — Mexico vs. England

## Pre-match baseline — recorded 2026-07-05 17:19:28 local

```
Pre-match basis baseline — cross_venue_mexico_england.jsonl
generated 2026-07-05 17:19:28.861 local

pair: KXMENWORLDCUP-26-GB:115556263888245616435851357148058235707004733438163639091106356867234218207169
  n snapshots     : 247
  basis mean/std  : -0.560 / 0.447 cents
  basis min/max   : -1.900 / +0.100 cents
  timestamp range : 2026-07-05 16:54:17.917 -> 2026-07-05 17:09:37.925
  suggested event-detection threshold (mean +/- k*std):
    3-sigma: [-1.901, +0.781] cents
    4-sigma: [-2.348, +1.229] cents
    5-sigma: [-2.795, +1.676] cents
  COMMITTED RULE (GB): event = |basis - (-0.56¢)| > 1.79¢, sustained >=30s  [branch: 4-sigma]

pair: KXMENWORLDCUP-26-MX:22587775301869146748237913050505932485648958481571808324285560650057390882036
  n snapshots     : 247
  basis mean/std  : +1.288 / 0.284 cents
  basis min/max   : +0.400 / +1.650 cents
  timestamp range : 2026-07-05 16:54:17.917 -> 2026-07-05 17:09:37.925
  suggested event-detection threshold (mean +/- k*std):
    3-sigma: [+0.435, +2.140] cents
    4-sigma: [+0.151, +2.425] cents
    5-sigma: [-0.134, +2.709] cents
  COMMITTED RULE (MX): event = |basis - (+1.29¢)| > 1.14¢, sustained >=30s  [branch: 4-sigma]

```
