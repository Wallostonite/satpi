"""Serving API.

Read endpoints are public; mutating/scenario endpoints require a bearer token
(SATPI_API_AUTH_TOKEN). Products are served from the hot store the pipeline
writes; the API never computes — it serves, which keeps request latency
independent of model runtime and lets the API tier scale horizontally.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

import numpy as np
import structlog
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import HTMLResponse

from satpi import __version__
from satpi.config import Settings, StudyArea, load_study_area
from satpi.serving.schemas import HealthOut, ProductSummary, ScenarioRequest

log = structlog.get_logger()


# --- app state (hot store handle) ------------------------------------------ #


class HotStore:
    """In-memory latest-products cache. Redis/PostGIS-backed in deployment;
    the interface (get/put latest) is identical."""

    def __init__(self) -> None:
        self.latest: dict[str, Any] = {}

    def put(self, key: str, value: Any) -> None:
        self.latest[key] = {"at": datetime.now(UTC).isoformat(), "value": value}

    def get(self, key: str) -> Any | None:
        return self.latest.get(key)


def create_app(settings: Settings | None = None, area: StudyArea | None = None) -> FastAPI:
    settings = settings or Settings()
    area = area or load_study_area(settings)
    app = FastAPI(
        title="SatPI Flood Intelligence API",
        version=__version__,
        description=f"Deployment: {area.name}",
    )
    store = HotStore()
    app.state.store = store
    app.state.area = area
    app.state.settings = settings

    def require_auth(authorization: Annotated[str | None, Header()] = None) -> None:
        token = settings.api_auth_token
        if not token:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "write API disabled (no token configured)"
            )
        if authorization != f"Bearer {token}":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")

    # --- routes -------------------------------------------------------- #

    @app.get("/health", response_model=HealthOut, tags=["ops"])
    def health() -> HealthOut:
        return HealthOut(
            status="ok",
            version=__version__,
            study_area=area.id,
            environment=settings.environment,
        )

    @app.get("/v1/study-area", tags=["metadata"])
    def study_area() -> dict[str, Any]:
        return area.model_dump(exclude={"gauges", "alert_rules"}) | {
            "n_gauges": len(area.gauges),
            "n_alert_rules": len(area.alert_rules),
        }

    @app.get("/v1/products/latest", response_model=ProductSummary, tags=["products"])
    def latest_product() -> ProductSummary:
        item = store.get("nowcast")
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no cycle published yet")
        p = item["value"]
        wet = float((np.asarray(p.mean_depth) > 0.15).mean())
        return ProductSummary(
            cycle_time=p.cycle_time,
            degraded=p.degraded,
            consistency=p.consistency,
            wet_fraction=round(wet, 4),
        )

    @app.get("/v1/gauges", tags=["metadata"])
    def gauges() -> list[dict[str, Any]]:
        return [g.model_dump() for g in area.gauges]

    @app.post("/v1/scenarios/run", tags=["scenarios"], dependencies=[Depends(require_auth)])
    def run_scenario(req: ScenarioRequest) -> dict[str, Any]:
        # Scenario execution is queued to workers in deployment; the pilot
        # endpoint validates the request against the SCM and enqueues.
        from satpi.causal.scm import Intervention, StructuralCausalModel

        scm = StructuralCausalModel()
        try:
            ivs = [Intervention(**iv) for iv in req.interventions]
            for iv in ivs:
                if iv.node not in scm.graph:
                    raise KeyError(iv.node)
        except (TypeError, ValueError, KeyError) as e:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"invalid intervention: {e}"
            ) from e
        job_id = f"scn-{datetime.now(UTC):%Y%m%d%H%M%S}"
        store.put(f"scenario:{job_id}", {"request": req.model_dump(), "status": "queued"})
        log.info("scenario.queued", job_id=job_id, interventions=len(ivs))
        return {
            "job_id": job_id,
            "status": "queued",
            "note": "scenario products are analyses, not forecasts",
        }

    @app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
    def dashboard() -> str:
        from satpi.serving.dashboard import render_dashboard

        return render_dashboard(area, settings)

    return app


app = create_app  # uvicorn factory: uvicorn "satpi.serving.api:app" --factory
