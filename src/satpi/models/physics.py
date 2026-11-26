"""Physics-consistency constraints.

Design decision (see docs/ARCHITECTURE): rather than solving PDEs inside a
neural network (classic PINN — intractable at 10 m over 10^4 km^2), the coarse
solver provides the physics prior and the ML downscaler is *regularized* with
soft physics penalties at training time. This module implements those penalties.

The functions here are pure numpy so they can be:
  1. unit-tested without torch,
  2. reported as *physical consistency scores* on any published map
     (governance requirement: accuracy gains must never hide physics
     violations), and
  3. wrapped as differentiable torch losses (see models/losses.py) — every
     operation used has a direct torch equivalent.

Conventions: depth fields are 2-D arrays in meters, DEMs in meters, cell size
in meters. NaN marks nodata and is excluded from all penalties.
"""

from __future__ import annotations

import numpy as np


def mass_conservation_residual(
    depth_fine: np.ndarray,
    depth_coarse: np.ndarray,
    scale: int,
) -> float:
    """Relative water-volume mismatch between a downscaled field and its
    coarse physical prior, aggregated per coarse cell.

    The downscaler may redistribute water *within* a coarse cell (that is its
    job) but must not create or destroy it. Returns mean |ΔV| / (V_coarse + ε):
    0.0 = perfect conservation.
    """
    if scale < 1:
        raise ValueError("scale must be >= 1")
    h, w = depth_coarse.shape
    fine = np.nan_to_num(depth_fine, nan=0.0)
    if fine.shape != (h * scale, w * scale):
        raise ValueError(
            f"fine shape {fine.shape} incompatible with coarse {depth_coarse.shape} @ scale {scale}"
        )
    # Volume per coarse cell: fine cells are (1/scale)^2 of coarse cell area.
    agg = fine.reshape(h, scale, w, scale).sum(axis=(1, 3)) / (scale * scale)
    coarse = np.nan_to_num(depth_coarse, nan=0.0)
    eps = 1e-6
    rel = np.abs(agg - coarse) / (coarse + eps)
    # Only score cells where the prior has water; dry-cell hallucination is
    # penalized separately by terrain consistency.
    wet = coarse > 1e-4
    return float(rel[wet].mean()) if wet.any() else 0.0


def uphill_flow_violation(
    depth: np.ndarray,
    dem: np.ndarray,
    tol_m: float = 0.05,
) -> float:
    """Fraction of wet-cell adjacencies whose free water surface climbs uphill.

    For hydrostatic flooding, the water surface elevation (WSE = dem + depth)
    of connected wet cells should be locally consistent: an isolated wet cell
    whose WSE sits far above a dry downslope neighbor implies water pinned to a
    hillside — physically implausible outside of active overland flow. `tol_m`
    absorbs DEM noise and genuine dynamic gradients.

    Returns fraction in [0, 1]; 0.0 = no violations.
    """
    if depth.shape != dem.shape:
        raise ValueError("depth and dem must share shape")
    wet = np.nan_to_num(depth, nan=0.0) > 1e-4
    if not wet.any():
        return 0.0
    wse = dem + np.nan_to_num(depth, nan=0.0)
    violations = 0
    pairs = 0
    for shift_axis in (0, 1):
        a_wet = wet.take(range(0, wet.shape[shift_axis] - 1), axis=shift_axis)
        b_wet = wet.take(range(1, wet.shape[shift_axis]), axis=shift_axis)
        a_wse = wse.take(range(0, wse.shape[shift_axis] - 1), axis=shift_axis)
        b_wse = wse.take(range(1, wse.shape[shift_axis]), axis=shift_axis)
        a_dem = dem.take(range(0, dem.shape[shift_axis] - 1), axis=shift_axis)
        b_dem = dem.take(range(1, dem.shape[shift_axis]), axis=shift_axis)
        # wet cell adjacent to dry cell with lower ground: water should have
        # flowed there. Violation if WSE exceeds the dry neighbor's ground by
        # more than tol.
        for a, b in ((0, 1), (1, 0)):
            wet_a = (a_wet, b_wet)[a]
            dry_b = ~(a_wet, b_wet)[b]
            wse_a = (a_wse, b_wse)[a]
            dem_b = (a_dem, b_dem)[b]
            mask = wet_a & dry_b
            pairs += int(mask.sum())
            violations += int((mask & (wse_a > dem_b + tol_m)).sum())
    return violations / pairs if pairs else 0.0


def depth_extent_monotonicity(depths: np.ndarray) -> float:
    """Given a stack of depth fields ordered by increasing forcing severity
    (e.g., ensemble percentiles or rising-limb time steps), the flooded extent
    must be non-decreasing. Returns the mean fraction of cells that dry out
    between consecutive severity levels; 0.0 = fully monotone.
    """
    if depths.ndim != 3 or depths.shape[0] < 2:
        raise ValueError("expected a (levels, H, W) stack with >= 2 levels")
    wet = np.nan_to_num(depths, nan=0.0) > 1e-4
    losses = []
    for k in range(1, wet.shape[0]):
        prev_wet = wet[k - 1]
        if prev_wet.any():
            losses.append(float((prev_wet & ~wet[k]).sum() / prev_wet.sum()))
    return float(np.mean(losses)) if losses else 0.0


def physical_consistency_score(
    depth_fine: np.ndarray,
    depth_coarse: np.ndarray,
    dem_fine: np.ndarray,
    scale: int,
) -> dict[str, float]:
    """Governance metric bundle published alongside every map product."""
    return {
        "mass_conservation_residual": mass_conservation_residual(depth_fine, depth_coarse, scale),
        "uphill_flow_violation": uphill_flow_violation(depth_fine, dem_fine),
    }
