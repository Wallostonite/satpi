"""State correction: continuous gauge nudging + intermittent satellite anchoring.

The dynamics subsystem runs on radar/NWP forcing between observations. Two
correction paths keep it honest:

1. Gauge nudging (continuous, point): relax modeled depth toward observed
   stage at gauge cells with a configurable relaxation timescale, spreading
   the increment over a local influence radius (a pragmatic, robust stand-in
   for a full EnKF at pilot scale; the interface admits an EnKF drop-in).

2. Satellite anchoring (intermittent, spatial): when the perception model
   produces a probabilistic extent/depth raster from a new pass, blend it into
   the state weighted by per-pixel confidence. Between passes the weight is
   zero and the model free-runs.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from satpi.dynamics.solver import SolverState


@dataclass
class GaugeObservation:
    cell: tuple[int, int]  # coarse-grid index of the gauge
    stage_m: float  # observed water depth above bed at the gauge cell
    obs_error_m: float = 0.05


def nudge_to_gauges(
    state: SolverState,
    observations: list[GaugeObservation],
    dem: np.ndarray,
    relaxation: float = 0.3,
    influence_radius_cells: int = 5,
) -> SolverState:
    """Relax state toward gauge observations.

    relaxation in (0, 1]: fraction of the innovation applied this cycle at the
    gauge cell, decaying with distance (Gaussian) out to the influence radius.
    """
    if not 0.0 < relaxation <= 1.0:
        raise ValueError("relaxation must be in (0, 1]")
    depth = state.depth.copy()
    h, w = depth.shape
    yy, xx = np.mgrid[0:h, 0:w]
    for obs in observations:
        i, j = obs.cell
        if not (0 <= i < h and 0 <= j < w):
            continue
        innovation = obs.stage_m - depth[i, j]
        dist2 = (yy - i) ** 2 + (xx - j) ** 2
        weight = np.exp(-dist2 / (2.0 * max(influence_radius_cells, 1) ** 2))
        weight[dist2 > influence_radius_cells**2 * 4] = 0.0
        depth += relaxation * innovation * weight
    np.clip(depth, 0.0, None, out=depth)
    return SolverState(depth=depth, t_seconds=state.t_seconds)


def blend_satellite_state(
    state: SolverState,
    sat_depth: np.ndarray,
    sat_confidence: np.ndarray,
    max_weight: float = 0.8,
) -> SolverState:
    """Blend a perception-derived depth field into the model state.

    sat_confidence in [0, 1] per pixel (from the GFM's calibrated
    probabilities); the blend weight is confidence * max_weight, so even a
    fully confident observation never wholly replaces the dynamic state —
    the observation is a snapshot that may already be stale by minutes.
    """
    if sat_depth.shape != state.depth.shape:
        raise ValueError("satellite field must be on the solver grid (coarsen first)")
    conf = np.clip(np.nan_to_num(sat_confidence, nan=0.0), 0.0, 1.0) * max_weight
    depth = (1.0 - conf) * state.depth + conf * np.nan_to_num(sat_depth, nan=0.0)
    return SolverState(depth=np.clip(depth, 0.0, None), t_seconds=state.t_seconds)


def ensemble_spread(depths: list[np.ndarray]) -> np.ndarray:
    """Per-cell ensemble standard deviation — the uncertainty layer that ships
    with every probabilistic product."""
    if len(depths) < 2:
        raise ValueError("need >= 2 members for spread")
    return np.std(np.stack(depths, axis=0), axis=0)


def exceedance_probability(depths: list[np.ndarray], threshold_m: float) -> np.ndarray:
    """P(depth > threshold) across the ensemble — the core alerting field."""
    stack = np.stack(depths, axis=0) > threshold_m
    return stack.mean(axis=0)
