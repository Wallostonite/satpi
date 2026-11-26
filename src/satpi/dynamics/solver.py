"""Coarse 2-D diffusive-wave overland-flow solver.

This is the reference implementation of the physics prior: an explicit
finite-volume diffusive-wave (zero-inertia) scheme in the LISFLOOD-FP family,
operating on the coarsened, hydro-conditioned DEM defined by the StudyArea
config. It is deliberately simple, fully vectorized numpy, and correct for the
role it plays — producing physically consistent coarse inundation that the ML
downscaler refines.

Production notes
----------------
- `scheme: external` in SolverConfig swaps this out for LISFLOOD-FP / SERGHEI
  via the same `SolverState -> SolverState` interface; nothing downstream
  changes. This reference solver keeps the platform runnable end-to-end with
  zero external binaries, which CI relies on.
- Stability: explicit diffusive wave requires dt <~ dx^2-ish limits; we apply
  the standard adaptive flow-limiter (cap inter-cell flux at the volume that
  equalizes water surfaces) which keeps the scheme robust at practical dt.
- Units: SI throughout. Rainfall in m/s, depths in m, discharge in m^3/s.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class SolverState:
    """Water state on the coarse grid."""

    depth: np.ndarray  # (H, W) water depth, m
    t_seconds: float = 0.0

    def copy(self) -> SolverState:
        return SolverState(depth=self.depth.copy(), t_seconds=self.t_seconds)


@dataclass
class DiffusiveWaveSolver:
    dem: np.ndarray  # (H, W) coarse DEM, m
    cell_size_m: float
    manning_n: np.ndarray | float = 0.05  # scalar or (H, W) roughness field
    dt_seconds: float = 10.0
    min_depth_m: float = 1e-4  # cells shallower than this don't convey
    nodata_mask: np.ndarray | None = None  # True where outside domain
    boundary_cells: list[tuple[int, int]] = field(default_factory=list)  # inflow points

    def __post_init__(self) -> None:
        self.dem = np.asarray(self.dem, dtype=np.float64)
        if np.isscalar(self.manning_n):
            self.manning_n = np.full_like(self.dem, float(self.manning_n))
        if self.nodata_mask is None:
            self.nodata_mask = np.zeros(self.dem.shape, dtype=bool)

    # ------------------------------------------------------------------ #

    def _face_flux(self, wse: np.ndarray, depth: np.ndarray, axis: int) -> np.ndarray:
        """Manning-based unit discharge across faces along `axis` (positive =
        flow from lower-index cell to higher-index cell)."""
        sl = [slice(None)] * 2
        sl_lo, sl_hi = list(sl), list(sl)
        sl_lo[axis] = slice(0, -1)
        sl_hi[axis] = slice(1, None)
        wse_lo, wse_hi = wse[tuple(sl_lo)], wse[tuple(sl_hi)]
        # Water-surface slope at the face
        slope = (wse_lo - wse_hi) / self.cell_size_m
        # Conveyance depth: flow depth at the face = max WSE minus max bed
        dem_lo, dem_hi = self.dem[tuple(sl_lo)], self.dem[tuple(sl_hi)]
        hflow = np.maximum(wse_lo, wse_hi) - np.maximum(dem_lo, dem_hi)
        hflow = np.clip(hflow, 0.0, None)
        n_face = 0.5 * (self.manning_n[tuple(sl_lo)] + self.manning_n[tuple(sl_hi)])
        conveys = hflow > self.min_depth_m
        q = np.zeros_like(slope)
        s_abs = np.abs(slope[conveys])
        # Manning: q = h^(5/3) * sqrt(S) / n   [m^2/s per unit width]
        q[conveys] = (
            np.sign(slope[conveys])
            * (hflow[conveys] ** (5.0 / 3.0))
            * np.sqrt(s_abs + 1e-12)
            / n_face[conveys]
        )
        # Flow limiter: a face may not move more volume in dt than would
        # equalize the two water surfaces (prevents explicit-scheme oscillation).
        vol_move = np.abs(q) * self.dt_seconds * self.cell_size_m  # m^3 per face
        vol_eq = 0.25 * np.abs(wse_lo - wse_hi) * self.cell_size_m**2
        scale = np.ones_like(vol_move)
        moving = vol_move > 1e-12
        scale[moving] = np.minimum(1.0, vol_eq[moving] / vol_move[moving])
        q *= scale
        # No flux across nodata boundaries
        nod = self.nodata_mask[tuple(sl_lo)] | self.nodata_mask[tuple(sl_hi)]
        q[nod] = 0.0
        return q

    def step(
        self,
        state: SolverState,
        rainfall_ms: np.ndarray | float = 0.0,
        inflow_cms: dict[tuple[int, int], float] | None = None,
        infiltration_ms: np.ndarray | float = 0.0,
    ) -> SolverState:
        """Advance one dt. rainfall/infiltration are rates (m/s); inflow_cms
        maps boundary cells (from NWM reach coupling) to discharge (m^3/s)."""
        depth = state.depth.copy()
        cell_area = self.cell_size_m**2

        # Sources / sinks
        depth += (np.asarray(rainfall_ms) - np.asarray(infiltration_ms)) * self.dt_seconds
        np.clip(depth, 0.0, None, out=depth)
        if inflow_cms:
            for (i, j), q in inflow_cms.items():
                depth[i, j] += q * self.dt_seconds / cell_area

        wse = self.dem + depth
        qx = self._face_flux(wse, depth, axis=1)  # (H, W-1)
        qy = self._face_flux(wse, depth, axis=0)  # (H-1, W)

        # Divergence -> depth update (unit-width q * face length / cell area)
        f = self.dt_seconds / self.cell_size_m
        depth[:, :-1] -= qx * f
        depth[:, 1:] += qx * f
        depth[:-1, :] -= qy * f
        depth[1:, :] += qy * f

        np.clip(depth, 0.0, None, out=depth)
        depth[self.nodata_mask] = 0.0
        return SolverState(depth=depth, t_seconds=state.t_seconds + self.dt_seconds)

    def run(
        self,
        hours: float,
        rainfall_ms: np.ndarray | float = 0.0,
        inflow_cms: dict[tuple[int, int], float] | None = None,
        initial: SolverState | None = None,
        snapshot_every_s: float | None = None,
    ) -> tuple[SolverState, list[np.ndarray]]:
        """Run for `hours` under constant forcing; returns final state and
        optional depth snapshots (for monotonicity checks / animation)."""
        state = initial.copy() if initial else SolverState(depth=np.zeros_like(self.dem))
        snapshots: list[np.ndarray] = []
        n_steps = int(round(hours * 3600.0 / self.dt_seconds))
        next_snap = snapshot_every_s or float("inf")
        for _ in range(n_steps):
            state = self.step(state, rainfall_ms=rainfall_ms, inflow_cms=inflow_cms)
            if state.t_seconds >= next_snap:
                snapshots.append(state.depth.copy())
                next_snap += snapshot_every_s  # type: ignore[operator]
        return state, snapshots

    # ------------------------------------------------------------------ #

    def total_volume(self, state: SolverState) -> float:
        """Domain water volume (m^3) — used by conservation tests."""
        return float(state.depth[~self.nodata_mask].sum() * self.cell_size_m**2)
