# Explainable Flight-Pattern Anomaly Explorer

Flags **hold-like patterns** (circles / racetracks / repeated turns near one airport) in historical ADS-B
position data, explains *why* in plain language, compares against similar flights, and shows each track on a map.

> **An alert is a pattern worth reviewing - not proof of an emergency, fault, or wrongdoing.** Holding is routine
> (traffic spacing, weather, runway changes, training). This project does not detect emergencies and does not
> identify or profile people.

## Status (v0.1)
- Pipeline, scoring, evaluation and dashboard code are included. The synthetic generator creates reproducible sample flight data and processed outputs.
- In this review, Python syntax compilation passed. Runtime tests and dashboard launch could not be verified because this environment does not have pandas, NumPy, pytest, Streamlit, PyDeck, or Plotly installed. Install `requirements.txt` and rerun the checks before relying on the results.
- **No real ADS-B data is included.** All numbers in `reports/evaluation.md` come from generator-made data with generator
  truth labels. They are a smoke test, not an accuracy claim.

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/run_pipeline.py --make-sample     # synthetic data -> data/processed + reports/evaluation.md
streamlit run app.py
python -m pytest tests                           # or run tests/test_basic.py functions directly
```
Optional: `export HOLD_EXPLORER_SALT="<long random secret>"` before running on any real data (pseudonymous IDs).

## Role of Argos Atlas (and what we checked)
Argos Atlas (https://argosatlas.com/map/) is used **only by a human, in a browser, for manual context** (inspect a
flight, compare with nearby airports). I read its landing page and Terms (version 2026-11-07, retrieved 2026-11-09):
- No public API or bulk export is advertised for the free map; the Terms **prohibit scraping, unauthorised automation,
  bulk access and reuse beyond personal use**, except via a subscribed API within its quota, and prohibit monitoring or
  profiling specific individuals. Data exported via its API stays subject to originating-source licences.
- Therefore: **this code never calls Argos Atlas**, and no Argos data/screenshots are stored or redistributed.
  Re-read the Terms yourself before relying on this; they can change.

## Data source (replaceable)
`src/hold_explorer/sources.py` maps any CSV to the canonical schema (column names, timestamp kind, altitude/speed units,
estimated-position flag). Add a `SourceSpec` and run:
`python scripts/run_pipeline.py --input my.csv --spec my_spec --labels my_labels.csv`.
**Before collecting real data, confirm the provider's licence permits your use and redistribution. If unclear, pause and
use a source with explicit permission** (e.g. a research dataset with a clear licence, or your own receiver's logs).
Canonical fields: timestamp, lat, lon, altitude (m), ground speed (m/s), track, flight id, source, `is_estimated`.

## Method (all thresholds in `config.py`)
1. **Clean**: parse UTC time, convert ft/kt to SI, drop bad rows (counted in the QC log), de-duplicate, null implausible values.
2. **Group** reports into flights (same aircraft, silence < 30 min); pseudonymous ID = truncated HMAC-SHA256(salt, icao24|start).
   Raw icao24/callsign are dropped unless `--keep-raw-ids`.
3. **Scope**: score only flights with enough airborne in-radius samples, enough dwell, not mostly estimated, and not
   departure-like. Others are listed with the reason.
4. **Features** (inside the radius, airborne): heading sweep (max-min of unwrapped heading), self-overlap ratio (back within
   1.5 km of a spot flown >= 3 min earlier), no-progress minutes (6-min windows with < 1.5 km progress toward the airport
   *and* path efficiency < 0.6), turning episodes, dwell.
5. **Score** 0-100 = 0.4 sweep + 0.3 overlap + 0.3 no-progress (each scaled 0-1). >= 55 = hold-like, 30-55 weak signal.
6. **Peer comparison**: other scored flights entering within +/-3 h and +/-90 deg of entry bearing. If >= 30% of >= 3 peers
   are also hold-like, the category is "common among peers" (likely traffic/weather flow) instead of "unusual vs peers".
   Peer context re-labels; it never hides an alert.
7. **Explain**: each flag gets plain-language reasons plus data-quality notices (estimated positions, gaps, missing
   altitude/speed, heading disagreement). Observed vs estimated positions are drawn in different colours.

## Privacy notes
Pseudonymous IDs by default; no registrations, callsigns or owner data in outputs; do not publish raw identifiers or try to
link flights to people. Keep the salt secret. Aggregate/redact before sharing screenshots of real flights.

## Known limitations
See `reports/evaluation.md` section 4. Highlights: tiny/synthetic evaluation, hand-set thresholds, gaps hide turns,
no wind/airspace/procedure data, flat projection, single airport, go-arounds/training circuits can look like holds.

## Layout
`src/hold_explorer/` (clean, features, detect, evaluate, synth, sources, pipeline) - `scripts/run_pipeline.py` - `app.py` -
`tests/` - `data/sample` (synthetic CSV + labels) - `data/processed` - `reports/` - `data/labels_template.csv` for manual labels.

## Next steps
Manual-review labels (via the dashboard + Argos Atlas by hand), held-out evaluation, real licensed dataset, optional
Isolation Forest comparison, published-hold-fix data, per-runway-direction peers.
