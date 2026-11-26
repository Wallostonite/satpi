# SatPI-FM-CDT: Conceptual Framework, System Architecture, and Full-Stack Requirements

**A Satellite-Informed, Physics-Consistent, Causal Digital Twin for Flood Intelligence in Southwestern Pennsylvania**

Version 1.0 — Pilot Design Document

---

## 1. Conceptual Framework

### 1.1 Problem Statement

Southwestern Pennsylvania faces a compound flood regime that defeats single-method modeling. Steep Appalachian tributaries produce flash floods with response times measured in hours; the Allegheny–Monongahela–Ohio confluence produces slower riverine flooding governed by basin-scale routing; and Pittsburgh's urban core produces pluvial flooding driven by impervious surfaces, aging combined sewers, and legacy mining alteration of subsurface flow. Existing operational tools each cover one piece: NWS river forecasts handle main-stem riverine flooding well but not urban or flash events; HEC-RAS studies are accurate but static and scenario-bound; and pure machine-learning flood mappers are fast but physically unconstrained and observation-limited.

### 1.2 Core Thesis

The framework rests on a separation of concerns among three subsystems, each doing what it is best suited for, coupled through well-defined interfaces:

**Perception (What is flooded?)** A fine-tuned geospatial foundation model (GFM) converts multi-sensor satellite imagery into probabilistic flood extent and depth estimates. Its role is *state estimation*, not prediction. Satellite revisit intervals (6–12 days for Sentinel-1/2) are too sparse to drive a nowcast in a flash-flood regime, so the perception subsystem instead provides intermittent, high-resolution corrections to the system's estimate of surface water state, and supplies the labeled training data that everything else learns from.

**Dynamics (What will be flooded, and when?)** A hybrid physics–ML engine predicts flood evolution at lead times from 0 to 7 days. High-cadence terrestrial forcing — MRMS radar precipitation, HRRR numerical weather forecasts, National Water Model channel routing, and USGS gauge observations — drives a coarse-resolution physical solver, and a learned downscaler refines its output to 10 m resolution while enforcing physical consistency (mass conservation, terrain-consistent flow, monotone depth–extent relationships). This inverts the usual PINN framing: rather than asking a neural network to solve the shallow water equations, the physics solver produces a coarse prior and the network corrects and sharpens it — a formulation that is computationally tractable at basin scale and directly comparable to the HEC-RAS baselines used by USACE.

**Causation (What would happen if...?)** A structural causal model (SCM) over the region's hydrologic drivers supports intervention and counterfactual queries for planning: green-infrastructure scenarios, culvert and levee modifications, and climate-perturbed forcing under pseudo-global-warming assumptions. The causal graph is *encoded from domain knowledge*, not discovered from data; observational causal discovery is used only to test uncertain edges (e.g., mine-drainage influence on local stage) where hydrologic theory is ambiguous.

### 1.3 Design Principles

1. **Physics as prior, ML as corrector.** The physical solver guarantees plausibility; the learned component supplies resolution and speed.
2. **Satellites as truth, radar as pulse.** Satellite observations anchor the system to reality at low cadence; radar/NWP forcing provides the minute-scale heartbeat.
3. **Open data, open weights, open tooling.** Every data source and model in the pilot stack is free for research use, keeping the data budget at zero and the compute budget modest.
4. **Probabilistic everywhere.** Every product carries calibrated uncertainty — ensemble forecasts, per-pixel flood probabilities, and confidence intervals on scenario outcomes.
5. **Operational from day one.** Architecture choices (containerized services, cloud-native geospatial formats, streaming ingestion) are made so the pilot can graduate to an operational deployment without re-architecture.
6. **Stakeholder-legible outputs.** Products map to decisions: probabilistic inundation maps for emergency managers, event skill scores for forecasters, scenario comparisons for planners.

### 1.4 Scope

- **Domain:** Allegheny and Monongahela basins converging on Pittsburgh; ~10,000–20,000 km²; 10 m output resolution.
- **Lead times:** Nowcast (0–6 h), short-range forecast (6–72 h), medium-range outlook (3–7 d), and offline scenario analysis.
- **Flood types:** Riverine, flash/tributary, and urban pluvial (treated as a distinct class with its own labels and skill metrics).

---

## 2. System Architecture

The system is organized as five layers plus two cross-cutting planes. Data flows upward from acquisition to products; the MLOps and governance planes span all layers.

```
┌─────────────────────────────────────────────────────────────────┐
│  L4  SERVING & PRODUCTS                                         │
│      Dashboard · Alerting · Scenario Studio · Public API        │
├─────────────────────────────────────────────────────────────────┤
│  L3  CAUSAL SCENARIO ENGINE                                     │
│      Structural causal model · Intervention engine ·            │
│      Pseudo-global-warming forcing · Counterfactual maps        │
├─────────────────────────────────────────────────────────────────┤
│  L2  MODELING CORE                                              │
│      Perception GFM (SAR/optical → extent/depth)                │
│      Coarse physics solver (diffusive wave / LISFLOOD-class)    │
│      Physics-consistent ML downscaler (coarse → 10 m)           │
│      Data assimilation (gauge + satellite state correction)     │
├─────────────────────────────────────────────────────────────────┤
│  L1  DATA PLATFORM                                              │
│      Lakehouse (COG/Zarr/GeoParquet) · STAC catalog ·           │
│      Feature store · Label store · Static layers (DEM, NLCD)    │
├─────────────────────────────────────────────────────────────────┤
│  L0  ACQUISITION & INGESTION                                    │
│      Satellite (S1/S2/HLS) · Radar (MRMS) · NWP (HRRR) ·        │
│      Hydrology (NWM, USGS) · Weak labels (311, NFIP, LSRs)      │
├─────────────────────────────────────────────────────────────────┤
│  X1  MLOps PLANE: experiment tracking · registry · CI/CD ·      │
│      drift monitoring · retraining triggers                     │
│  X2  GOVERNANCE PLANE: validation · versioned datasets ·        │
│      audit trails · stakeholder review                          │
└─────────────────────────────────────────────────────────────────┘
```

### 2.1 Layer 0 — Acquisition & Ingestion

Ingestion is split into three cadence classes, each with its own pipeline pattern.

**Streaming (minutes).** MRMS quantitative precipitation estimates (1 km, 2 min), USGS instantaneous gauge values (15 min via the USGS Water Services API), and NWS watches/warnings arrive continuously. A lightweight scheduler polls these endpoints, normalizes units and geodesy, and writes to the platform's hot store. GOES imagery is ingested on the same path when a flood watch is active.

**Batch-on-arrival (hours to days).** New Sentinel-1 GRD, Sentinel-2 L2A, and Harmonized Landsat–Sentinel (HLS) scenes intersecting the study area trigger event-driven processing: SAR terrain correction and incidence-angle/layover masking against the PASDA LiDAR DEM, optical cloud masking, index computation (NDWI, MNDWI), and tiling into analysis-ready chips. HRRR forecast cycles (hourly, 18–48 h horizons) and NWM channel outputs (hourly) are pulled from their AWS open-data buckets on publication.

**Static and slowly varying (monthly to annual).** LiDAR-derived DEM and hydro-conditioned derivatives (slope, curvature, topographic wetness index, height above nearest drainage), NLCD land cover and imperviousness, National Flood Hazard Layer geometries, mining-feature layers from PA DEP, and culvert/levee inventories are versioned as static layers and refreshed on their source cadence.

**Weak-label ingestion.** Pittsburgh/Allegheny County 311 flood reports (via the Western Pennsylvania Regional Data Center), OpenFEMA NFIP claims, NWS Local Storm Reports, and USGS high-water marks are geocoded, deduplicated, and time-bucketed into the label store as point/polygon evidence with source-specific reliability weights.

### 2.2 Layer 1 — Data Platform

The platform is a cloud-native geospatial lakehouse:

- **Raster store:** Cloud-Optimized GeoTIFF for single-scene products; Zarr for dense spatiotemporal cubes (forcing stacks, forecast ensembles).
- **Vector/tabular store:** GeoParquet for labels, gauge series, infrastructure inventories, and event catalogs.
- **Catalog:** A STAC (SpatioTemporal Asset Catalog) API indexes every asset with provenance, processing version, and spatial/temporal extent, so any experiment can reconstruct its exact inputs.
- **Feature store:** Precomputed model-ready chips (multi-channel tensors of SAR + optical + forcing + static layers) keyed by tile, timestamp, and feature-set version, eliminating repeated preprocessing during training.
- **Label store:** Versioned flood masks from three tiers — Tier 1 (hand-validated satellite masks for major events such as Ida 2021), Tier 2 (GFM-generated masks spot-checked by analysts), Tier 3 (weak labels from 311/NFIP/LSR points) — with per-tier loss weighting downstream.
- **Hot store:** A PostGIS instance holds the last 72 hours of streaming observations and the current forecast for low-latency serving.

### 2.3 Layer 2 — Modeling Core

**2.3.1 Perception subsystem.** A fine-tuned GFM backbone (Clay v1.5 and Prithvi-EO-2.0 both evaluated; selection is empirical per sensor, with Clay favored for Sentinel-2 and compute efficiency and Prithvi for Sentinel-1) with a segmentation head produces per-pixel flood probability from each new satellite scene. Inputs per chip: SAR VV/VH backscatter, incidence angle, layover/shadow mask, optical bands and water indices when available, DEM derivatives, and imperviousness. Urban pixels form a separate class with dedicated weighting to counter systematic SAR under-observation (double-bounce, occlusion). Depth is estimated by intersecting predicted extent with the LiDAR DEM via a HAND-based (height above nearest drainage) floodwater-surface fit. Outputs are written to the platform as probabilistic extent/depth rasters and become both (a) assimilation increments for the dynamics subsystem and (b) Tier-2 labels after QC.

**2.3.2 Dynamics subsystem.** The forecast chain runs in three stages:

1. **Forcing assembly.** For nowcasts, MRMS QPE blended with MRMS/HRRR short-range precipitation forecasts; for 1–7 day horizons, HRRR and GFS/NBM ensemble members. NWM channel discharge provides boundary inflows; USGS gauges correct NWM bias via a lightweight error-correction model.
2. **Coarse physical solve.** A diffusive-wave / LISFLOOD-class 2D solver runs on a coarsened (~90 m) hydro-conditioned DEM over the domain, per ensemble member, producing physically consistent coarse inundation and depth fields. This stage is the physics prior.
3. **Physics-consistent downscaling.** A learned super-resolution network maps the coarse solution plus 10 m static layers (LiDAR DEM, imperviousness, drainage features) to 10 m extent/depth. Training minimizes a composite loss: supervised terms against Tier 1–3 labels, plus physics-consistency penalties — subcatchment mass conservation, no uphill flow against the DEM, monotone depth–extent relations, and agreement with gauge stages at cross-sections. Physics terms are applied at training time only, keeping inference fast (seconds per tile).

**2.3.3 Data assimilation.** An ensemble state-correction step nudges the dynamic state toward observations whenever they arrive: continuously from gauges, intermittently from satellite perception outputs. Between satellite passes the system runs on forcing and gauges alone; each pass re-anchors the spatial state.

### 2.4 Layer 3 — Causal Scenario Engine

The SCM encodes the region's driver graph explicitly: precipitation → soil moisture → runoff → tributary discharge → main-stem stage → inundation, with side branches for imperviousness → urban runoff, drainage/culvert capacity → local conveyance, and mine-feature → subsurface routing where evidence supports it. Node mechanisms are implemented by the Layer 2 components themselves (the solver and downscaler serve as the structural equations for the hydraulic nodes), which keeps counterfactual maps consistent with forecast maps.

Supported query classes:

- **Interventions on land surface:** e.g., reduce imperviousness by X% in specified sewersheds (green-infrastructure scenarios) — implemented as edits to the imperviousness and roughness layers, re-run through the chain.
- **Interventions on infrastructure:** culvert resizing, levee modification at named confluences — implemented as conveyance-parameter edits in the solver mesh.
- **Climate counterfactuals:** +1.5 °C / +2 °C re-runs of historical events under pseudo-global-warming deltas applied to forcing (temperature-scaled precipitation intensity), clearly labeled as scenario products, not forecasts.
- **Edge testing:** constraint-based causal discovery (PCMCI-class methods) applied to the historical gauge–precipitation–satellite record *only* to adjudicate uncertain edges before they are admitted to the SCM.

### 2.5 Layer 4 — Serving & Products

- **Web dashboard:** map-centric UI showing current nowcast, probabilistic forecast layers by lead time, gauge hydrographs with forecast fans, and recent satellite confirmations. Built on vector/raster tiles served from the platform.
- **Scenario Studio:** planner-facing interface to configure and compare interventions (baseline vs. scenario difference maps with uncertainty).
- **Alerting service:** threshold- and probability-based triggers (e.g., >40% probability of inundation over a critical corridor such as Route 51) delivered via webhook/email; explicitly framed as decision support supplementing, never replacing, NWS warnings.
- **API:** REST + OGC-standard endpoints (STAC for discovery, tiles for maps, JSON for time series) so partners (Allegheny County Emergency Services, USACE Pittsburgh District) can integrate outputs into their own systems.
- **Edge package:** a distilled perception model exported to ONNX for post-event rapid mapping on local hardware or drone-collected imagery when cloud connectivity is degraded.

### 2.6 Cross-Cutting Planes

**MLOps plane.** Every training run logs code version, feature-set version, label-tier composition, and hyperparameters to an experiment tracker; promoted models enter a registry with evaluation cards. Retraining triggers fire on (a) new Tier-1 event labels, (b) drift in perception-model confidence against gauge-corroborated ground truth, or (c) upstream data-format changes. CI runs the full pipeline on a fixed miniature domain (one HUC-10 subbasin) so regressions surface before deployment.

**Governance plane.** All published products carry version stamps and provenance links back through STAC. A validation ledger records skill scores per event. Scenario products are watermarked as non-forecast analyses. Stakeholder review gates (county EMS, USACE) precede any alerting-threshold change.

### 2.7 Data Flow Summary

- **Nowcast path (continuous):** MRMS/gauges → forcing assembly → coarse solver (latest cycle) → downscaler → hot store → dashboard/alerts. Target end-to-end latency: under 15 minutes from radar observation to updated 10 m map.
- **Forecast path (hourly cycles):** HRRR/NWM ensemble → solver ensemble → downscaler → probabilistic products by lead time.
- **Perception path (event-driven):** new S1/S2/HLS scene → preprocessing → GFM inference → extent/depth raster → assimilation increment + Tier-2 label candidate.
- **Training path (offline):** feature store + label store → fine-tuning/downscaler training → evaluation on held-out subbasins and held-out events → registry promotion.
- **Scenario path (on demand):** SCM intervention spec → parameter/forcing edits → chain re-run → difference maps in Scenario Studio.

---

## 3. Full-Stack Requirements

### 3.1 Data Sources (all free for research use)

| Source | Role | Cadence / Resolution | Access |
|---|---|---|---|
| Sentinel-1 GRD | SAR flood perception | 6–12 d / 10 m | Copernicus Data Space, AWS |
| Sentinel-2 L2A / HLS | Optical perception | 5 d (clear-sky) / 10–30 m | Copernicus, NASA LP DAAC, AWS |
| MRMS QPE | Precipitation nowcast forcing | 2 min / 1 km | NOAA on AWS |
| HRRR | Short-range NWP forcing | Hourly cycles / 3 km | NOAA on AWS |
| GFS / NBM | Medium-range ensemble forcing | 6-hourly / 13–25 km | NOAA on AWS |
| National Water Model | Channel routing, boundary inflows | Hourly / reach-scale | NOAA on AWS |
| USGS NWIS gauges | Stage/discharge truth & assimilation | 15 min / point | USGS Water Services API |
| PASDA LiDAR / QL2 DEM | Terrain, HAND, hydro-conditioning | Static / ≤1 m | PASDA |
| NLCD | Land cover, imperviousness | Annual / 30 m | MRLC |
| National Flood Hazard Layer | Regulatory baseline geometry | Static / vector | FEMA |
| Sen1Floods11 | Fine-tuning benchmark labels | Static | Cloud to Street / GitHub |
| OpenFEMA NFIP claims | Weak labels (urban/pluvial) | Event-driven / point | OpenFEMA API |
| Pittsburgh 311 | Weak labels (urban) | Continuous / point | WPRDC |
| NWS Local Storm Reports | Weak labels, event catalog | Event-driven / point | IEM/NWS |
| PA DEP mining features | Legacy-mining channel | Static / vector | PA DEP, PASDA |

### 3.2 Modeling & ML Stack

| Component | Technology | Notes |
|---|---|---|
| GFM backbones | Clay v1.5 (26M), Prithvi-EO-2.0 (600M) | Open weights (Hugging Face); empirical selection per sensor |
| DL framework | PyTorch + Lightning | Training loops, mixed precision |
| Geospatial DL tooling | TorchGeo, TerraTorch | Samplers, GFM fine-tuning scaffolding |
| Coarse solver | LISFLOOD-FP (academic) or SERGHEI / ANUGA (open) | GPU-capable diffusive wave |
| Data assimilation | Ensemble nudging (custom, NumPy/JAX) | Gauge + satellite increments |
| Causal tooling | DoWhy / Tigramite (PCMCI) | SCM queries; edge testing only |
| Distillation/export | ONNX Runtime | Edge deployment |
| Experiment tracking | MLflow or Weights & Biases | Registry + evaluation cards |

### 3.3 Geospatial Data Engineering Stack

| Component | Technology |
|---|---|
| Raster processing | GDAL, rasterio, rioxarray, xarray + Dask |
| SAR preprocessing | ESA SNAP (graph processing) or sarsen |
| Formats | COG, Zarr, GeoParquet |
| Catalog | STAC (pgstac + stac-fastapi) |
| Vector/DB | PostGIS 16 |
| Tiling | TiTiler (raster), tipg/martin (vector) |
| Bulk archive access | Google Earth Engine (research tier) for historical pulls; direct AWS for operational |

### 3.4 Backend & Serving Stack

| Component | Technology |
|---|---|
| API framework | FastAPI (REST + OGC endpoints) |
| Orchestration | Prefect or Airflow (cycle scheduling, event triggers) |
| Streaming/queue | Redis streams (pilot) → Kafka (operational) |
| Containers | Docker; Kubernetes for operational phase (k3s acceptable for pilot) |
| Alerting | Webhook/email service with probability-threshold rules engine |

### 3.5 Frontend Stack

| Component | Technology |
|---|---|
| Framework | React + TypeScript |
| Mapping | MapLibre GL JS with deck.gl overlays |
| Charts | Recharts/Plotly (hydrograph fans, skill dashboards) |
| Scenario Studio | Same stack; parameter forms driving async scenario jobs |

### 3.6 Infrastructure & Compute

| Phase | Requirement |
|---|---|
| Training (pilot) | 1× A100 40GB (or 2× RTX 4090) for Clay-scale fine-tuning and downscaler training; NSF ACCESS or university cluster covers at $0 |
| Prithvi evaluation | 2–4× A100 for the 600M-parameter comparison runs |
| Inference (operational cycle) | 1 GPU node (T4/L4-class) sustains 15-min nowcast cycles over the domain |
| Solver | CPU cluster node or 1 GPU (SERGHEI) per ensemble member; 10–20 members |
| Storage | ~5–15 TB pilot archive (5 yr forcing + imagery chips + products) |
| Cloud | AWS or GCP; exploit open-data buckets in-region to avoid egress fees |

### 3.7 Non-Functional Requirements

- **Latency:** ≤15 min radar-to-map for nowcasts; hourly forecast refresh.
- **Resolution:** 10 m products; ~90 m internal solver grid.
- **Availability:** best-effort in pilot; 99% cycle-completion target in operational phase with graceful degradation (if the downscaler fails, publish coarse solver output; if forcing fails, persist last state with staleness flags).
- **Reproducibility:** any published map reconstructible from STAC provenance.
- **Security & access:** public read-only products; authenticated write and scenario endpoints; no PII (311/NFIP points aggregated to block level before publication).
- **Interoperability:** OGC-compliant services so USACE/county GIS can consume layers directly.

---

## 4. Validation Framework

- **Spatial block cross-validation:** hold out entire HUC-10 subbasins, never random pixels, to prevent spatial leakage.
- **Event-based holdout:** at least one major event (e.g., Ida 2021) reserved end-to-end for final evaluation.
- **Metrics by product:** mIoU/F1 and calibration curves for extent; NSE/KGE for stage/discharge; RMSE against high-water marks for depth; POD/FAR/CSI against NWS warnings and observed impacts for alerting skill.
- **Baselines:** U-Net-on-Sentinel control (matching prior PA studies), NWM/HAND static inundation, and available HEC-RAS results at USACE study reaches.
- **Physical consistency score:** fraction of predicted flood volume violating mass/terrain constraints — reported alongside accuracy so ML gains never come at the cost of physical plausibility.

---

## 5. Phased Delivery Plan

| Phase | Duration | Deliverables |
|---|---|---|
| P0 — Data foundation | Months 1–2 | Ingestion pipelines, STAC catalog, Ida-era label set (Tiers 1–3), baseline U-Net control |
| P1 — Perception | Months 2–4 | Clay vs. Prithvi fine-tune benchmark on SW PA; selected GFM in production inference; Tier-2 labeling loop |
| P2 — Dynamics | Months 4–8 | Coarse solver operational on domain; downscaler trained with physics losses; assimilation loop; first end-to-end nowcast |
| P3 — Causal engine | Months 7–10 | SCM implementation; green-infrastructure and culvert scenario classes; PGW climate re-runs of Ida |
| P4 — Products & partners | Months 9–12 | Dashboard, alerting, API; stakeholder pilots with Allegheny County EMS / USACE Pittsburgh; validation report and publication draft |

Phases overlap deliberately: perception outputs feed dynamics training, and the solver built in P2 becomes the structural backbone of P3.

---

## 6. Risk Register (Top Items)

| Risk | Mitigation |
|---|---|
| Sparse satellite observations of flash events | Radar-driven dynamics carries prediction; satellites anchor state — design already assumes this |
| Urban SAR under-detection | Dedicated urban class, weak-label fusion (311/NFIP), optical/HLS augmentation |
| Solver runtime exceeds cycle budget | Coarsen grid adaptively; GPU solver (SERGHEI); reduce ensemble size with post-hoc calibration |
| GEE licensing at operational stage | GEE confined to historical archive pulls; operational path uses AWS open data directly |
| Weak-label noise | Tiered loss weighting; reliability learned per source |
| Stakeholder trust in ML products | Physics-consistency scoring, HEC-RAS benchmarking, NWS-supplementary framing of alerts |
