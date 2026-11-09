"""Trajectory features. All geometry uses a local equirectangular projection around the
airport (error is well under 1% inside a 50 km radius - documented limitation).

Headings are derived from successive positions (more robust than reported track, which is
only used as a data-quality cross-check).
"""
import numpy as np
import pandas as pd

from .config import Config, DEFAULT


def wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


def add_geometry(df: pd.DataFrame, cfg: Config = DEFAULT) -> pd.DataFrame:
    df = df.copy()
    df["x_km"] = (df["lon"] - cfg.airport_lon) * 111.320 * np.cos(np.radians(cfg.airport_lat))
    df["y_km"] = (df["lat"] - cfg.airport_lat) * 110.574
    df["dist_km"] = np.hypot(df["x_km"], df["y_km"])
    df["bearing_deg"] = np.degrees(np.arctan2(df["x_km"], df["y_km"])) % 360
    df["in_radius"] = df["dist_km"] <= cfg.radius_km
    df["on_ground"] = (df["alt_m"] <= cfg.ground_alt_m) & (df["gs_mps"] <= cfg.ground_speed_mps)
    df["analyzed"] = df["in_radius"] & ~df["on_ground"]
    return df


def _point_features(g: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    g = g.sort_values("ts").copy()
    t = (g["ts"] - g["ts"].iloc[0]).dt.total_seconds().to_numpy()
    x, y = g["x_km"].to_numpy(), g["y_km"].to_numpy()
    dt = np.diff(t, prepend=np.nan)
    dx, dy = np.diff(x, prepend=np.nan), np.diff(y, prepend=np.nan)
    step = np.hypot(dx, dy)
    hdg = np.degrees(np.arctan2(dx, dy)) % 360
    hdg[~(step >= cfg.min_step_km)] = np.nan
    hdg = pd.Series(hdg).ffill().to_numpy()
    dh = wrap180(np.diff(hdg, prepend=np.nan))
    ok = (dt > 0) & (dt <= cfg.gap_s) & np.isfinite(dh)
    turn = np.where(ok, dh / np.where(dt > 0, dt, np.nan), np.nan)
    g["t_s"], g["dt_s"], g["heading_deg"] = t, dt, hdg
    g["dheading_deg"] = np.where(ok, dh, 0.0)
    g["turn_rate_dps"] = pd.Series(turn).rolling(5, center=True, min_periods=2).median().to_numpy()
    g["no_progress"] = False
    return g


def _runs(mask: np.ndarray):
    idx = np.flatnonzero(np.diff(np.r_[0, mask.astype(int), 0]))
    return list(zip(idx[::2], idx[1::2]))


def flight_features(g: pd.DataFrame, cfg: Config = DEFAULT):
    """Return (point_df_with_features, feature_dict) for one flight."""
    g = _point_features(g, cfg)
    n = len(g)
    f = {"flight_id": g["flight_id"].iloc[0], "n_points": n,
         "start_ts": g["ts"].iloc[0], "end_ts": g["ts"].iloc[-1],
         "duration_min": g["t_s"].iloc[-1] / 60.0,
         "min_dist_km": float(g["dist_km"].min())}
    an = g["analyzed"].to_numpy()
    prev_an = np.r_[False, an[:-1]]
    ga = g[an]
    f["n_analyzed"] = int(an.sum())
    f["est_frac"] = float(ga["is_estimated"].mean()) if len(ga) else np.nan
    f["alt_missing_frac"] = float(ga["alt_m"].isna().mean()) if len(ga) else np.nan
    f["speed_missing_frac"] = float(ga["gs_mps"].isna().mean()) if len(ga) else np.nan
    f["source"] = ";".join(sorted(map(str, g["source"].dropna().unique())))
    dts = ga["dt_s"].to_numpy()[1:] if len(ga) > 1 else np.array([])
    f["max_gap_s"] = float(np.nanmax(dts)) if len(dts) and np.isfinite(dts).any() else 0.0
    f["n_gaps"] = int((dts > cfg.gap_s).sum())

    # reported-track cross-check (data quality, not used for scoring)
    m = an & g["track_deg"].notna().to_numpy() & (g["gs_mps"].to_numpy() > 40) & np.isfinite(g["heading_deg"].to_numpy())
    f["heading_agree_deg"] = float(np.median(np.abs(wrap180(g["track_deg"].to_numpy()[m] - g["heading_deg"].to_numpy()[m])))) if m.sum() >= 10 else np.nan

    base = dict(heading_sweep_deg=0.0, abs_turn_total_deg=0.0, n_turn_episodes=0, turning_frac=0.0,
                revisit_ratio=0.0, no_progress_min=0.0, dwell_min=0.0, entry_ts=pd.NaT, entry_bearing_deg=np.nan,
                first_dist_km=np.nan, alt_change_noprog_m=np.nan, mean_alt_m=np.nan, last_alt_m=np.nan,
                phase_guess="unknown", reached_airport=False)
    f.update(base)
    if f["n_analyzed"] < 5:
        return g, f

    # --- turning ---
    dh = np.where(an & prev_an, g["dheading_deg"].to_numpy(), 0.0)
    cum = np.cumsum(dh)
    f["heading_sweep_deg"] = float(cum[an].max() - cum[an].min())
    f["abs_turn_total_deg"] = float(np.abs(dh[an]).sum())
    sm = g["turn_rate_dps"].to_numpy()
    turning = an & (np.abs(np.nan_to_num(sm)) > cfg.turning_rate_dps)
    tt = g["t_s"].to_numpy()
    eps = [(a, b) for a, b in _runs(turning) if tt[min(b, n) - 1] - tt[a] >= 20]
    f["n_turn_episodes"] = len(eps)

    ta = tt[an]; xa = g["x_km"].to_numpy()[an]; ya = g["y_km"].to_numpy()[an]; da = g["dist_km"].to_numpy()[an]
    w = np.clip(np.diff(ta, append=ta[-1]), 0, cfg.gap_s)
    f["dwell_min"] = float(w.sum() / 60)
    f["turning_frac"] = float((w * turning[an]).sum() / max(w.sum(), 1e-9))
    f["entry_ts"] = ga["ts"].iloc[0]
    f["entry_bearing_deg"] = float(ga["bearing_deg"].iloc[0])
    f["first_dist_km"] = float(da[0])
    f["mean_alt_m"] = float(ga["alt_m"].mean()) if ga["alt_m"].notna().any() else np.nan
    f["last_alt_m"] = float(ga["alt_m"].dropna().iloc[-1]) if ga["alt_m"].notna().any() else np.nan

    # --- revisit (path overlaps itself) ---
    med_dt = np.median(np.diff(ta)) if len(ta) > 1 else 10
    k = max(1, int(round(20 / max(med_dt, 1))))
    sel = np.arange(0, len(ta), k)
    T = ta[sel][:, None] - ta[sel][None, :]
    D = np.hypot(xa[sel][:, None] - xa[sel][None, :], ya[sel][:, None] - ya[sel][None, :])
    f["revisit_ratio"] = float(((T >= cfg.revisit_min_dt_s) & (D < cfg.revisit_dist_km)).any(axis=1).mean())

    # --- no progress toward airport while winding ---
    step = np.hypot(np.diff(xa, prepend=xa[0]), np.diff(ya, prepend=ya[0]))
    cp = np.cumsum(step)
    j = np.searchsorted(ta, ta + cfg.window_s)
    ok = (j < len(ta))
    j = np.minimum(j, len(ta) - 1)
    ok &= (ta[j] - (ta + cfg.window_s)) <= 60
    disp = np.hypot(xa[j] - xa, ya[j] - ya)
    path = np.maximum(cp[j] - cp, 1e-6)
    flagged = ok & ((da - da[j]) < cfg.min_progress_km) & ((disp / path) < cfg.max_path_efficiency)
    diff = np.zeros(len(ta) + 1)
    for i in np.flatnonzero(flagged):
        diff[i] += 1
        diff[j[i] + 1] -= 1
    covered = np.cumsum(diff)[:-1] > 0
    f["no_progress_min"] = float((w * covered).sum() / 60)
    if covered.any():
        alt_a = ga["alt_m"].to_numpy()
        a = alt_a[covered]; a = a[~np.isnan(a)]
        if len(a) > 1:
            f["alt_change_noprog_m"] = float(a[-1] - a[0])
    npcol = np.zeros(n, dtype=bool); npcol[np.flatnonzero(an)[covered]] = True
    g["no_progress"] = npcol

    # --- phase guess (departures are not scored: holds are an arrival-phase concept) ---
    alt_ok = ga["alt_m"].dropna()
    climb = (alt_ok.iloc[-1] - alt_ok.iloc[0]) if len(alt_ok) > 1 else np.nan
    f["reached_airport"] = bool(f["min_dist_km"] < 5 and (np.isnan(f["last_alt_m"]) or f["last_alt_m"] < 600))
    if bool(g["on_ground"].iloc[0]) or (da[0] < 10 and np.isfinite(climb) and climb > 300):
        f["phase_guess"] = "departure_like"
    elif f["reached_airport"] or (np.isfinite(climb) and climb < -300):
        f["phase_guess"] = "arrival_like"
    else:
        f["phase_guess"] = "transit_or_other"
    return g, f


def build_features(pos: pd.DataFrame, cfg: Config = DEFAULT):
    pos = add_geometry(pos, cfg)
    pts, rows = [], []
    for _, g in pos.groupby("flight_id", sort=False):
        gp, f = flight_features(g, cfg)
        pts.append(gp); rows.append(f)
    flights = pd.DataFrame(rows)

    def why(r):
        if r["n_points"] < cfg.min_points_total: return f"fewer than {cfg.min_points_total} position reports"
        if r["n_analyzed"] < cfg.min_points_in_radius: return f"fewer than {cfg.min_points_in_radius} airborne reports inside the {cfg.radius_km:.0f} km area"
        if r["dwell_min"] < cfg.min_dwell_min: return f"under {cfg.min_dwell_min:.0f} min observed inside the area"
        if r["est_frac"] > cfg.max_estimated_frac: return "mostly estimated (not observed) positions"
        if r["phase_guess"] == "departure_like": return "departure-like flight (holds are an arrival-phase pattern)"
        return ""
    flights["excluded_reason"] = flights.apply(why, axis=1)
    flights["scored"] = flights["excluded_reason"] == ""
    return pd.concat(pts, ignore_index=True), flights
