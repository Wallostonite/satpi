"""Configuration system.

The central design contract of SatPI is that *everything region-specific lives in
a StudyArea config file*. Code never hard-codes coordinates, gauge IDs, CRS,
data endpoints, or thresholds. To deploy in a new region you write one YAML file
(see configs/study_areas/_template.yaml) and re-run the pipeline.

All configs are validated with pydantic at load time so misconfiguration fails
fast and loudly, before any data is pulled or any model is run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BoundingBox(BaseModel):
    """Geographic bounding box in EPSG:4326 (lon/lat)."""

    west: float = Field(ge=-180, le=180)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)

    @model_validator(mode="after")
    def _ordered(self) -> BoundingBox:
        if self.west >= self.east:
            raise ValueError("west must be < east")
        if self.south >= self.north:
            raise ValueError("south must be < north")
        return self

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.west, self.south, self.east, self.north)


class GaugeStation(BaseModel):
    """A stream gauge used for assimilation and validation."""

    provider: Literal["usgs", "other"] = "usgs"
    station_id: str
    name: str = ""
    river: str = ""
    # Stage thresholds (meters, gauge datum) for alerting; region-specific.
    action_stage_m: float | None = None
    flood_stage_m: float | None = None


class ForcingSource(BaseModel):
    """A meteorological / hydrologic forcing product.

    New regions swap sources here (e.g., MRMS -> OPERA/EUMETSAT radar in Europe)
    without touching pipeline code: each `kind` maps to a registered ingestor.
    """

    kind: Literal["mrms_qpe", "hrrr", "gfs", "nwm", "generic_grib", "generic_zarr"]
    enabled: bool = True
    endpoint: str = ""  # base URL / bucket; ingestors supply sensible defaults
    variables: list[str] = Field(default_factory=list)


class SatelliteSource(BaseModel):
    kind: Literal["sentinel1", "sentinel2", "hls", "landsat"]
    enabled: bool = True
    stac_endpoint: str = "https://earth-search.aws.element84.com/v1"
    collection: str = ""

    @model_validator(mode="after")
    def _default_collection(self) -> SatelliteSource:
        defaults = {
            "sentinel1": "sentinel-1-grd",
            "sentinel2": "sentinel-2-l2a",
            "hls": "hls",
            "landsat": "landsat-c2-l2",
        }
        if not self.collection:
            self.collection = defaults[self.kind]
        return self


class WeakLabelSource(BaseModel):
    """Point/polygon flood evidence with a reliability weight in [0, 1]."""

    name: str
    kind: Literal["socrata_311", "openfema_nfip", "nws_lsr", "usgs_hwm", "csv"]
    endpoint: str = ""
    reliability: float = Field(default=0.5, ge=0.0, le=1.0)
    enabled: bool = True


class TerrainConfig(BaseModel):
    dem_path: str  # path or URL to the high-res DEM (COG)
    dem_resolution_m: float = 1.0
    solver_resolution_m: float = 90.0
    output_resolution_m: float = 10.0
    hydro_conditioned: bool = False


class SolverConfig(BaseModel):
    scheme: Literal["diffusive_wave", "kinematic", "external"] = "diffusive_wave"
    dt_seconds: float = Field(default=10.0, gt=0)
    manning_n_default: float = Field(default=0.05, gt=0)
    ensemble_members: int = Field(default=10, ge=1, le=100)
    max_runtime_minutes: float = 10.0


class AlertRule(BaseModel):
    name: str
    geometry: str  # named zone id registered in the platform (e.g., "route-51-corridor")
    probability_threshold: float = Field(ge=0.0, le=1.0)
    min_depth_m: float = 0.0
    channels: list[Literal["webhook", "email", "log"]] = Field(default_factory=lambda: ["log"])


class StudyArea(BaseModel):
    """Complete, self-contained description of a deployment region.

    Adapting the platform to a new region == writing one of these.
    """

    id: str = Field(pattern=r"^[a-z0-9_\-]+$")
    name: str
    bbox: BoundingBox
    crs_epsg: int = Field(description="Projected CRS for analysis, e.g. UTM zone")
    timezone: str = "UTC"
    huc_codes: list[str] = Field(default_factory=list, description="Basin codes (HUC in US)")
    gauges: list[GaugeStation] = Field(default_factory=list)
    forcing: list[ForcingSource] = Field(default_factory=list)
    satellites: list[SatelliteSource] = Field(default_factory=list)
    weak_labels: list[WeakLabelSource] = Field(default_factory=list)
    terrain: TerrainConfig
    solver: SolverConfig = SolverConfig()
    alert_rules: list[AlertRule] = Field(default_factory=list)
    # Free-form region metadata (e.g., mining layers) forwarded to feature builder
    extra_static_layers: dict[str, str] = Field(default_factory=dict)

    @field_validator("crs_epsg")
    @classmethod
    def _valid_epsg(cls, v: int) -> int:
        if not (1024 <= v <= 32767):
            raise ValueError(f"implausible EPSG code: {v}")
        return v

    @classmethod
    def from_yaml(cls, path: str | Path) -> StudyArea:
        with open(path) as f:
            raw = yaml.safe_load(f)
        return cls.model_validate(raw)


class Settings(BaseSettings):
    """Process-level settings from environment (12-factor)."""

    model_config = SettingsConfigDict(env_prefix="SATPI_", env_file=".env", extra="ignore")

    environment: Literal["dev", "staging", "prod"] = "dev"
    data_root: Path = Path("./data")
    study_area_config: Path = Path("configs/study_areas/sw_pennsylvania.yaml")
    database_url: str = "postgresql://satpi:satpi@localhost:5432/satpi"
    redis_url: str = "redis://localhost:6379/0"
    mlflow_tracking_uri: str = ""
    log_level: str = "INFO"
    api_auth_token: str = ""  # empty => read-only public mode
    # Dashboard basemap. CARTO basemaps are free for non-commercial use within
    # CARTO's tile limits and must credit OpenStreetMap and CARTO; a free CARTO
    # key (carto.com/basemaps/apikey) is recommended. See DATA_SOURCES.md.
    basemap_style_url: str = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
    basemap_api_key: str = ""
    basemap_attribution: str = (
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
        'contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
    )


def load_study_area(settings: Settings | None = None) -> StudyArea:
    settings = settings or Settings()
    return StudyArea.from_yaml(settings.study_area_config)
