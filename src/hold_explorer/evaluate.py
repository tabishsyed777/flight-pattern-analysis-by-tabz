"""Evaluation against labelled flights + markdown report writer."""
import numpy as np
import pandas as pd

from .config import Config, DEFAULT


def _prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else float("nan")
    r = tp / (tp + fn) if tp + fn else float("nan")
    return p, r


def evaluate(fl: pd.DataFrame, labels: pd.DataFrame, qc: dict, cfg: Config = DEFAULT, source_note: str = "") -> str:
    m = fl.merge(labels, on="flight_id", how="left")
    lab = m[m["label"].isin(["hold", "normal"])]
    sc = lab[lab["scored"]]
    L = []
    L.append("# Evaluation report\n")
    L.append("> **Read this first.** An alert is a *pattern worth reviewing*, not proof of an emergency, fault or wrongdoing. "
             "Holds are routine. " + (source_note or "") + "\n")
    # ---- coverage
    days = (fl["end_ts"].max() - fl["start_ts"].min()).total_seconds() / 86400
    L.append("## 1. Data coverage\n")
    L.append(f"- Time span: {fl['start_ts'].min():%Y-%m-%d} to {fl['end_ts'].max():%Y-%m-%d} ({days:.1f} days)")
    L.append(f"- Raw rows: {qc.get('rows_in', 'n/a')}; after QC: {qc.get('rows_after_qc', 'n/a')}")
    for k, v in qc.items():
        if k.startswith(("dropped", "speed", "altitude")):
            L.append(f"  - {k}: {v}")
    L.append(f"- Flights reconstructed: {len(fl)}; scored: {int(fl['scored'].sum())} ({fl['scored'].mean():.0%})")
    ex = fl.loc[~fl["scored"], "excluded_reason"].value_counts()
    for k, v in ex.items():
        L.append(f"  - excluded: {k}: {v}")
    L.append(f"- Scored flights with confidence low/medium/high: "
             f"{int((fl.confidence == 'low').sum())}/{int((fl.confidence == 'medium').sum())}/{int((fl.confidence == 'high').sum())}\n")
    # ---- metrics
    L.append("## 2. Detection vs labels\n")
    L.append(f"- Labelled flights: {len(lab)} ({int((lab.label == 'hold').sum())} hold, {int((lab.label == 'normal').sum())} normal); "
             f"of these scored: {len(sc)}. Label sources: {', '.join(sorted(lab['label_source'].dropna().unique())) or 'n/a'}")
    miss_unscored = lab[~lab["scored"]]
    if len(miss_unscored):
        L.append(f"- {len(miss_unscored)} labelled flight(s) were not scored (insufficient data): "
                 f"{int((miss_unscored.label == 'hold').sum())} of them are labelled hold (counted as missed in the recall below).")
    L.append("\n| Threshold | TP | FP | FN | TN | Precision | Recall |\n|---|---|---|---|---|---|---|")
    for th in [40, 50, cfg.hold_threshold, 60, 70]:
        flagged = lab["scored"] & (lab["score"] >= th)
        pos = lab["label"] == "hold"
        tp, fp = int((flagged & pos).sum()), int((flagged & ~pos).sum())
        fn, tn = int((~flagged & pos).sum()), int((~flagged & ~pos).sum())
        p, r = _prf(tp, fp, fn)
        mark = " (default)" if th == cfg.hold_threshold else ""
        L.append(f"| {th:g}{mark} | {tp} | {fp} | {fn} | {tn} | {p:.2f} | {r:.2f} |")
    L.append("\n### Breakdown by scenario (default threshold)\n")
    L.append("| Scenario | n | scored | flagged hold-like | median score |\n|---|---|---|---|---|")
    for s, g in m[m["label_source"].notna()].groupby("scenario"):
        L.append(f"| {s} | {len(g)} | {int(g.scored.sum())} | {int(g.hold_like.sum())} | "
                 f"{g.score.median():.0f} |" if g.scored.any() else f"| {s} | {len(g)} | 0 | 0 | n/a |")
    fp_rows = lab[(lab["label"] == "normal") & lab["hold_like"]]
    fn_rows = lab[(lab["label"] == "hold") & ~lab["hold_like"]]
    L.append(f"\n### False positives ({len(fp_rows)}) and false negatives ({len(fn_rows)})\n")
    for name, d in [("False positive", fp_rows), ("False negative", fn_rows)]:
        for _, r in d.iterrows():
            L.append(f"- {name}: `{r.flight_id}` scenario={r.get('scenario')}, score={r.score if pd.notna(r.score) else 'not scored'}"
                     f"{'' if pd.isna(r.score) else f' (sweep {r.heading_sweep_deg:.0f} deg, revisit {r.revisit_ratio:.0%}, no-progress {r.no_progress_min:.0f} min)'}")
    # ---- peer context
    L.append("\n## 3. Effect of peer comparison\n")
    hl = m[m["hold_like"]]
    L.append(f"Hold-like flights: {len(hl)}. Category split: " + "; ".join(f"{k}: {v}" for k, v in hl["category"].value_counts().items()) + ".")
    if "scenario" in hl:
        cong = hl[hl["scenario"] == "hold_congestion"]
        iso = hl[hl["scenario"] == "hold_isolated"]
        L.append(f"- Congestion-window holds labelled common among peers: {int((cong.category == 'Hold-like (common among peers)').sum())}/{len(cong)}")
        L.append(f"- Isolated holds labelled unusual vs peers: {int((iso.category == 'Hold-like (unusual vs peers)').sum())}/{len(iso)}")
    L.append("\n## 4. Limitations\n")
    for t in [
        "Small sample; metrics on a synthetic or tiny manually reviewed set say little about real-world performance. Do not quote them as accuracy.",
        "Synthetic ground truth comes from the generator, not from human review; real labels must be added (see README, `data/labels_template.csv`).",
        "Thresholds were set by hand and then checked on the same sample - expect optimism. Use a held-out set before changing them.",
        "Peer context can hide genuine anomalies when many flights share a pattern; it down-ranks, it never deletes alerts.",
        "Reporting gaps hide turns (loops may be under-counted); estimated positions are not observations.",
        "Local flat projection, no wind, no airspace/procedure data: published holding fixes and published hold shapes are not used.",
        "Departure-like flights are excluded; go-arounds and training circuits can look hold-like.",
        "Single-airport study; parameters (radius, windows) were not tuned for other airports.",
    ]:
        L.append(f"- {t}")
    return "\n".join(L) + "\n"
