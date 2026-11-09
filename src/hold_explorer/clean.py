"""Load -> normalise -> QC -> group into flights -> pseudonymise.

Canonical schema (SI units, UTC):
  ts, icao24, callsign, lat, lon, alt_m, gs_mps, track_deg, source, is_estimated
"""
import hashlib
import hmac
import os

import numpy as np
import pandas as pd

from .config import Config, DEFAULT
from .sources import SourceSpec

FT_TO_M = 0.3048
KT_TO_MPS = 0.514444


def get_salt() -> str:
    """Secret salt for pseudonymous IDs. Set HOLD_EXPLORER_SALT for any real dataset."""
    return os.environ.get("HOLD_EXPLORER_SALT", "sample-salt-change-me")


def make_flight_id(icao24: str, start_epoch: float, salt: str | None = None) -> str:
    salt = get_salt() if salt is None else salt
    msg = f"{icao24}|{int(start_epoch)}".encode()
    return "F-" + hmac.new(salt.encode(), msg, hashlib.sha256).hexdigest()[:8]


def load_and_normalise(path: str, spec: SourceSpec, cfg: Config = DEFAULT):
    """Read a CSV and return (canonical_df, qc_log). Never mutates the source file."""
    raw = pd.read_csv(path, low_memory=False)
    qc = {"rows_in": int(len(raw))}
    out = pd.DataFrame(index=raw.index)
    for canon in ["timestamp", "icao24", "callsign", "lat", "lon", "alt", "gs", "track", "source"]:
        col = spec.columns.get(canon)
        out[canon] = raw[col] if col and col in raw.columns else np.nan

    if spec.ts_kind == "epoch_s":
        out["ts"] = pd.to_datetime(pd.to_numeric(out["timestamp"], errors="coerce"), unit="s", utc=True)
    else:
        out["ts"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    for c in ["lat", "lon", "alt", "gs", "track"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")

    out["alt_m"] = out["alt"] * (FT_TO_M if spec.alt_unit == "ft" else 1.0)
    f = {"kt": KT_TO_MPS, "kmh": 1 / 3.6}.get(spec.speed_unit, 1.0)
    out["gs_mps"] = out["gs"] * f
    out["track_deg"] = out["track"] % 360
    if spec.estimated_col and spec.estimated_col in raw.columns:
        out["is_estimated"] = raw[spec.estimated_col].astype(str).str.lower().isin(spec.estimated_values)
    else:
        out["is_estimated"] = False
    out["source"] = out["source"].astype("object").where(out["source"].notna(), spec.name)
    out["icao24"] = out["icao24"].astype("object").astype(str).str.lower().str.strip()
    out["callsign"] = out["callsign"].astype("object")

    # --- QC drops (counted and reported, never silent) ---
    bad_ts = out["ts"].isna() | out["lat"].isna() | out["lon"].isna()
    qc["dropped_missing_ts_or_position"] = int(bad_ts.sum())
    out = out[~bad_ts]
    bad_rng = (out["lat"].abs() > 90) | (out["lon"].abs() > 180)
    qc["dropped_out_of_range_latlon"] = int(bad_rng.sum())
    out = out[~bad_rng]
    null_island = (out["lat"].abs() < 0.01) & (out["lon"].abs() < 0.01)
    qc["dropped_null_island"] = int(null_island.sum())
    out = out[~null_island]
    n = len(out)
    out = out.drop_duplicates(["icao24", "ts"], keep="first")
    qc["dropped_duplicates"] = int(n - len(out))
    # Implausible values become missing (kept row, flagged) instead of dropping the position.
    bad_gs = out["gs_mps"] > cfg.max_speed_mps
    bad_alt = (out["alt_m"] < cfg.alt_min_m) | (out["alt_m"] > cfg.alt_max_m)
    qc["speed_set_missing_implausible"] = int(bad_gs.sum())
    qc["altitude_set_missing_implausible"] = int(bad_alt.sum())
    out.loc[bad_gs, "gs_mps"] = np.nan
    out.loc[bad_alt, "alt_m"] = np.nan
    qc["rows_after_qc"] = int(len(out))
    cols = ["ts", "icao24", "callsign", "lat", "lon", "alt_m", "gs_mps", "track_deg", "source", "is_estimated"]
    return out[cols].reset_index(drop=True), qc


def assign_flights(df: pd.DataFrame, cfg: Config = DEFAULT, salt: str | None = None,
                   keep_raw_ids: bool = False):
    """Group reports into flights (same icao24, silence gap < cfg.max_gap_split_s).

    Returns (positions, callsigns). Raw identifiers (icao24/callsign) are dropped from the
    returned positions unless keep_raw_ids=True. Callsign lookup is returned only for that case.
    """
    df = df.sort_values(["icao24", "ts"]).reset_index(drop=True)
    gap = df["ts"].diff().dt.total_seconds()
    new = (df["icao24"] != df["icao24"].shift()) | (gap > cfg.max_gap_split_s)
    df["seg"] = new.cumsum()
    starts = df.groupby("seg").agg(icao24=("icao24", "first"), start=("ts", "min"))
    ids = {s: make_flight_id(r.icao24, r.start.timestamp(), salt) for s, r in starts.iterrows()}
    df["flight_id"] = df["seg"].map(ids)
    cs = None
    if keep_raw_ids:
        cs = df.groupby("flight_id").agg(icao24=("icao24", "first"),
                                         callsign=("callsign", lambda s: s.dropna().mode().iloc[0]
                                                   if s.notna().any() else None)).reset_index()
    drop = ["seg"] + ([] if keep_raw_ids else ["icao24", "callsign"])
    return df.drop(columns=drop), cs
