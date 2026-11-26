"""Terrain derivatives on regular grids (numpy core).

DEM -> slope, coarsening, and a simplified HAND (height above nearest
drainage). The geo extra adds georeferenced IO (rioxarray) around these pure
functions; keeping the math dependency-free keeps it testable everywhere.
"""

from __future__ import annotations

import numpy as np


def slope_magnitude(dem: np.ndarray, cell_size_m: float) -> np.ndarray:
    """Slope (rise/run) via central differences."""
    gy, gx = np.gradient(dem.astype(float), cell_size_m)
    return np.hypot(gx, gy)


def coarsen(field: np.ndarray, factor: int, how: str = "mean") -> np.ndarray:
    """Block-aggregate a fine grid to the solver grid. Trims edge remainders."""
    if factor < 1:
        raise ValueError("factor must be >= 1")
    h = (field.shape[0] // factor) * factor
    w = (field.shape[1] // factor) * factor
    blocks = field[:h, :w].reshape(h // factor, factor, w // factor, factor)
    if how == "mean":
        return blocks.mean(axis=(1, 3))
    if how == "min":  # DEMs coarsen better with min for channel preservation
        return blocks.min(axis=(1, 3))
    raise ValueError(f"unknown aggregation {how!r}")


def hand(dem: np.ndarray, drainage_mask: np.ndarray, max_iter: int | None = None) -> np.ndarray:
    """Simplified HAND: height above the nearest (grid-BFS) drainage cell.

    Full HAND traces D8 flow directions; this BFS variant — propagate each
    cell's nearest-drainage elevation outward ring by ring — is a sound
    approximation on hydro-conditioned DEMs and needs no geo dependencies.
    Used for depth attribution from perception extents and as a downscaler
    input channel.
    """
    if dem.shape != drainage_mask.shape:
        raise ValueError("dem and drainage_mask must share shape")
    if not drainage_mask.any():
        raise ValueError("drainage mask is empty")
    dem = dem.astype(float)
    ref = np.where(drainage_mask, dem, np.nan)
    limit = max_iter if max_iter is not None else dem.shape[0] + dem.shape[1]
    for _ in range(limit):
        if not np.isnan(ref).any():
            break
        prev_nan = np.isnan(ref)
        # Gather neighbor reference elevations (edge-safe, no wraparound)
        neighbors = np.full((4, *ref.shape), np.nan)
        neighbors[0, 1:, :] = ref[:-1, :]   # from north
        neighbors[1, :-1, :] = ref[1:, :]   # from south
        neighbors[2, :, 1:] = ref[:, :-1]   # from west
        neighbors[3, :, :-1] = ref[:, 1:]   # from east
        # fmin ignores NaN pairwise and never warns on all-NaN stacks
        fill = np.fmin.reduce(neighbors, axis=0)
        take = prev_nan & ~np.isnan(fill)
        ref[take] = fill[take]
        if not take.any():
            break
    ref = np.where(np.isnan(ref), dem, ref)
    return np.clip(dem - ref, 0.0, None)
