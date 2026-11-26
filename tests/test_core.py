"""Core platform tests — run without ml/geo extras (CI fast path)."""

from __future__ import annotations

import numpy as np
import pytest

from satpi.causal.scm import Intervention, StructuralCausalModel, pseudo_global_warming_delta
from satpi.config import BoundingBox, StudyArea
from satpi.dynamics.assimilation import (
    GaugeObservation,
    blend_satellite_state,
    exceedance_probability,
    nudge_to_gauges,
)
from satpi.dynamics.solver import DiffusiveWaveSolver, SolverState
from satpi.models.physics import (
    depth_extent_monotonicity,
    mass_conservation_residual,
    uphill_flow_violation,
)
from satpi.preprocessing.terrain import coarsen, hand, slope_magnitude

# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #


def test_reference_config_validates():
    area = StudyArea.from_yaml("configs/study_areas/sw_pennsylvania.yaml")
    assert area.id == "sw_pennsylvania"
    assert area.terrain.solver_resolution_m > area.terrain.output_resolution_m
    assert any(g.station_id == "03049500" for g in area.gauges)


def test_template_config_validates():
    area = StudyArea.from_yaml("configs/study_areas/_template.yaml")
    assert area.id == "my_region"


def test_bbox_rejects_inverted():
    with pytest.raises(ValueError):
        BoundingBox(west=1, south=0, east=0, north=1)


# --------------------------------------------------------------------------- #
# physics constraints
# --------------------------------------------------------------------------- #


def test_mass_conservation_perfect_and_violated():
    coarse = np.array([[1.0, 0.0], [0.0, 2.0]])
    scale = 2
    fine_ok = np.zeros((4, 4))
    fine_ok[0:2, 0:2] = 1.0  # redistributed but same mean per block
    fine_ok[2:4, 2:4] = 2.0
    assert mass_conservation_residual(fine_ok, coarse, scale) == pytest.approx(0.0)

    fine_bad = fine_ok.copy()
    fine_bad[0:2, 0:2] = 3.0  # tripled the water in block (0,0)
    assert mass_conservation_residual(fine_bad, coarse, scale) > 0.5


def test_mass_conservation_allows_within_block_redistribution():
    coarse = np.array([[1.0]])
    fine = np.array([[4.0, 0.0], [0.0, 0.0]])  # all block water in one cell
    assert mass_conservation_residual(fine, coarse, 2) == pytest.approx(0.0)


def test_uphill_flow_flags_perched_water():
    dem = np.array([[10.0, 0.0], [10.0, 0.0]])
    depth = np.array([[2.0, 0.0], [2.0, 0.0]])  # deep water perched above dry low ground
    assert uphill_flow_violation(depth, dem) == 1.0
    # water in the low cells instead: no violation
    depth_ok = np.array([[0.0, 2.0], [0.0, 2.0]])
    assert uphill_flow_violation(depth_ok, dem) == 0.0


def test_monotonicity():
    grow = np.zeros((3, 4, 4))
    grow[0, 0, 0] = 1.0
    grow[1, 0:2, 0:2] = 1.0
    grow[2] = 1.0
    assert depth_extent_monotonicity(grow) == pytest.approx(0.0)
    shrink = grow[::-1].copy()
    assert depth_extent_monotonicity(shrink) > 0.0


# --------------------------------------------------------------------------- #
# solver
# --------------------------------------------------------------------------- #


def _flat_solver(n=16, cell=90.0):
    return DiffusiveWaveSolver(dem=np.zeros((n, n)), cell_size_m=cell, dt_seconds=5.0)


def test_solver_conserves_mass_closed_domain():
    solver = _flat_solver()
    state = SolverState(depth=np.zeros((16, 16)))
    state.depth[8, 8] = 2.0  # 2 m column released on flat ground
    v0 = solver.total_volume(state)
    for _ in range(200):
        state = solver.step(state)
    assert solver.total_volume(state) == pytest.approx(v0, rel=1e-9)
    # and it spread out
    assert state.depth.max() < 2.0
    assert (state.depth > 1e-6).sum() > 1


def test_solver_water_flows_downhill():
    n = 32
    dem = np.tile(np.linspace(10, 0, n), (n, 1))  # west high, east low
    solver = DiffusiveWaveSolver(dem=dem, cell_size_m=90.0, dt_seconds=5.0)
    state = SolverState(depth=np.zeros((n, n)))
    state.depth[:, 2] = 1.0
    com0 = float((state.depth.sum(axis=0) * np.arange(n)).sum() / state.depth.sum())
    for _ in range(2000):
        state = solver.step(state)
    com = float((state.depth.sum(axis=0) * np.arange(n)).sum() / state.depth.sum())
    assert com > com0 + 5  # center of mass moved well downslope (east)
    assert state.depth[:, :3].sum() < 0.05 * state.depth.sum()  # source cells drained


def test_solver_rainfall_and_positivity():
    solver = _flat_solver(n=8)
    state = SolverState(depth=np.zeros((8, 8)))
    rain = 20e-3 / 3600.0  # 20 mm/h
    state, _ = solver.run(hours=1.0, rainfall_ms=rain, initial=state)
    assert state.depth.min() >= 0.0
    assert state.depth.mean() == pytest.approx(0.02, rel=1e-6)  # 20 mm accumulated


def test_solver_inflow_coupling():
    solver = _flat_solver(n=8)
    state = SolverState(depth=np.zeros((8, 8)))
    state = solver.step(state, inflow_cms={(4, 0): 81.0})  # 81 m^3/s for 5 s into 8100 m^2
    assert solver.total_volume(state) == pytest.approx(81.0 * 5.0, rel=1e-9)


# --------------------------------------------------------------------------- #
# assimilation
# --------------------------------------------------------------------------- #


def test_gauge_nudging_moves_toward_observation():
    state = SolverState(depth=np.zeros((20, 20)))
    obs = [GaugeObservation(cell=(10, 10), stage_m=1.0)]
    nudged = nudge_to_gauges(state, obs, dem=np.zeros((20, 20)), relaxation=0.5)
    assert nudged.depth[10, 10] == pytest.approx(0.5)
    assert nudged.depth[10, 12] > 0.0  # spatial spread
    assert nudged.depth[0, 0] == pytest.approx(0.0)  # beyond influence radius


def test_satellite_blend_never_fully_replaces_model():
    state = SolverState(depth=np.ones((4, 4)))
    sat = np.zeros((4, 4))
    conf = np.ones((4, 4))
    blended = blend_satellite_state(state, sat, conf, max_weight=0.8)
    assert blended.depth[0, 0] == pytest.approx(0.2)


def test_exceedance_probability():
    members = [np.full((2, 2), 0.1), np.full((2, 2), 0.3), np.full((2, 2), 0.5)]
    p = exceedance_probability(members, threshold_m=0.2)
    assert p[0, 0] == pytest.approx(2 / 3)


# --------------------------------------------------------------------------- #
# causal SCM
# --------------------------------------------------------------------------- #


def _toy_scm() -> StructuralCausalModel:
    scm = StructuralCausalModel(
        edges=[("precipitation", "runoff"), ("imperviousness", "runoff"), ("runoff", "inundation")]
    )
    scm.add_mechanism("runoff", lambda p: p["precipitation"] * (0.3 + 0.7 * p["imperviousness"]))
    scm.add_mechanism("inundation", lambda p: 2.0 * p["runoff"])
    return scm


def test_scm_baseline_and_intervention():
    scm = _toy_scm()
    exo = {"precipitation": 10.0, "imperviousness": 0.5}
    base = scm.run(exo, targets=["inundation"])
    assert base.outputs["inundation"] == pytest.approx(2 * 10 * 0.65)
    # do(imperviousness := 0.4): green-infrastructure scenario
    alt = scm.run(exo, ["inundation"], [Intervention(node="imperviousness", value=0.4)])
    assert alt.outputs["inundation"] < base.outputs["inundation"]
    assert alt.is_counterfactual


def test_scm_scale_intervention():
    scm = _toy_scm()
    exo = {"precipitation": 10.0, "imperviousness": 0.5}
    alt = scm.run(exo, ["inundation"], [Intervention(node="runoff", scale=0.5)])
    base = scm.run(exo, ["inundation"])
    assert alt.outputs["inundation"] == pytest.approx(0.5 * base.outputs["inundation"])


def test_scm_missing_mechanism_fails_fast():
    scm = StructuralCausalModel(edges=[("a", "b"), ("b", "c")])
    scm.add_mechanism("c", lambda p: p["b"])
    with pytest.raises(ValueError, match="no mechanism"):
        scm.run({"a": 1.0}, targets=["c"])


def test_scm_rejects_cycles():
    with pytest.raises(ValueError, match="DAG"):
        StructuralCausalModel(edges=[("a", "b"), ("b", "a")])


def test_pgw_scaling():
    assert pseudo_global_warming_delta(np.array(100.0), delta_temp_c=2.0) == pytest.approx(
        100 * 1.07**2
    )


# --------------------------------------------------------------------------- #
# terrain preprocessing
# --------------------------------------------------------------------------- #


def test_coarsen_mean_and_min():
    f = np.arange(16, dtype=float).reshape(4, 4)
    c = coarsen(f, 2, "mean")
    assert c.shape == (2, 2)
    assert c[0, 0] == pytest.approx(f[0:2, 0:2].mean())
    assert coarsen(f, 2, "min")[0, 0] == 0.0


def test_hand_valley():
    n = 9
    dem = np.tile(np.abs(np.arange(n) - n // 2).astype(float) * 5, (n, 1))  # V-valley
    drainage = np.zeros((n, n), bool)
    drainage[:, n // 2] = True  # channel at valley floor
    h = hand(dem, drainage)
    assert (h[:, n // 2] == 0).all()
    assert h[0, 0] == pytest.approx(dem[0, 0])  # ridge height above channel


def test_slope():
    dem = np.tile(np.arange(5, dtype=float), (5, 1))  # 1 m rise per cell
    s = slope_magnitude(dem, cell_size_m=1.0)
    assert s[2, 2] == pytest.approx(1.0)
