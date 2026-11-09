# Evaluation report

> **Read this first.** An alert is a *pattern worth reviewing*, not proof of an emergency, fault or wrongdoing. Holds are routine. Source: sample_synthetic. **Data is synthetic; labels are generator truth, not human review.**

## 1. Data coverage

- Time span: 2026-09-14 to 2026-10-04 (20.6 days)
- Raw rows: 21571; after QC: 21563
  - dropped_missing_ts_or_position: 0
  - dropped_out_of_range_latlon: 1
  - dropped_null_island: 1
  - dropped_duplicates: 6
  - speed_set_missing_implausible: 0
  - altitude_set_missing_implausible: 0
- Flights reconstructed: 332; scored: 284 (86%)
  - excluded: departure-like flight (holds are an arrival-phase pattern): 42
  - excluded: fewer than 40 position reports: 4
  - excluded: mostly estimated (not observed) positions: 2
- Scored flights with confidence low/medium/high: 0/34/250

## 2. Detection vs labels

- Labelled flights: 289 (25 hold, 264 normal); of these scored: 284. Label sources: synthetic_generator_truth
- 5 labelled flight(s) were not scored (insufficient data): 0 of them are labelled hold (counted as missed in the recall below).

| Threshold | TP | FP | FN | TN | Precision | Recall |
|---|---|---|---|---|---|---|
| 40 | 25 | 0 | 0 | 264 | 1.00 | 1.00 |
| 50 | 24 | 0 | 1 | 264 | 1.00 | 0.96 |
| 55 (default) | 24 | 0 | 1 | 264 | 1.00 | 0.96 |
| 60 | 24 | 0 | 1 | 264 | 1.00 | 0.96 |
| 70 | 23 | 0 | 2 | 264 | 1.00 | 0.92 |

### Breakdown by scenario (default threshold)

| Scenario | n | scored | flagged hold-like | median score |
|---|---|---|---|---|
| departure | 43 | 0 | 0 | n/a |
| dogleg | 51 | 51 | 0 | 0 |
| hold_congestion | 7 | 7 | 7 | 76 |
| hold_isolated | 18 | 18 | 17 | 76 |
| long_vector | 28 | 27 | 0 | 2 |
| overflight | 67 | 65 | 0 | 0 |
| straight | 118 | 116 | 0 | 0 |

### False positives (0) and false negatives (1)

- False negative: `F-3e2be318` scenario=hold_isolated, score=47.424749163879596 (sweep 756 deg, revisit 8%, no-progress 0 min)

## 3. Effect of peer comparison

Hold-like flights: 24. Category split: Hold-like (unusual vs peers): 9; Hold-like (no peer context): 8; Hold-like (common among peers): 7.
- Congestion-window holds labelled common among peers: 5/7
- Isolated holds labelled unusual vs peers: 7/17

## 4. Limitations

- Small sample; metrics on a synthetic or tiny manually reviewed set say little about real-world performance. Do not quote them as accuracy.
- Synthetic ground truth comes from the generator, not from human review; real labels must be added (see README, `data/labels_template.csv`).
- Thresholds were set by hand and then checked on the same sample - expect optimism. Use a held-out set before changing them.
- Peer context can hide genuine anomalies when many flights share a pattern; it down-ranks, it never deletes alerts.
- Reporting gaps hide turns (loops may be under-counted); estimated positions are not observations.
- Local flat projection, no wind, no airspace/procedure data: published holding fixes and published hold shapes are not used.
- Departure-like flights are excluded; go-arounds and training circuits can look hold-like.
- Single-airport study; parameters (radius, windows) were not tuned for other airports.
