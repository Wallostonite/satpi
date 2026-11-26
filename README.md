# SatPI-FM-CDT

[![CI](https://img.shields.io/badge/CI-GitHub_Actions-2088FF)](.github/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/code-Apache--2.0-blue)](LICENSE)
[![Data: see DATA_SOURCES](https://img.shields.io/badge/data-open%20sources%2C%20credited-3EA6C9)](DATA_SOURCES.md)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-informational)](pyproject.toml)

**Satellite-informed, physics-consistent, causal flood intelligence platform.**

SatPI fuses three subsystems, each doing what it is best at:

| Subsystem | Question | Implementation |
|---|---|---|
| Perception | *What is flooded?* | Fine-tuned geospatial foundation model (Clay / Prithvi) on Sentinel-1/2 — intermittent, high-resolution state estimation |
| Dynamics | *What will flood, when?* | Radar/NWP-forced coarse diffusive-wave solver + physics-regularized ML downscaler to 10 m, with gauge/satellite assimilation |
| Causation | *What if…?* | Structural causal model over the hydrologic driver graph — interventions (green infrastructure, culverts) and PGW climate counterfactuals |

The reference deployment is **Southwestern Pennsylvania** (Pittsburgh three-rivers region). The platform is **region-agnostic by construction**: everything region-specific lives in one YAML file. See [docs/ADAPTING.md](docs/ADAPTING.md).

## Quickstart

```bash
pip install -e ".[dev]"            # core platform (no heavy deps)
satpi validate-config              # check the study-area config
satpi run-cycle                    # end-to-end demo nowcast on synthetic terrain
satpi serve                        # API + ops dashboard at :8000/dashboard
pytest                             # full core test suite
```

Optional extras (install as needed):

```bash
pip install -e ".[geo]"            # rasterio/xarray/STAC — real data pipelines
pip install -e ".[ml]"             # torch/lightning/torchgeo — training & downscaler
pip install -e ".[causal]"         # dowhy/tigramite — causal edge testing
```

The split is deliberate: the API tier, solver, and CI never need torch or GDAL, so
they stay small, fast to build, and cheap to scale.

## Repository map

```
configs/study_areas/     Region configs. sw_pennsylvania.yaml = reference;
                         _template.yaml = start here for a new region.
src/satpi/
  config.py              Pydantic schemas — the region-portability contract
  ingestion/             USGS, STAC satellite discovery, MRMS/NWM (retry/backoff,
                         registered by config `kind`)
  preprocessing/         Terrain (HAND, slope, coarsening), optical indices
  dynamics/              Diffusive-wave solver · assimilation · nowcast cycles
  models/                physics.py (consistency constraints, numpy) ·
                         networks.py (GFM head + downscaler, torch, optional)
  causal/                Structural causal model, interventions, PGW scaling
  platform/              Tiered append-only label store, catalog interfaces
  serving/               FastAPI app · alert rules engine · ops dashboard
docker/                  Images + compose stack (API, worker, PostGIS, Redis)
docs/ADAPTING.md         Checklist for deploying a new study area
docs/ARCHITECTURE.md     Conceptual framework, system design, full-stack requirements
DATA_SOURCES.md          Every data source: license, attribution, citation
NOTICE · LICENSE         Required notices · Apache-2.0 code license
CITATION.cff             How to cite this software
```

## Operating model

- **Cycles are pure functions** (`dynamics/pipeline.py`): config + forcing +
  prior state + observations → products. Idempotent, replayable, parallel.
- **Graceful degradation:** no downscaler ⇒ publish the coarse physical field
  flagged `degraded`; a coarse map beats no map.
- **Physics governance:** every product ships `mass_conservation_residual` and
  `uphill_flow_violation` scores — accuracy gains never hide physics violations.
- **Alerts are decision support.** Every alert payload carries the NWS-supplement
  disclaimer; thresholds live in config and change only through stakeholder review.
- **Labels are append-only and tiered** (gold analyst masks → silver GFM masks →
  bronze 311/NFIP/LSR evidence), so any training run's inputs are reconstructible.

## Deployment

```bash
docker compose -f docker/docker-compose.yml up --build
```

brings up API (:8000), a cycle worker, PostGIS, and Redis. Kubernetes manifests
for the operational phase follow the same two-image split (api / worker); the
worker scales horizontally per ensemble member.

## Scaling path

| Concern | Pilot | Operational |
|---|---|---|
| Hot store | in-memory | Redis + PostGIS |
| Catalog | JSONL | pgstac + stac-fastapi |
| Scheduler | CLI / cron | Prefect or Airflow |
| Solver | reference numpy | LISFLOOD-FP / SERGHEI via `scheme: external` |
| Serving | uvicorn | k8s HPA behind a tile cache |

## Data sources and attribution

SatPI runs entirely on open data: Copernicus Sentinel-1/2, NASA HLS, NOAA MRMS,
HRRR and the National Water Model, USGS stream gauges, and local flood-report
feeds (Pittsburgh 311 via WPRDC, FEMA OpenFEMA NFIP claims, NWS Local Storm
Reports). **No third-party data are stored in this repository**; they are
downloaded at run time under each provider's terms.

[`DATA_SOURCES.md`](DATA_SOURCES.md) lists every source with its license, the
attribution it requires, a citation, and links to the terms. Any public map or
publication made with SatPI must carry the attribution block in Section 3 of
that file. Mention of a provider does not imply its endorsement.

## Citing

See [`CITATION.cff`](CITATION.cff) (GitHub shows a "Cite this repository"
button), and cite the datasets your work used as listed in `DATA_SOURCES.md`.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). New data sources must be credited in
`DATA_SOURCES.md`; a test enforces it.

## License

Code: Apache License 2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
The code license does not apply to third-party data or models, which remain
under their providers' terms (see `DATA_SOURCES.md`).

SatPI products are decision support and research outputs. They supplement, and
never replace, official National Weather Service warnings or FEMA regulatory
flood maps.
