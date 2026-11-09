"""Streamlit dashboard. Run:  streamlit run app.py   (after: python scripts/run_pipeline.py --make-sample)"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st
from plotly.subplots import make_subplots

DATA = Path("data/processed")
st.set_page_config(page_title="Hold-pattern explorer", layout="wide")


@st.cache_data
def load():
    fl = pd.read_csv(DATA / "flights.csv", parse_dates=["start_ts", "end_ts", "entry_ts"])
    pos = pd.read_csv(DATA / "positions.csv.gz", parse_dates=["ts"])
    meta = json.loads((DATA / "meta.json").read_text())
    return fl, pos, meta


if not (DATA / "flights.csv").exists():
    st.error("No processed data. Run `python scripts/run_pipeline.py --make-sample` first.")
    st.stop()
fl, pos, meta = load()
ap = meta["airport"]

st.title("Explainable flight-pattern explorer: hold-like patterns")
st.warning("An alert is a **pattern worth reviewing**, not proof of an emergency or wrongdoing. Holds are routine "
           "(traffic spacing, weather, runway changes, training).")
if meta["source"] == "sample_synthetic":
    st.info("You are viewing **synthetic sample data** - no real aircraft.")
if meta.get("salt_is_default"):
    st.caption("Flight IDs are pseudonymous (HMAC of identifier). The default demo salt is in use; set HOLD_EXPLORER_SALT for real data.")

tab_f, tab_o, tab_e = st.tabs(["Flight review", "Overview", "Evaluation report"])

with tab_o:
    sc = fl[fl.scored]
    c1, c2, c3 = st.columns(3)
    c1.metric("Flights", len(fl)); c2.metric("Scored", len(sc)); c3.metric("Hold-like", int(fl.hold_like.sum()))
    st.bar_chart(fl.category.value_counts())
    st.caption("Score histogram (scored flights)")
    st.bar_chart(np.histogram(sc.score, bins=range(0, 105, 5))[0])
    st.dataframe(fl.sort_values("score", ascending=False)[["flight_id", "start_ts", "score", "category", "confidence",
                 "heading_sweep_deg", "revisit_ratio", "no_progress_min", "n_peers", "peer_hold_rate"]], use_container_width=True)

with tab_e:
    rp = Path("reports/evaluation.md")
    st.markdown(rp.read_text() if rp.exists() else "No report yet.")

with tab_f:
    with st.sidebar:
        st.header("Filter")
        cats = st.multiselect("Category", sorted(fl.category.unique()),
                              default=[c for c in fl.category.unique() if c.startswith(("Hold-like", "Weak"))])
        min_score = st.slider("Minimum score", 0, 100, 0)
        view = fl[fl.category.isin(cats) & (fl.score.fillna(0) >= min_score)].sort_values("score", ascending=False)
        st.caption(f"{len(view)} flights match")
        fid = st.selectbox("Flight (pseudonymous ID)", view.flight_id.tolist()) if len(view) else None
    if fid is None:
        st.stop()
    r = fl[fl.flight_id == fid].iloc[0]
    g = pos[pos.flight_id == fid].sort_values("ts").reset_index(drop=True)

    a, b, c, d = st.columns(4)
    a.metric("Score", "n/a" if pd.isna(r.score) else f"{r.score:.0f}/100")
    b.metric("Category", r.category.replace("Hold-like ", "Hold-like\n"))
    c.metric("Data confidence", r.confidence)
    d.metric("Peers compared", int(r.n_peers))

    left, right = st.columns([3, 2])
    with left:
        obs, est = g[~g.is_estimated], g[g.is_estimated]
        layers = [
            pdk.Layer("ScatterplotLayer", data=pd.DataFrame([{"lon": ap["lon"], "lat": ap["lat"]}]), get_position="[lon, lat]",
                      get_radius=ap["radius_km"] * 1000, stroked=True, filled=False, get_line_color=[120, 120, 120],
                      line_width_min_pixels=2),
            pdk.Layer("PathLayer", data=[{"path": g[["lon", "lat"]].values.tolist()}], get_path="path",
                      get_color=[60, 90, 200], width_min_pixels=2),
            pdk.Layer("ScatterplotLayer", data=obs, get_position="[lon, lat]", get_radius=250, get_fill_color=[40, 80, 220]),
            pdk.Layer("ScatterplotLayer", data=g[g.no_progress], get_position="[lon, lat]", get_radius=350, get_fill_color=[220, 30, 30]),
            pdk.Layer("ScatterplotLayer", data=est, get_position="[lon, lat]", get_radius=350, get_fill_color=[255, 150, 0]),
            pdk.Layer("ScatterplotLayer", data=pd.DataFrame([{"lon": ap["lon"], "lat": ap["lat"]}]), get_position="[lon, lat]",
                      get_radius=900, get_fill_color=[0, 0, 0]),
        ]
        st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=pdk.ViewState(latitude=ap["lat"], longitude=ap["lon"], zoom=7.6)))
        st.caption("Blue = observed positions; red = minutes with no progress toward the airport; orange = ESTIMATED positions; "
                   "black dot = airport; grey ring = analysis radius.")
    with right:
        st.subheader("Why this classification")
        for t in json.loads(r.reasons):
            st.markdown(f"- {t}")
        st.subheader("Data-quality notices")
        for t in json.loads(r.quality_notes):
            st.markdown(f"- {t}")
        with st.expander("Score components"):
            st.write({"heading sweep": round(r.s_sweep, 2), "self-overlap": round(r.s_revisit, 2), "no progress": round(r.s_noprog, 2)})
            st.caption("Weights 0.4 / 0.3 / 0.3; see src/hold_explorer/config.py")
        st.markdown("**Manual context check:** open [Argos Atlas](https://argosatlas.com/map/) in your browser to compare nearby "
                    "airports/context by hand. Do not scrape or bulk-export it. Pseudonymous IDs are not Argos IDs; find a real "
                    "flight by time and place. (Sample data is synthetic and will not appear there.)")

    # ---- timeline ----
    gg = g.copy()
    gap = gg.ts.diff().dt.total_seconds() > 60
    brk = gg[gap].copy(); brk["ts"] = brk["ts"] - pd.Timedelta(seconds=1)
    for col in ["alt_m", "gs_mps", "turn_rate_dps", "dist_km"]:
        brk[col] = np.nan
    gg = pd.concat([gg, brk]).sort_values("ts")
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                        subplot_titles=("Altitude (m)", "Ground speed (m/s)", "Turn rate (deg/s, smoothed)", "Distance to airport (km)"))
    for i, col in enumerate(["alt_m", "gs_mps", "turn_rate_dps", "dist_km"], 1):
        fig.add_trace(go.Scatter(x=gg.ts, y=gg[col], mode="lines", line=dict(width=1.5), showlegend=False), row=i, col=1)
        e = g[g.is_estimated]
        if len(e):
            fig.add_trace(go.Scatter(x=e.ts, y=e[col], mode="markers", marker=dict(color="orange", symbol="x", size=5),
                                     name="estimated", showlegend=(i == 1)), row=i, col=1)
    idx = np.flatnonzero(np.diff(np.r_[0, g.no_progress.astype(int).values, 0]))
    for s, e_ in zip(idx[::2], idx[1::2]):
        fig.add_vrect(x0=g.ts.iloc[s], x1=g.ts.iloc[e_ - 1], fillcolor="red", opacity=0.12, line_width=0)
    fig.add_hline(y=0, row=3, col=1, line_dash="dot")
    fig.update_layout(height=700, margin=dict(t=30, b=10))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Red bands: minutes flagged as no progress toward the airport. Line breaks: reporting gaps (> 60 s). Orange x: estimated positions.")
