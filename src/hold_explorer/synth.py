"""Synthetic ADS-B-like sample generator (NO real aircraft).

Purpose: let the pipeline/dashboard run end-to-end with no licensed data. Scenarios:
  straight, dogleg, long_vector      -> normal arrivals (long_vector = hard negative)
  overflight                          -> crosses the area without landing (hard negative)
  departure                           -> excluded from scoring
  hold_isolated                       -> arrival with 2-5 racetrack/orbit loops
  hold_congestion                     -> many holds in one 2-hour window (peer-context test)
Injected data problems: dropouts, estimated segments, missing altitude, duplicates, bad rows.
Ground truth here is generator truth, NOT manual review - see README/evaluation caveats.
"""
import numpy as np
import pandas as pd

from .config import Config, DEFAULT
from .clean import make_flight_id

RWY_HDG = 140.0  # landing heading
M_PER_DEG_LAT = 110574.0


def _pol(r_km, brg_deg):
    a = np.radians(brg_deg)
    return np.array([r_km * np.sin(a), r_km * np.cos(a)])


def _arc(c, r, a0, a1, step_km=0.1):
    """clockwise arc (heading increases) around centre c, from angle a0 to a1 (rad, compass-style)."""
    n = max(2, int(abs(a1 - a0) * r / step_km))
    a = np.linspace(a0, a1, n)
    return np.c_[c[0] + r * np.sin(a), c[1] + r * np.cos(a)]


def _polyline(wps, step_km=0.1):
    pts = [wps[0]]
    for a, b in zip(wps[:-1], wps[1:]):
        L = np.hypot(*(b - a)); k = max(1, int(L / step_km))
        for i in range(1, k + 1):
            pts.append(a + (b - a) * i / k)
    return np.array(pts)


def _hold_path(entry, hdg_deg, loops, kind, rng):
    """Right-hand racetrack ('race') or circular orbit ('orbit') starting at entry heading hdg_deg."""
    h = np.radians(hdg_deg)
    right = np.array([np.cos(h), -np.sin(h)])         # unit vector to the right of travel (x,y)
    fwd = np.array([np.sin(h), np.cos(h)])
    segs = []
    if kind == "orbit":
        r = rng.uniform(2.5, 3.5)
        c = entry + right * r
        a0 = np.arctan2(entry[0] - c[0], entry[1] - c[1])
        segs.append(_arc(c, r, a0, a0 + 2 * np.pi * loops))
    else:
        r, leg = 2.0, rng.uniform(5.0, 7.0)
        p = entry.copy(); fw = fwd.copy()
        for _ in range(loops):
            for _half in range(2):
                p2 = p + fw * leg
                segs.append(_polyline([p, p2]))
                rt = np.array([fw[1], -fw[0]])
                c = p2 + rt * r
                a0 = np.arctan2(p2[0] - c[0], p2[1] - c[1])
                segs.append(_arc(c, r, a0, a0 + np.pi))
                p = segs[-1][-1]; fw = -fw
    return np.vstack(segs)


def _simulate(path_xy, hold_mask, rng, t0, icao, callsign, cfg, dt=10.0, depart=False):
    """Move along path with speed profile; return dataframe of raw-ish records."""
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(path_xy, axis=0).T))]
    nonhold_to_go = np.cumsum(((~hold_mask) * np.r_[0, np.hypot(*np.diff(path_xy, axis=0).T)])[::-1])[::-1]
    alt_prof = 80.0 * nonhold_to_go                     # m (80 m per km to go)
    spd_prof = np.clip(90 + 2.2 * nonhold_to_go, 90, 220)
    spd_prof = np.where(hold_mask, 100.0, spd_prof)
    if depart:
        alt_prof = np.clip(60.0 * d, 0, 6000); spd_prof = np.clip(15 + 5 * d, 15, 200)
    s, rows, t = 0.0, [], 0.0
    total = d[-1]
    while s < total:
        i = min(np.searchsorted(d, s), len(d) - 1)
        rows.append((t, path_xy[i, 0], path_xy[i, 1], alt_prof[i], spd_prof[i]))
        s += spd_prof[i] * dt / 1000.0
        t += dt
    a = np.array(rows)
    ts = t0 + pd.to_timedelta(a[:, 0].astype(int), unit="s")
    x = a[:, 1] + rng.normal(0, 0.04, len(a)); y = a[:, 2] + rng.normal(0, 0.04, len(a))
    lat = cfg.airport_lat + y / 110.574
    lon = cfg.airport_lon + x / (111.320 * np.cos(np.radians(cfg.airport_lat)))
    hdg = (np.degrees(np.arctan2(np.gradient(x), np.gradient(y))) + rng.normal(0, 1.5, len(a))) % 360
    return pd.DataFrame(dict(time_iso=ts.strftime("%Y-%m-%dT%H:%M:%SZ"), icao24=icao, callsign=callsign,
                             latitude=lat, longitude=lon,
                             altitude_ft=np.round((a[:, 3] + rng.normal(0, 10, len(a))) / 0.3048 / 25) * 25,
                             groundspeed_kt=np.round((a[:, 4] + rng.normal(0, 1.0, len(a))) / 0.514444),
                             track=np.round(hdg), source="adsb", estimated=False))


def generate(out_csv, out_labels, seed=7, days=21, cfg: Config = DEFAULT):
    rng = np.random.default_rng(seed)
    faf = _pol(15, RWY_HDG + 180)
    apt = np.array([0.0, 0.0])
    frames, labels = [], []
    base = pd.Timestamp("2026-09-14", tz="UTC")
    uid = 0

    def new_id():
        nonlocal uid
        uid += 1
        return f"{rng.integers(0x100000, 0xFFFFFF):06x}", f"SYN{uid:04d}"

    def arrival(t0, scenario, hold=None):
        brg = rng.uniform(0, 360)
        start = _pol(60, brg)
        if scenario == "dogleg":
            wps = [start, _pol(rng.uniform(25, 40), brg + rng.uniform(-60, 60)), faf, apt]
        elif scenario == "long_vector":
            wps = [start, _pol(35, brg + 80), _pol(30, brg + 160), _pol(28, RWY_HDG + 180 + rng.uniform(-30, 30)), faf, apt]
        else:
            wps = [start, faf, apt]
        if hold:
            kind, loops = hold
            hfix = _pol(rng.uniform(24, 32), brg)
            pre = _polyline([start, hfix])
            h_hdg = np.degrees(np.arctan2(*(apt - hfix)[[0, 1]])) % 360
            hp = _hold_path(hfix, h_hdg, loops, kind, rng)
            post = _polyline([hp[-1], faf, apt])
            path = np.vstack([pre, hp, post])
            mask = np.r_[np.zeros(len(pre), bool), np.ones(len(hp), bool), np.zeros(len(post), bool)]
        else:
            path = _polyline(wps)
            mask = np.zeros(len(path), bool)
        return path, mask

    def add(df, scenario, label, **kw):
        t0 = pd.Timestamp(df["time_iso"].iloc[0])
        fid = make_flight_id(df["icao24"].iloc[0], t0.timestamp())
        labels.append(dict(flight_id=fid, label=label, scenario=scenario, label_source="synthetic_generator_truth"))
        frames.append(df)

    for d in range(days):
        day0 = base + pd.Timedelta(days=d)
        plan = []
        for _ in range(rng.poisson(9)):
            plan.append(("arr", rng.uniform(2, 17)))
        for _ in range(rng.poisson(3)):
            plan.append(("over", rng.uniform(2, 17)))
        for _ in range(rng.poisson(2)):
            plan.append(("dep", rng.uniform(2, 17)))
        if d == 5:                                       # congestion window 08:00-10:00 UTC
            plan += [("cong", rng.uniform(8, 10)) for _ in range(9)]
        for kind, hr in plan:
            icao, cs = new_id()
            t0 = day0 + pd.Timedelta(hours=float(hr)) + pd.Timedelta(seconds=int(rng.integers(0, 60)))
            if kind == "dep":
                b = RWY_HDG + 180
                wps = [apt, _pol(40, b), _pol(55, b + rng.uniform(-40, 40))]
                path = _polyline(wps); mask = np.zeros(len(path), bool)
                df = _simulate(path, mask, rng, t0, icao, cs, cfg, depart=True); add(df, "departure", "excluded")
            elif kind == "over":
                brg = rng.uniform(0, 360); off = rng.uniform(5, 40)
                a = _pol(70, brg + 90) + _pol(off, brg); b = _pol(70, brg - 90) + _pol(off, brg)
                path = _polyline([a, b]); mask = np.zeros(len(path), bool)
                df = _simulate(path, mask, rng, t0, icao, cs, cfg)
                df["altitude_ft"] = 34000.0; df["groundspeed_kt"] = 450.0; add(df, "overflight", "normal")
            else:
                if kind == "cong":
                    hold = (rng.choice(["race", "orbit"]), int(rng.integers(2, 4))) if rng.random() < 0.7 else None
                    sc = "hold_congestion" if hold else "straight"
                else:
                    r = rng.random()
                    hold = (rng.choice(["race", "orbit"]), int(rng.integers(2, 6))) if r < 0.07 else None
                    sc = "hold_isolated" if hold else rng.choice(["straight", "dogleg", "long_vector"], p=[.55, .3, .15])
                path, mask = arrival(t0, sc, hold)
                df = _simulate(path, mask, rng, t0, icao, cs, cfg)
                add(df, sc, "hold" if hold else "normal")

    # --- inject data problems (never touch first row so flight_id stays stable) ---
    out = []
    for df in frames:
        df = df.copy()
        r = rng.random()
        if len(df) > 60 and r < 0.10:                                   # dropout 60-150 s
            i = int(rng.integers(20, len(df) - 20)); df = df.drop(df.index[i:i + int(rng.integers(6, 15))])
        elif len(df) > 60 and r < 0.15:                                 # estimated segment
            i = int(rng.integers(10, len(df) - 50)); df.iloc[i:i + 40, df.columns.get_loc("estimated")] = True
            df.iloc[i:i + 40, df.columns.get_loc("source")] = "estimated"
        elif r < 0.20:                                                  # missing altitude
            m = rng.random(len(df)) < 0.35; m[0] = False; df.loc[m, "altitude_ft"] = np.nan
        if rng.random() < 0.03:                                         # duplicate rows
            df = pd.concat([df, df.iloc[5:8]])
        out.append(df)
    # a few truncated (too short) flights
    for k in rng.choice(len(out), 4, replace=False):
        out[k] = out[k].iloc[:15]
    allp = pd.concat(out, ignore_index=True)
    junk = allp.iloc[[100, 200]].copy()
    junk.iloc[0, junk.columns.get_loc("latitude")] = 0.0; junk.iloc[0, junk.columns.get_loc("longitude")] = 0.0
    junk.iloc[1, junk.columns.get_loc("latitude")] = 123.0
    junk["time_iso"] = (pd.to_datetime(junk["time_iso"]) + pd.Timedelta(seconds=3)).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    allp = pd.concat([allp, junk]).sample(frac=1.0, random_state=seed)   # shuffled like a raw dump
    allp.to_csv(out_csv, index=False)
    pd.DataFrame(labels).to_csv(out_labels, index=False)
    return len(allp), len(labels)
