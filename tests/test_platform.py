"""Platform tests: label store, alert engine, nowcast pipeline, and API."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from satpi.config import AlertRule, Settings, StudyArea
from satpi.dynamics.pipeline import run_nowcast_cycle
from satpi.platform.labels import LabelStore
from satpi.serving.alerts import DISCLAIMER, evaluate_rules
from satpi.serving.api import create_app

AREA = StudyArea.from_yaml("configs/study_areas/sw_pennsylvania.yaml")


# --------------------------------------------------------------------------- #
# label store
# --------------------------------------------------------------------------- #


def test_label_store_roundtrip_and_supersede(tmp_path):
    store = LabelStore(tmp_path, "sw_pennsylvania")
    a = store.add(tier=1, event_id="ida-2021", geometry_ref="s3://x/mask.tif", source="analyst")
    b = store.add(tier=2, event_id="ida-2021", geometry_ref="s3://x/gfm.tif", source="gfm-v3")
    assert {r.label_id for r in store.active("ida-2021")} == {a.label_id, b.label_id}
    assert store.active(tier=1)[0].reliability == 1.0

    c = store.add(tier=2, event_id="ida-2021", geometry_ref="s3://x/gfm2.tif", source="gfm-v4")
    store.supersede(b.label_id, c)
    active_ids = {r.label_id for r in store.active("ida-2021")}
    assert b.label_id not in active_ids and c.label_id in active_ids


def test_label_store_rejects_bad_tier(tmp_path):
    with pytest.raises(ValueError):
        LabelStore(tmp_path, "x").add(tier=4, event_id="e", geometry_ref="g", source="s")  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# alerts
# --------------------------------------------------------------------------- #


def test_alert_triggers_and_carries_disclaimer():
    exceedance = np.zeros((10, 10))
    exceedance[0:3, 0:3] = 0.9
    zone = np.zeros((10, 10), bool)
    zone[0:3, 0:3] = True
    rules = [
        AlertRule(name="hot", geometry="z1", probability_threshold=0.4, channels=["log"]),
        AlertRule(name="cold", geometry="z2", probability_threshold=0.4, channels=["log"]),
    ]
    masks = {"z1": zone, "z2": ~zone}
    alerts = evaluate_rules(rules, exceedance, masks)
    assert [a.rule_name for a in alerts] == ["hot"]
    assert alerts[0].disclaimer == DISCLAIMER


def test_alert_unknown_zone_is_skipped_not_fatal():
    rules = [AlertRule(name="r", geometry="missing", probability_threshold=0.1)]
    assert evaluate_rules(rules, np.ones((2, 2)), {}) == []


# --------------------------------------------------------------------------- #
# nowcast pipeline (end-to-end, degraded mode)
# --------------------------------------------------------------------------- #


def test_nowcast_cycle_end_to_end():
    n = 48
    yy, xx = np.mgrid[0:n, 0:n].astype(float)
    dem = 300.0 + 0.3 * yy + np.abs(xx - n / 2)  # gentle valley
    products, members = run_nowcast_cycle(
        area=AREA,
        dem_coarse=dem,
        rainfall_ms=15e-3 / 3600.0,
        gauge_obs=[],
        horizon_hours=0.25,
        seed=42,
    )
    assert len(members) == AREA.solver.ensemble_members
    assert products.degraded is True  # no downscaler installed in core tests
    assert products.mean_depth.shape == dem.shape
    assert products.spread.min() >= 0.0
    assert 0.0 <= products.exceedance_15cm.min() and products.exceedance_15cm.max() <= 1.0
    # rain fell: some water somewhere
    assert products.mean_depth.max() > 0.0
    # physics governance metrics are attached
    assert "mass_conservation_residual" in products.consistency
    assert products.consistency["uphill_flow_violation"] <= 0.05  # solver output ~consistent


def test_nowcast_cycle_reproducible():
    dem = np.zeros((16, 16))
    p1, _ = run_nowcast_cycle(AREA, dem, 1e-6, [], horizon_hours=0.1, seed=7)
    p2, _ = run_nowcast_cycle(AREA, dem, 1e-6, [], horizon_hours=0.1, seed=7)
    np.testing.assert_allclose(p1.mean_depth, p2.mean_depth)


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


@pytest.fixture()
def client():
    settings = Settings(
        api_auth_token="test-token",
        study_area_config="configs/study_areas/sw_pennsylvania.yaml",
    )
    app = create_app(settings=settings, area=AREA)
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["study_area"] == "sw_pennsylvania"


def test_latest_product_404_then_200(client):
    assert client.get("/v1/products/latest").status_code == 404
    # publish a cycle into the hot store, as the scheduler does
    dem = np.zeros((16, 16))
    products, _ = run_nowcast_cycle(AREA, dem, 5e-6, [], horizon_hours=0.1)
    client.app.state.store.put("nowcast", products)
    r = client.get("/v1/products/latest")
    assert r.status_code == 200
    body = r.json()
    assert body["degraded"] is True
    assert "mass_conservation_residual" in body["consistency"]


def test_scenario_requires_auth(client):
    payload = {"interventions": [{"node": "imperviousness", "scale": 0.8}]}
    assert client.post("/v1/scenarios/run", json=payload).status_code == 401
    r = client.post(
        "/v1/scenarios/run", json=payload, headers={"Authorization": "Bearer test-token"}
    )
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
    assert "not forecasts" in r.json()["note"]


def test_scenario_rejects_unknown_node(client):
    r = client.post(
        "/v1/scenarios/run",
        json={"interventions": [{"node": "dragons", "scale": 0.5}]},
        headers={"Authorization": "Bearer test-token"},
    )
    assert r.status_code == 422


def test_dashboard_renders(client):
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "SatPI Flood Intelligence" in r.text
    assert "National Weather Service" in r.text  # disclaimer present
    # basemap + data attribution required by CARTO/OSM, Copernicus and NOAA terms
    assert "OpenStreetMap" in r.text and "CARTO" in r.text
    assert "contains modified Copernicus Sentinel data" in r.text


def test_dashboard_appends_basemap_key():
    from satpi.serving.dashboard import render_dashboard

    html = render_dashboard(AREA, Settings(basemap_api_key="abc123"))
    assert "style.json?key=abc123" in html


def test_study_area_endpoint_hides_sensitive_lists(client):
    body = client.get("/v1/study-area").json()
    assert "gauges" not in body and body["n_gauges"] == len(AREA.gauges)
