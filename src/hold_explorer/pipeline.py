"""End-to-end: (generate sample) -> load -> clean -> features -> score -> evaluate -> write outputs."""
import argparse
import json
import os
from pathlib import Path

import pandas as pd

from .config import DEFAULT
from .clean import load_and_normalise, assign_flights, get_salt
from .features import build_features
from .detect import score_flights
from .evaluate import evaluate
from .sources import SPECS
from . import synth


def run(input_csv, spec_name, out_dir, labels_csv=None, keep_raw_ids=False, cfg=DEFAULT, report_path=None):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    spec = SPECS[spec_name]
    raw, qc = load_and_normalise(input_csv, spec, cfg)
    pos, callsigns = assign_flights(raw, cfg, keep_raw_ids=keep_raw_ids)
    pts, fl = build_features(pos, cfg)
    fl = score_flights(fl, cfg)
    if keep_raw_ids and callsigns is not None:
        fl = fl.merge(callsigns, on="flight_id", how="left")
    keep = ["flight_id", "ts", "lat", "lon", "alt_m", "gs_mps", "track_deg", "source", "is_estimated", "dist_km",
            "analyzed", "on_ground", "heading_deg", "turn_rate_dps", "no_progress"]
    pts[keep].to_csv(out / "positions.csv.gz", index=False, float_format="%.5f")
    fl.to_csv(out / "flights.csv", index=False)
    meta = dict(source=spec.name, attribution=spec.attribution, licence_note=spec.licence_note, qc=qc,
                airport=dict(icao=cfg.airport_icao, name=cfg.airport_name, lat=cfg.airport_lat, lon=cfg.airport_lon, radius_km=cfg.radius_km),
                salt_is_default=(get_salt() == "sample-salt-change-me"), raw_ids_kept=keep_raw_ids)
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    if labels_csv and os.path.exists(labels_csv):
        labels = pd.read_csv(labels_csv)
        note = "Source: " + spec.name + ". " + ("**Data is synthetic; labels are generator truth, not human review.**" if spec.name == "sample_synthetic" else "")
        rep = evaluate(fl, labels, qc, cfg, note)
        rp = Path(report_path or out.parent.parent / "reports" / "evaluation.md"); rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(rep)
    return pts, fl, qc


def main():
    ap = argparse.ArgumentParser(description="Hold-pattern review pipeline")
    ap.add_argument("--make-sample", action="store_true", help="generate synthetic sample data first")
    ap.add_argument("--input", default="data/sample/sample_adsb.csv")
    ap.add_argument("--spec", default="sample_synthetic", choices=list(SPECS))
    ap.add_argument("--labels", default="data/sample/labels.csv")
    ap.add_argument("--out", default="data/processed")
    ap.add_argument("--report", default="reports/evaluation.md")
    ap.add_argument("--keep-raw-ids", action="store_true", help="keep icao24/callsign (off by default; privacy)")
    a = ap.parse_args()
    if a.make_sample:
        Path(a.input).parent.mkdir(parents=True, exist_ok=True)
        n, k = synth.generate(a.input, a.labels)
        print(f"synthetic sample: {n} rows, {k} flights")
    _, fl, qc = run(a.input, a.spec, a.out, a.labels, a.keep_raw_ids, report_path=a.report)
    print(json.dumps(qc))
    print(fl["category"].value_counts().to_string())


if __name__ == "__main__":
    main()
