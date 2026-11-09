"""Transparent rule-based scoring + peer comparison + plain-language explanations.

An alert means "this track resembles a holding pattern and may be worth a human look".
It is NOT evidence of an emergency, a fault, or wrongdoing. Holds are routine (traffic
flow, weather, runway changes, training).
"""
import json

import numpy as np
import pandas as pd

from .config import Config, DEFAULT

DISCLAIMER = ("This is a pattern worth reviewing, not proof of an emergency or wrongdoing. "
              "Holding is a routine procedure (traffic spacing, weather, runway changes, training).")


def _sub(v, lo, hi):
    return float(np.clip((v - lo) / (hi - lo), 0.0, 1.0)) if np.isfinite(v) else 0.0


def score_flights(fl: pd.DataFrame, cfg: Config = DEFAULT) -> pd.DataFrame:
    fl = fl.copy()
    fl["s_sweep"] = [_sub(v, cfg.sweep_lo_deg, cfg.sweep_hi_deg) for v in fl["heading_sweep_deg"]]
    fl["s_revisit"] = [_sub(v, cfg.revisit_lo, cfg.revisit_hi) for v in fl["revisit_ratio"]]
    fl["s_noprog"] = [_sub(v, cfg.noprog_lo_min, cfg.noprog_hi_min) for v in fl["no_progress_min"]]
    raw = 100 * (cfg.w_sweep * fl["s_sweep"] + cfg.w_revisit * fl["s_revisit"] + cfg.w_noprogress * fl["s_noprog"])
    fl["score"] = np.where(fl["scored"], raw, np.nan)
    fl["hold_like"] = fl["scored"] & (fl["score"] >= cfg.hold_threshold)

    # --- peers: other scored flights entering ~same time and sector ---
    n = len(fl)
    t = ((fl["entry_ts"] - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds() / 60.0).to_numpy(dtype=float)
    b = fl["entry_bearing_deg"].to_numpy(dtype=float)
    sc = fl["score"].to_numpy(dtype=float)
    ok = fl["scored"].to_numpy()
    hl = fl["hold_like"].to_numpy()
    n_peers = np.zeros(n, int); rate = np.full(n, np.nan); med = np.full(n, np.nan); z = np.full(n, np.nan)
    for i in range(n):
        if not ok[i]:
            continue
        dtm = np.abs(t - t[i])
        db = np.abs((b - b[i] + 180) % 360 - 180)
        m = ok & (dtm <= cfg.peer_time_min) & (db <= cfg.peer_sector_deg)
        m[i] = False
        n_peers[i] = int(m.sum())
        if n_peers[i] > 0:
            rate[i] = hl[m].mean()
            med[i] = np.median(sc[m])
            mad = 1.4826 * np.median(np.abs(sc[m] - med[i]))
            z[i] = (sc[i] - med[i]) / max(mad, 10.0)
    fl["n_peers"], fl["peer_hold_rate"], fl["peer_median_score"], fl["peer_z"] = n_peers, rate, med, z

    def category(r):
        if not r["scored"]:
            return "Not scored (insufficient data / out of scope)"
        s = r["score"]
        if s < cfg.weak_threshold: return "No hold-like pattern"
        if s < cfg.hold_threshold: return "Weak signal"
        if r["n_peers"] < cfg.min_peers: return "Hold-like (no peer context)"
        if r["peer_hold_rate"] >= cfg.peer_common_rate: return "Hold-like (common among peers)"
        return "Hold-like (unusual vs peers)"
    fl["category"] = fl.apply(category, axis=1)

    def confidence(r):
        if not r["scored"]: return "n/a"
        bad = [r["est_frac"] > 0.25, r["max_gap_s"] > 90, r["alt_missing_frac"] > 0.3,
               np.isfinite(r["heading_agree_deg"]) and r["heading_agree_deg"] > 25]
        return {0: "high", 1: "medium"}.get(sum(bad), "low")
    fl["confidence"] = fl.apply(confidence, axis=1)
    fl["reasons"] = fl.apply(lambda r: json.dumps(explain(r, cfg)), axis=1)
    fl["quality_notes"] = fl.apply(lambda r: json.dumps(quality_notes(r, cfg)), axis=1)
    return fl


def explain(r, cfg: Config = DEFAULT) -> list:
    if not r["scored"]:
        return [f"Not scored: {r['excluded_reason']}."]
    out = []
    sw = r["heading_sweep_deg"]
    if sw > cfg.sweep_lo_deg:
        out.append(f"Heading swept {sw:.0f} degrees (about {sw / 360:.1f} full turns) while inside the "
                   f"{cfg.radius_km:.0f} km area; typical straight-in or vectored arrivals sweep under ~{cfg.sweep_lo_deg:.0f} degrees.")
    if r["revisit_ratio"] > cfg.revisit_lo:
        out.append(f"{r['revisit_ratio']:.0%} of the track passed within {cfg.revisit_dist_km} km of a spot flown at least "
                   f"{cfg.revisit_min_dt_s / 60:.0f} min earlier, so the path overlaps itself (looping geometry).")
    if r["no_progress_min"] > 0:
        extra = ""
        if np.isfinite(r["alt_change_noprog_m"]):
            extra = f" Altitude changed by {r['alt_change_noprog_m']:+.0f} m during that time."
        out.append(f"For about {r['no_progress_min']:.0f} min the aircraft made less than {cfg.min_progress_km} km of progress toward "
                   f"the airport over {cfg.window_s / 60:.0f}-minute windows while flying a winding path.{extra}")
    if r["n_turn_episodes"] >= 2:
        out.append(f"{int(r['n_turn_episodes'])} distinct turning episodes (>{cfg.turning_rate_dps:g} deg/s), "
                   f"turning {r['turning_frac']:.0%} of the time observed in the area.")
    if not out:
        out.append("No strong hold signals: little cumulative turning, no self-overlap, and steady progress or crossing of the area.")
    out.append("After this window the track " + ("came within 5 km of the airport at low altitude." if r["reached_airport"]
               else "did not reach the airport in the data available (it may have continued elsewhere or left coverage)."))
    if r["score"] >= cfg.hold_threshold:
        if r["n_peers"] >= cfg.min_peers:
            pr = r["peer_hold_rate"]
            if pr >= cfg.peer_common_rate:
                out.append(f"Context: {int(r['n_peers'])} comparable flights (entry within +/-{cfg.peer_time_min:.0f} min and "
                           f"+/-{cfg.peer_sector_deg:.0f} deg sector) - {pr:.0%} also look hold-like, so this looks common for that "
                           f"time and approach sector (e.g. traffic flow or weather), not unusual by itself.")
            else:
                out.append(f"Context: of {int(r['n_peers'])} comparable flights, only {pr:.0%} look hold-like (peer median score "
                           f"{r['peer_median_score']:.0f}), so this is unusual relative to similar traffic - worth a human look, nothing more.")
        else:
            out.append(f"Context: only {int(r['n_peers'])} comparable flights found, too few to judge whether this is common for the time/sector.")
    out.append(DISCLAIMER)
    return out


def quality_notes(r, cfg: Config = DEFAULT) -> list:
    n = []
    if r["est_frac"] > 0:
        n.append(f"{r['est_frac']:.0%} of in-area positions are ESTIMATED/interpolated, not observed (shown in orange).")
    if r["n_gaps"] > 0:
        n.append(f"{int(r['n_gaps'])} reporting gap(s) over {cfg.gap_s:.0f} s (longest {r['max_gap_s']:.0f} s); turning inside gaps is not measured, "
                 "so loops may be under-counted.")
    if r["alt_missing_frac"] > 0.05:
        n.append(f"Altitude missing for {r['alt_missing_frac']:.0%} of in-area reports.")
    if r["speed_missing_frac"] > 0.05:
        n.append(f"Ground speed missing for {r['speed_missing_frac']:.0%} of in-area reports.")
    if np.isfinite(r["heading_agree_deg"]) and r["heading_agree_deg"] > 25:
        n.append(f"Reported track disagrees with position-derived heading (median {r['heading_agree_deg']:.0f} deg) - check data quality.")
    if not n:
        n.append("No data-quality issues detected by the automatic checks (this is not a guarantee).")
    return n
