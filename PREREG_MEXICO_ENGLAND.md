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

## Pre-match baseline — recorded 2026-07-06 11:48:50 local

```
Pre-match basis baseline — cross_venue_portugal_spain_v3.jsonl
generated 2026-07-06 11:48:50.271 local

pair: KXMENWORLDCUP-26-ES:4394372887385518214471608448209527405727552777602031099972143344338178308080
  n snapshots     : 61
  basis mean/std  : +0.893 / 0.036 cents
  basis min/max   : +0.700 / +0.900 cents
  timestamp range : 2026-07-06 11:45:13.873 -> 2026-07-06 11:48:46.471
  suggested event-detection threshold (mean +/- k*std):
    3-sigma: [+0.786, +1.001] cents
    4-sigma: [+0.750, +1.037] cents
    5-sigma: [+0.714, +1.073] cents
  COMMITTED RULE (ES): event = |basis - (+0.89¢)| > 1.00¢, sustained >=30s  [branch: 1-cent floor]

pair: KXMENWORLDCUP-26-PT:45415751658241142530386585138386640503488308219341470020075667342738719018629
  n snapshots     : 61
  basis mean/std  : +0.570 / 0.046 cents
  basis min/max   : +0.500 / +0.600 cents
  timestamp range : 2026-07-06 11:45:13.873 -> 2026-07-06 11:48:46.471
  suggested event-detection threshold (mean +/- k*std):
    3-sigma: [+0.433, +0.708] cents
    4-sigma: [+0.387, +0.754] cents
    5-sigma: [+0.341, +0.800] cents
  COMMITTED RULE (PT): event = |basis - (+0.57¢)| > 1.00¢, sustained >=30s  [branch: 1-cent floor]

```

## Pre-match baseline — recorded 2026-07-06 16:30:59 local

```
Pre-match basis baseline — cross_venue_usa_belgium_v2.jsonl
generated 2026-07-06 16:30:59.424 local

pair: KXMENWORLDCUP-26-BE:30815807067456631524510535002617106205417832891402132396713720656146245200000
  n snapshots     : 274
  basis mean/std  : +0.100 / 0.000 cents
  basis min/max   : +0.100 / +0.100 cents
  timestamp range : 2026-07-06 16:14:42.508 -> 2026-07-06 16:30:58.065
  suggested event-detection threshold (mean +/- k*std):
    3-sigma: [+0.100, +0.100] cents
    4-sigma: [+0.100, +0.100] cents
    5-sigma: [+0.100, +0.100] cents
  COMMITTED RULE (BE): event = |basis - (+0.10¢)| > 1.00¢, sustained >=30s  [branch: 1-cent floor]

pair: KXMENWORLDCUP-26-US:94603648636330087039501304492699481091005420017442244191603206509188088089447
  n snapshots     : 274
  basis mean/std  : +0.500 / 0.030 cents
  basis min/max   : +0.400 / +0.600 cents
  timestamp range : 2026-07-06 16:14:42.508 -> 2026-07-06 16:30:58.065
  suggested event-detection threshold (mean +/- k*std):
    3-sigma: [+0.411, +0.589] cents
    4-sigma: [+0.382, +0.619] cents
    5-sigma: [+0.352, +0.649] cents
  COMMITTED RULE (US): event = |basis - (+0.50¢)| > 1.00¢, sustained >=30s  [branch: 1-cent floor]

```
