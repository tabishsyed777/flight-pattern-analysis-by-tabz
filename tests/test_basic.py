import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import numpy as np, pandas as pd
from hold_explorer.config import DEFAULT as C
from hold_explorer.clean import make_flight_id, assign_flights
from hold_explorer.features import add_geometry, flight_features


def _track(xy, alt=3000.0, speed=100.0, dt=10):
    lat = C.airport_lat + xy[:, 1] / 110.574
    lon = C.airport_lon + xy[:, 0] / (111.320 * np.cos(np.radians(C.airport_lat)))
    ts = pd.Timestamp("2026-01-01", tz="UTC") + pd.to_timedelta(np.arange(len(xy)) * dt, unit="s")
    df = pd.DataFrame(dict(ts=ts, lat=lat, lon=lon, alt_m=alt, gs_mps=speed, track_deg=0.0, source="t",
                           is_estimated=False, flight_id="F-test"))
    return add_geometry(df, C)


def test_flight_id_deterministic_and_salted():
    assert make_flight_id("abc123", 100, "s") == make_flight_id("abc123", 100, "s")
    assert make_flight_id("abc123", 100, "s") != make_flight_id("abc123", 100, "other")


def test_straight_line_has_no_sweep():
    n = 60; xy = np.c_[np.linspace(-30, 0, n), np.zeros(n)]
    _, f = flight_features(_track(xy), C)
    assert f["heading_sweep_deg"] < 30 and f["revisit_ratio"] == 0 and f["no_progress_min"] == 0


def test_circles_are_detected():
    th = np.linspace(0, 3 * 2 * np.pi, 3 * 20)      # 3 loops
    xy = np.c_[20 + 3 * np.sin(th), 3 * np.cos(th)]  # r=3 km, ~190 s/loop at 10 s sampling
    _, f = flight_features(_track(xy, speed=100), C)
    assert f["heading_sweep_deg"] > 700 and f["revisit_ratio"] > 0.3


def test_flight_split_on_gap():
    ts = pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-01T00:00:10Z", "2026-01-01T02:00:00Z"], utc=True)
    df = pd.DataFrame(dict(ts=ts, icao24="aaa", callsign="X"))
    out, _ = assign_flights(df, C)
    assert out.flight_id.nunique() == 2 and "icao24" not in out.columns
