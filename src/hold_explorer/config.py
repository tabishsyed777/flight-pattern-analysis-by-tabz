"""All tunable assumptions live here so they are documented in one place."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # --- Study area -------------------------------------------------------
    airport_icao: str = "VANP"
    airport_name: str = "Nagpur (VANP) - SAMPLE DATA IS SYNTHETIC"
    airport_lat: float = 21.0922
    airport_lon: float = 79.0472
    radius_km: float = 50.0

    # --- Cleaning / flight grouping --------------------------------------
    max_gap_split_s: int = 1800        # silence > 30 min => new flight
    max_speed_mps: float = 400.0       # physical plausibility
    alt_min_m: float = -500.0
    alt_max_m: float = 20000.0
    ground_alt_m: float = 50.0         # on-ground heuristic ...
    ground_speed_mps: float = 30.0     # ... alt<=50 m AND gs<=30 m/s

    # --- Coverage filters (flight is "scored" only if all pass) -----------
    min_points_total: int = 40
    min_points_in_radius: int = 20
    min_dwell_min: float = 3.0
    max_estimated_frac: float = 0.60   # mostly-estimated tracks are not scored

    # --- Feature parameters ----------------------------------------------
    gap_s: float = 60.0                # intervals longer than this are "gaps"
    min_step_km: float = 0.05          # below this, heading is undefined
    turning_rate_dps: float = 1.0      # |turn rate| above this = "turning"
    revisit_min_dt_s: float = 180.0    # revisit = back within X km of a spot flown >= 3 min earlier
    revisit_dist_km: float = 1.5
    window_s: float = 360.0            # progress window (6 min)
    min_progress_km: float = 1.5       # < this closer to airport in the window = "no progress"
    max_path_efficiency: float = 0.6   # displacement / path length below this = "winding"

    # --- Scoring (0-100) --------------------------------------------------
    w_sweep: float = 0.40
    w_revisit: float = 0.30
    w_noprogress: float = 0.30
    sweep_lo_deg: float = 270.0        # <= 270 deg total heading sweep: typical vectoring
    sweep_hi_deg: float = 720.0        # >= 2 full turns: saturates
    revisit_lo: float = 0.02
    revisit_hi: float = 0.25
    noprog_lo_min: float = 6.0
    noprog_hi_min: float = 18.0
    weak_threshold: float = 30.0
    hold_threshold: float = 55.0

    # --- Peer comparison --------------------------------------------------
    peer_time_min: float = 180.0       # entry time within +/- 3 h (sparse sample; tighten for busy airports)
    peer_sector_deg: float = 90.0       # entry bearing within +/- 90 deg
    min_peers: int = 3
    peer_common_rate: float = 0.30     # >=30% peers hold-like => "common in context"


DEFAULT = Config()
