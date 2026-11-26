"""Nowcast / forecast cycle orchestration.

`run_nowcast_cycle` is the unit the scheduler (Prefect/Airflow in deployment,
CLI in dev) executes every cycle. It is a pure function of (study area config,
forcing, prior state, observations) -> products, which makes cycles idempotent,
replayable from the catalog, and trivially parallel across ensemble members.

Graceful degradation (NFR): if the downscaler is unavailable the cycle
publishes the coarse solver field with a `degraded` flag rather than failing —
an operational map that is coarse beats no map.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np
import structlog

from satpi.config import StudyArea
from satpi.dynamics.assimilation import (
    GaugeObservation,
    ensemble_spread,
    exceedance_probability,
    nudge_to_gauges,
)
from satpi.dynamics.solver import DiffusiveWaveSolver, SolverState
from satpi.models.physics import physical_consistency_score

log = structlog.get_logger()


@dataclass
class CycleProducts:
    cycle_time: str
    study_area_id: str
    mean_depth: np.ndarray
    spread: np.ndarray
    exceedance_15cm: np.ndarray
    degraded: bool
    consistency: dict[str, float]
    meta: dict[str, Any] = field(default_factory=dict)


def perturb_forcing(
    rainfall_ms: np.ndarray | float, member: int, n_members: int, rng: np.random.Generator
) -> np.ndarray | float:
    """Simple multiplicative log-normal forcing perturbation for the pilot
    ensemble; replaced by true NWP ensemble members (HRRR/GFS) when available."""
    factor = float(rng.lognormal(mean=0.0, sigma=0.25))
    return rainfall_ms * factor


def run_nowcast_cycle(
    area: StudyArea,
    dem_coarse: np.ndarray,
    rainfall_ms: np.ndarray | float,
    gauge_obs: list[GaugeObservation],
    prior_states: list[SolverState] | None = None,
    horizon_hours: float = 1.0,
    downscaler: Any = None,  # torch module or None (degraded mode)
    dem_fine: np.ndarray | None = None,
    seed: int = 0,
) -> tuple[CycleProducts, list[SolverState]]:
    rng = np.random.default_rng(seed)
    n = area.solver.ensemble_members
    solver = DiffusiveWaveSolver(
        dem=dem_coarse,
        cell_size_m=area.terrain.solver_resolution_m,
        manning_n=area.solver.manning_n_default,
        dt_seconds=area.solver.dt_seconds,
    )
    if prior_states is None:
        prior_states = [SolverState(depth=np.zeros_like(dem_coarse, dtype=float)) for _ in range(n)]
    if len(prior_states) != n:
        raise ValueError(f"expected {n} prior states, got {len(prior_states)}")

    members: list[SolverState] = []
    for m, prior in enumerate(prior_states):
        forcing = perturb_forcing(rainfall_ms, m, n, rng)
        state, _ = solver.run(hours=horizon_hours, rainfall_ms=forcing, initial=prior)
        state = nudge_to_gauges(state, gauge_obs, dem_coarse)
        members.append(state)

    depths = [s.depth for s in members]
    mean_coarse = np.mean(np.stack(depths), axis=0)

    degraded = downscaler is None or dem_fine is None
    if degraded:
        fine = mean_coarse  # publish coarse field, flagged
        scale = 1
        dem_for_score = dem_coarse
    else:  # pragma: no cover - requires ml extra
        import torch

        scale = int(round(area.terrain.solver_resolution_m / area.terrain.output_resolution_m))
        with torch.no_grad():
            coarse_t = torch.from_numpy(mean_coarse).float()[None, None]
            up = torch.nn.functional.interpolate(
                coarse_t, scale_factor=scale, mode="bilinear", align_corners=False
            )
            static = torch.from_numpy(dem_fine).float()[None, None]
            fine = downscaler(up, static)[0, 0].numpy()
        dem_for_score = dem_fine

    consistency = physical_consistency_score(
        depth_fine=fine, depth_coarse=mean_coarse, dem_fine=dem_for_score, scale=scale
    )

    products = CycleProducts(
        cycle_time=datetime.now(UTC).isoformat(),
        study_area_id=area.id,
        mean_depth=fine,
        spread=ensemble_spread(depths),
        exceedance_15cm=exceedance_probability(depths, threshold_m=0.15),
        degraded=degraded,
        consistency=consistency,
        meta={"members": n, "horizon_hours": horizon_hours},
    )
    log.info(
        "cycle.complete",
        area=area.id,
        degraded=degraded,
        **{k: round(v, 4) for k, v in consistency.items()},
    )
    return products, members
