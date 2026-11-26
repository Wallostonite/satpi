# Adapting SatPI to a New Study Area

The platform's portability contract: **all region-specific knowledge lives in one
YAML file** validated by `satpi.config.StudyArea`. No code changes are required
for a new region unless it needs a data source *kind* that doesn't exist yet
(see step 3).

## Checklist

### 1. Create the config

```bash
cp configs/study_areas/_template.yaml configs/study_areas/my_region.yaml
export SATPI_STUDY_AREA_CONFIG=configs/study_areas/my_region.yaml
satpi validate-config      # fails fast on any schema violation
```

Fill in, in this order of importance:

| Field | Guidance |
|---|---|
| `bbox`, `crs_epsg` | AOI in lon/lat; pick the UTM zone (or national grid) covering it |
| `terrain.dem_path` | Best available DEM as a COG. LiDAR if you have it; Copernicus GLO-30 works globally as a floor |
| `gauges` | Every reliable stream gauge in the basin. These anchor assimilation and validation — more is better |
| `forcing` | See step 2: this is the main regional swap |
| `satellites` | Sentinel-1/2 are global; usually keep the defaults |
| `weak_labels` | Local flood-report feeds: 311-equivalents, insurance claims, storm reports |
| `alert_rules` | Leave empty until stakeholders define zones and thresholds |

### 2. Swap forcing sources (the only real regional work)

MRMS, HRRR, and NWM are CONUS-only. Outside the US:

- Radar QPE → your national met service's product via `generic_grib` /
  `generic_zarr` (e.g., EUMETSAT/OPERA composites in Europe, JMA radar in Japan).
- NWP → the regional model (ICON-D2, AROME, ACCESS…) or GFS globally via the
  existing `gfs` kind.
- Channel routing → national hydrologic model if one exists (e.g., EFAS in
  Europe); otherwise drive the solver from gauged inflows only.

If a source needs custom parsing, implement one class:

```python
# src/satpi/ingestion/my_source.py
from satpi.ingestion.base import Asset, BaseIngestor, register

@register("my_radar")
class MyRadar(BaseIngestor):
    def fetch(self, start, end, **kw):
        ...  # yield Asset(...)
```

Registering the `kind` makes it available to every study area config; nothing
else changes.

### 3. Terrain bootstrap

With the `geo` extra installed:

- Reproject/mosaic the DEM to `crs_epsg` as a COG at `dem_resolution_m`.
- Hydro-condition if possible (breach culverts/bridges); set
  `hydro_conditioned: true` so the pipeline skips its fallback pit-filling.
- The pipeline derives the coarse solver grid, slope, and HAND automatically
  (`satpi.preprocessing.terrain`).

### 4. Labels and models

- Seed the label store with any historical event masks (Tier 1) — e.g.,
  Copernicus EMS activations, UNOSAT maps.
- The perception model fine-tuned on Sen1Floods11 transfers zero-shot; expect a
  regional fine-tune (Tier 1+2 labels from your first monitored events) to add
  several points of IoU. The downscaler must be retrained per region — it
  learns terrain-specific redistribution.
- Until a downscaler exists the platform runs in **degraded mode** (coarse
  products, flagged) — it is operational from day one.

### 5. Causal graph extensions

`DEFAULT_EDGES` in `satpi/causal/scm.py` covers any rain-driven regime. Add
region-specific nodes with mechanisms, never by editing the default graph:

```python
scm.add_mechanism("snowmelt", melt_fn, parents=["temperature"])
scm.graph.add_edge("snowmelt", "tributary_discharge")
```

Coastal regions add a `storm_surge → mainstem_stage` branch; snow regimes add
snowpack; SW PA adds mine drainage. Validate uncertain edges with the
`causal` extra (PCMCI) before admitting them.

### 6. Validation gates before going live

1. `satpi validate-config` and `satpi run-cycle` pass.
2. Hindcast one historical event; check gauge NSE/KGE and extent IoU against
   any reference map.
3. Physics-consistency scores within tolerance (mass residual < 0.05,
   uphill violations < 0.02) on hindcast products.
4. Stakeholder review of alert zones/thresholds — alerts stay disabled until
   this sign-off exists.

## What scales automatically

Solver, assimilation, ensemble machinery, label store, API, dashboard, alert
engine, and CI are all region-independent. The demo cycle (`satpi run-cycle`)
runs on synthetic terrain precisely so a new deployment can verify the entire
software path before a single byte of regional data is plumbed.
