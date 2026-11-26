"""Operator CLI.

    satpi validate-config          # fail-fast check of a study-area YAML
    satpi run-cycle                # one nowcast cycle (synthetic demo forcing in dev)
    satpi serve                    # API + dashboard
    satpi discover-scenes          # STAC discovery over the AOI (network)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import typer

from satpi.config import Settings, StudyArea

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def validate_config(
    path: Path = typer.Option(  # noqa: B008  (typer idiom)
        None, help="Study-area YAML (defaults to SATPI_STUDY_AREA_CONFIG)"
    ),
) -> None:
    """Validate a study-area config; exits non-zero on failure."""
    cfg_path = path or Settings().study_area_config
    area = StudyArea.from_yaml(cfg_path)
    typer.echo(f"OK: {area.id} — {area.name}")
    typer.echo(f"    bbox={area.bbox.as_tuple()} crs=EPSG:{area.crs_epsg}")
    typer.echo(f"    gauges={len(area.gauges)} forcing={len(area.forcing)} "
               f"satellites={len(area.satellites)} alert_rules={len(area.alert_rules)}")


@app.command()
def run_cycle(
    demo: bool = typer.Option(True, help="Use synthetic terrain/forcing (no data downloads)"),
    horizon_hours: float = 1.0,
) -> None:
    """Run one nowcast cycle. Demo mode exercises the full solver->assimilation
    ->products path on synthetic terrain so new deployments can smoke-test
    before any data plumbing exists."""
    from satpi.dynamics.pipeline import run_nowcast_cycle

    settings = Settings()
    area = StudyArea.from_yaml(settings.study_area_config)
    if not demo:
        typer.echo("non-demo cycles require the geo extra + bootstrapped data", err=True)
        raise typer.Exit(2)
    # Synthetic valley terrain (a tilted plane with a channel) at coarse res
    h = w = 96
    yy, xx = np.mgrid[0:h, 0:w].astype(float)
    dem = 300.0 + 0.5 * yy + 8.0 * np.abs(xx - w / 2) / w * 10  # v-shaped valley
    rain = 10e-3 / 3600.0  # 10 mm/h in m/s
    products, _ = run_nowcast_cycle(
        area=area, dem_coarse=dem, rainfall_ms=rain, gauge_obs=[], horizon_hours=horizon_hours
    )
    wet = float((products.mean_depth > 0.15).mean())
    typer.echo(f"cycle {products.cycle_time} [{'DEGRADED' if products.degraded else 'nominal'}]")
    typer.echo(f"  wet fraction >15cm : {wet:.3%}")
    for k, v in products.consistency.items():
        typer.echo(f"  {k:<28}: {v:.5f}")


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Start the API + dashboard."""
    import uvicorn

    uvicorn.run("satpi.serving.api:app", host=host, port=port, factory=True)


@app.command()
def discover_scenes(days: int = 7) -> None:
    """List recent satellite scenes over the AOI (requires network)."""
    from satpi.ingestion.satellite import SatelliteDiscovery

    area = StudyArea.from_yaml(Settings().study_area_config)
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    for sat in area.satellites:
        if not sat.enabled:
            continue
        ing = SatelliteDiscovery(endpoint=sat.stac_endpoint)
        n = 0
        for asset in ing.fetch(start, end, bbox=area.bbox, collection=sat.collection, max_items=50):
            typer.echo(f"{asset.timestamp:%Y-%m-%d %H:%M}  {asset.source:<24} {asset.asset_id}")
            n += 1
        typer.echo(f"-- {sat.kind}: {n} scenes in last {days}d")


if __name__ == "__main__":
    app()
