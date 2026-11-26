"""API schemas (module-level so FastAPI resolves postponed annotations)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthOut(BaseModel):
    status: str
    version: str
    study_area: str
    environment: str


class ProductSummary(BaseModel):
    cycle_time: str
    degraded: bool
    consistency: dict[str, float]
    wet_fraction: float = Field(description="fraction of domain with depth > 15 cm")


class ScenarioRequest(BaseModel):
    interventions: list[dict[str, Any]]
    targets: list[str] = ["inundation"]
