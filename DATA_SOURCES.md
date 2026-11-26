# Data Sources, Licenses and Credits

**Project:** SatPI-FM-CDT — satellite-informed, physics-consistent, causal flood intelligence
**Reference deployment:** Southwestern Pennsylvania (Allegheny / Monongahela / Ohio confluence)
**Terms last reviewed:** 25 November 2026

This document credits every external dataset, model and service that SatPI
reads or is designed to read, states the license or terms under which each is
used, and gives the attribution each provider asks for. Terms change; check the
linked source pages before any publication or commercial deployment.

---

## 1. Scope: what this repository does and does not distribute

- **Code** in this repository is licensed under the Apache License 2.0 (see
  [`LICENSE`](LICENSE)).
- **This repository contains no third-party data.** Data are fetched at run time
  from each provider's own service and written to a local `data/` directory,
  which is excluded from version control (see [`.gitignore`](.gitignore)).
- **The Apache-2.0 license covers the code only.** It does not relicense any
  dataset or model listed here. Every dataset remains under its provider's
  terms, and anyone running SatPI is responsible for complying with them.
- **Derived products** (flood extent, depth, exceedance probabilities, alerts)
  inherit attribution duties from their inputs. Section 3 gives a single
  attribution block that satisfies all sources in the reference deployment.

---

## 2. Summary

Ingestion *kind* is the value used in a study-area config
(`configs/study_areas/*.yaml`) to enable that source.

### 2.1 Data ingested by the code

| Dataset | Provider | Role in SatPI | Ingestion kind | License / terms | Commercial use | Attribution |
|---|---|---|---|---|---|---|
| Sentinel-1 GRD (SAR) | ESA / European Union, Copernicus | Flood perception (all-weather) | `sentinel1` via `stac_satellite` | Copernicus Sentinel data legal notice — free, full and open | Not restricted by the notice | Required |
| Sentinel-2 L2A (optical) | ESA / European Union, Copernicus | Flood perception, water indices | `sentinel2` via `stac_satellite` | Copernicus Sentinel data legal notice | Not restricted by the notice | Required |
| Harmonized Landsat Sentinel-2 (HLS) v2.0 | NASA (LP DAAC) | 30 m optical perception | `hls` via `stac_satellite` | NASA Earth science data policy (CC0 for NASA-led data) plus Copernicus terms for its Sentinel-2 component | Yes | Requested; Copernicus notice applies |
| MRMS QPE | NOAA / NSSL, via NOAA Open Data Dissemination (NODD) | Radar precipitation forcing (nowcast) | `mrms_qpe` | NOAA NODD: open, use as desired | Yes | Requested; no endorsement |
| HRRR | NOAA, via NODD | Short-range weather forcing | `hrrr` | NOAA NODD | Yes | Requested; no endorsement |
| National Water Model short-range | NOAA Office of Water Prediction, via NODD | Channel inflows, boundary conditions | `nwm` | NOAA NODD | Yes | Requested; no endorsement |
| NWIS instantaneous values | U.S. Geological Survey | Gauge stage and discharge: assimilation and validation | `usgs_iv` | U.S. public domain | Yes | Requested |
| Pittsburgh 311 Data | City of Pittsburgh, hosted by WPRDC | Tier-3 weak flood labels | `socrata_311` | Creative Commons Attribution (CC BY) | Yes, with attribution | **Required** |
| FIMA NFIP Redacted Claims (v2) | FEMA, via OpenFEMA API | Tier-3 weak flood labels | `openfema_nfip` | OpenFEMA terms; U.S. government work | Yes | **Required disclaimer** |
| NWS Local Storm Reports | NOAA National Weather Service, served by the Iowa Environmental Mesonet | Tier-3 weak labels, event catalog | `nws_lsr` | Public domain (NWS products; IEM materials) | Yes | Requested |

### 2.2 Static layers named in configs or the architecture

| Dataset | Provider | Role | License / terms | Attribution |
|---|---|---|---|---|
| Lidar-derived DEM (USGS QL2, Western PA 2019–2020; PAMAP 2006–2008) | USGS 3DEP partners; PA DCNR PAMAP Program; distributed via PASDA and NOAA OCM | Terrain, HAND, hydro-conditioning | No access constraints stated; U.S. government work for USGS products | Credit originators (Section 4.11) |
| Annual NLCD Collection 1 | U.S. Geological Survey | Land cover, imperviousness | U.S. government work | Requested citation |
| National Flood Hazard Layer | FEMA | Regulatory baseline, validation context | U.S. government work | Credit FEMA |
| Abandoned Mine Land Inventory | PA DEP (subset of OSMRE AML inventory), via PASDA | Legacy-mining static layer | **No license stated** by the distributor | Credit PA DEP / OSMRE |
| USGS high-water marks (STN) | U.S. Geological Survey | Depth validation | U.S. public domain | Requested |
| Culvert inventory | Local agency (not yet sourced) | Conveyance edits in scenarios | **Set when sourced** | Per source |

### 2.3 Models, training data and services

| Item | Provider | Role | License / terms |
|---|---|---|---|
| Clay Foundation Model v1.5 (weights) | Clay Foundation | Perception backbone | Apache-2.0 |
| Prithvi-EO-2.0 (weights) | IBM and NASA | Perception backbone (Sentinel-1 comparison) | Apache-2.0 |
| Sen1Floods11 | Cloud to Street | Perception fine-tuning benchmark | **No license stated** by the publisher; citation requested |
| Earth Search STAC API | Element 84 | Scene discovery | Free to use, best effort, no service guarantee; data remain under their own licenses |
| NASA CMR STAC (LPCLOUD) | NASA | HLS discovery | NASA data policy; downloads need a free Earthdata Login |
| CARTO basemaps (Dark Matter) | CARTO, using OpenStreetMap data | Dashboard background map | CARTO basemap terms; OpenStreetMap data under ODbL |
| MapLibre GL JS | MapLibre contributors | Dashboard map renderer | BSD-3-Clause |
| Google Earth Engine (optional) | Google | Historical archive pulls (architecture only; not used by the code) | Free for noncommercial and research use only |

---

## 3. Required attribution for maps, dashboards and publications

Place this block, or an equivalent, on any public product built with the
reference deployment. The live dashboard already shows a short form of it.

> Contains modified Copernicus Sentinel data [YEAR].
> Precipitation, weather and streamflow forecasts: NOAA Multi-Radar/Multi-Sensor
> System, High-Resolution Rapid Refresh and National Water Model (NOAA Open Data
> Dissemination). Stream gauge data courtesy of the U.S. Geological Survey.
> HLS data: NASA LP DAAC. Flood reports: City of Pittsburgh 311 (WPRDC, CC BY);
> NWS Local Storm Reports via the Iowa Environmental Mesonet.
> This product uses the Federal Emergency Management Agency's OpenFEMA API, but
> is not endorsed by FEMA. The Federal Government or FEMA cannot vouch for the
> data or analyses derived from these data.
> Not endorsed by NOAA, NASA or USGS. Products are derived from, and are not,
> original NOAA data.
> Basemap © OpenStreetMap contributors © CARTO.

Replace `[YEAR]` with the year(s) of the Sentinel acquisitions used.

---

## 4. Source details

Each entry gives the provider, what SatPI uses, where it is accessed, the
license, the citation to use, and caveats.

### 4.1 Copernicus Sentinel-1 and Sentinel-2

- **Provider:** European Union, Copernicus programme; satellites operated by ESA.
- **Used for:** Sentinel-1 GRD backscatter (VV/VH) and Sentinel-2 L2A surface
  reflectance as perception inputs and labels.
- **Access:** discovered through Element 84 Earth Search
  (`https://earth-search.aws.element84.com/v1`, collections `sentinel-1-grd`,
  `sentinel-2-l2a`); assets on the AWS Registry of Open Data.
- **License:** Copernicus Sentinel data legal notice. Access is free, full and
  open; reproduction, distribution, adaptation and combination with other data
  are permitted. Data come without warranty, and users waive damage claims
  against the EU and data providers.
- **Attribution (mandatory when distributing or communicating to the public):**
  `Copernicus Sentinel data [Year]` for unmodified data;
  `Contains modified Copernicus Sentinel data [Year]` for modified data. SatPI's
  products are modified data, so use the second form.
- **Links:** [Copernicus Sentinel data licence](https://ads.atmosphere.copernicus.eu/licences/ec-sentinel) ·
  [Sentinel-1 on AWS](https://registry.opendata.aws/sentinel-1) ·
  [Sentinel-2 COGs on AWS](https://registry.opendata.aws/sentinel-2-l2a-cogs/)

### 4.2 Harmonized Landsat Sentinel-2 (HLS) v2.0

- **Provider:** NASA; archived and distributed by the Land Processes DAAC.
- **Used for:** 30 m harmonized optical observations (`HLSS30.v2.0`).
- **Access:** NASA CMR STAC, `https://cmr.earthdata.nasa.gov/stac/LPCLOUD`.
  Downloads require a free NASA Earthdata Login.
- **License:** NASA Earth science data policy. Data from NASA-led missions are
  CC0 unless marked otherwise; NASA must not be used to imply endorsement.
  HLS S30 is derived from Sentinel-2, so the Copernicus notice in 4.1 also applies.
- **Citation:** Masek, J., et al. HLS Sentinel-2 MSI Surface Reflectance Daily
  Global 30m v2.0. NASA EOSDIS Land Processes DAAC.
  doi:10.5067/HLS/HLSS30.002. Acknowledge NASA as the source.
- **Links:** [NASA data use policy](https://www.earthdata.nasa.gov/learn/use-data/data-use-policy) ·
  [HLS project](https://www.earthdata.nasa.gov/data/projects/hls)

### 4.3 NOAA Multi-Radar/Multi-Sensor System (MRMS)

- **Provider:** NOAA National Severe Storms Laboratory; disseminated through the
  NOAA Open Data Dissemination (NODD) program.
- **Used for:** `MultiSensor_QPE_01H_Pass2` hourly quantitative precipitation
  estimates driving the nowcast solver.
- **Access:** `https://noaa-mrms-pds.s3.amazonaws.com`.
- **License:** NODD data are open to the public and may be used as desired.
  NOAA requests attribution for unaltered data, does not allow stating or
  implying NOAA endorsement or affiliation, and does not allow presenting
  modified data as original, unaltered NOAA data.
- **Citation:** NOAA Multi-Radar/Multi-Sensor System (MRMS) was accessed on
  [DATE] from https://registry.opendata.aws/noaa-mrms-pds.
- **Links:** [Registry entry](https://registry.opendata.aws/noaa-mrms-pds/) ·
  [MRMS documentation](https://www.nssl.noaa.gov/projects/mrms/)

### 4.4 NOAA High-Resolution Rapid Refresh (HRRR)

- **Provider:** NOAA; disseminated through NODD.
- **Used for:** short-range precipitation and temperature forcing (`APCP`, `TMP`).
- **Access:** `https://noaa-hrrr-bdp-pds.s3.amazonaws.com`.
- **License:** NOAA NODD terms as in 4.3.
- **Citation:** NOAA High-Resolution Rapid Refresh (HRRR) Model was accessed on
  [DATE] from https://registry.opendata.aws/noaa-hrrr-pds.
- **Links:** [Registry entry](https://registry.opendata.aws/noaa-hrrr-pds)

### 4.5 NOAA National Water Model (NWM)

- **Provider:** NOAA Office of Water Prediction; disseminated through NODD.
- **Used for:** short-range `channel_rt` streamflow as solver boundary inflows.
- **Access:** `https://noaa-nwm-pds.s3.amazonaws.com`.
- **License:** NOAA NODD terms as in 4.3.
- **Citation:** NOAA National Water Model Short-Range Forecast was accessed on
  [DATE] from https://registry.opendata.aws/noaa-nwm-pds.
- **Links:** [Registry entry](https://registry.opendata.aws/noaa-nwm-pds) ·
  [About the NWM](https://water.noaa.gov/about/nwm)

### 4.6 USGS National Water Information System (NWIS)

- **Provider:** U.S. Geological Survey.
- **Used for:** instantaneous gage height (00065) and discharge (00060) at the
  five reference gauges: 03049500 Allegheny River at Natrona; 03085000
  Monongahela River at Braddock; 03086000 Ohio River at Sewickley; 03084000
  Turtle Creek at Trafford; 03042000 Blacklick Creek at Josephine. Converted to
  SI units on ingest.
- **Access:** `https://waterservices.usgs.gov/nwis/iv/`.
- **License:** most USGS information is in the U.S. public domain and may be
  used without restriction.
- **Citation:** U.S. Geological Survey, [YEAR], USGS Water Data for the Nation:
  U.S. Geological Survey National Water Information System database, accessed
  [DATE], at https://doi.org/10.5066/F7P55KJN. Short credit:
  "Stream gauge data courtesy of the U.S. Geological Survey."
- **Caveat:** recent values are provisional and subject to revision by USGS.
- **Links:** [USGS water data citation](https://waterdata.usgs.gov/citation) ·
  [Crediting USGS](https://www.usgs.gov/information-policies-and-instructions/crediting-usgs)

### 4.7 Pittsburgh 311 Data

- **Provider:** City of Pittsburgh, Department of Innovation & Performance
  (311 Response Center); hosted by the Western Pennsylvania Regional Data
  Center (WPRDC).
- **Used for:** flooding-related service requests as Tier-3 weak labels
  (reliability weight 0.4).
- **Access:** `https://data.wprdc.org` (dataset `pittsburgh-311-data`).
- **License:** Creative Commons Attribution (CC BY). Attribution is a license
  condition, not a courtesy.
- **Attribution:** "Pittsburgh 311 Data, City of Pittsburgh, via the Western
  Pennsylvania Regional Data Center, licensed CC BY."
- **Caveats:** the City withholds exact locations of some complaints for
  privacy. The City moved to a new 311 system in February 2025, so record
  formats differ before and after that date. WPRDC provides the data without
  warranty.
- **Links:** [Dataset page](https://data.wprdc.org/dataset/pittsburgh-311-data)

### 4.8 FEMA NFIP Redacted Claims (OpenFEMA)

- **Provider:** Federal Emergency Management Agency, Federal Insurance and
  Mitigation Administration.
- **Used for:** National Flood Insurance Program claims as Tier-3 weak labels
  (reliability weight 0.6).
- **Access:** `https://www.fema.gov/api/open/v2/FimaNfipClaims`.
- **License:** OpenFEMA terms and conditions; U.S. government work. The data
  are redacted by FEMA to protect policyholder privacy.
- **Required disclaimer:** "This product uses the Federal Emergency Management
  Agency's OpenFEMA API, but is not endorsed by FEMA. The Federal Government or
  FEMA cannot vouch for the data or analyses derived from these data."
- **Do not** use the FEMA logo or imply FEMA endorsement.
- **Links:** [OpenFEMA terms](https://www.fema.gov/about/openfema/terms-conditions) ·
  [Dataset page](https://www.fema.gov/openfema-data-page/fima-nfip-redacted-claims-v2)

### 4.9 NWS Local Storm Reports (via the Iowa Environmental Mesonet)

- **Provider:** NOAA National Weather Service (reports); Iowa Environmental
  Mesonet (IEM), Iowa State University (service).
- **Used for:** flood reports as Tier-3 weak labels (reliability weight 0.7)
  and an event catalog.
- **Access:** `https://mesonet.agron.iastate.edu/geojson/lsr.geojson`.
- **License:** IEM states its materials are in the public domain and may be
  used for any lawful purpose; NWS products are U.S. government works. No
  accuracy warranty.
- **Attribution (requested, not required):** "NWS Local Storm Reports via the
  Iowa Environmental Mesonet, Iowa State University."
- **Links:** [IEM disclaimer](https://mesonet.agron.iastate.edu/disclaimer.php)

### 4.10 Annual NLCD

- **Provider:** U.S. Geological Survey (MRLC consortium).
- **Used for:** land cover and imperviousness channels; imperviousness is the
  node edited in green-infrastructure scenarios.
- **Citation:** U.S. Geological Survey (USGS), 2024, Annual NLCD Collection 1
  Science Products (ver. 1.1, June 2025): U.S. Geological Survey data release,
  https://doi.org/10.5066/P94UXNTS.
- **Links:** [How to cite Annual NLCD](https://www.usgs.gov/centers/eros/how-do-i-cite-annual-nlcd-data)

### 4.11 Lidar elevation (Pennsylvania)

- **Providers:** USGS QL2 lidar (Western Pennsylvania, 2019–2020; data set
  credit Quantum Spatial, Inc. and USGS); PAMAP Program, Bureau of Topographic
  and Geologic Survey, PA Department of Conservation and Natural Resources
  (2006–2008). Distributed through PASDA and NOAA Office for Coastal Management.
- **Used for:** the 1 m DEM configured as `terrain.dem_path`, coarsened to the
  90 m solver grid; slope and HAND derivatives.
- **License:** metadata records list no access constraints. Use constraints
  note that terrain may have changed since collection and that the data should
  not be used for critical applications without understanding their limits.
- **Credit:** "Elevation data: USGS 3D Elevation Program partners and the PA
  DCNR PAMAP Program, via PASDA."
- **Links:** [USGS QL2 Western PA record](https://www.fisheries.noaa.gov/inport/item/79559) ·
  [PAMAP lidar record](https://www.fisheries.noaa.gov/inport/item/49951)

### 4.12 FEMA National Flood Hazard Layer (NFHL)

- **Provider:** FEMA (listed on data.gov under DHS / HIFLD).
- **Used for:** regulatory flood-zone context in validation.
- **License:** U.S. government work (`usa.gov/government-works`).
- **Caveat:** effective regulatory maps come from FEMA's Map Service Center;
  SatPI products are not regulatory flood maps.
- **Links:** [NFHL on data.gov](https://catalog.data.gov/dataset/national-flood-hazard-layer-nfhl)

### 4.13 Abandoned Mine Land Inventory

- **Provider:** PA Department of Environmental Protection; a subset of the
  federal Office of Surface Mining AML Inventory. Distributed via PASDA.
- **Used for:** optional `mining_features` static layer (SW PA only).
- **License:** **not stated by the distributor.** Treat as a public-agency
  record: credit PA DEP and OSMRE, and confirm terms with PA DEP before
  redistributing the layer itself.
- **Links:** [Catalog record](https://geo.btaa.org/catalog/pasda-458)

### 4.14 USGS high-water marks (Short-Term Network)

- **Provider:** U.S. Geological Survey.
- **Used for:** depth validation against surveyed high-water marks (planned).
- **License:** U.S. public domain. Cite the specific event data release used.
- **Links:** [STN data portal](https://stn.wim.usgs.gov/STNDataPortal)

---

## 5. Models and training data

### 5.1 Clay Foundation Model v1.5
- **License:** Apache-2.0 (weights and code).
- **Citation:** Clay Foundation, Clay Foundation Model. Hugging Face,
  doi:10.57967/hf/1537.
- **Link:** [huggingface.co/made-with-clay/Clay](https://huggingface.co/made-with-clay/Clay)

### 5.2 Prithvi-EO-2.0
- **License:** Apache-2.0.
- **Citation:** Szwarcman, D., Roy, S., Fraccaro, P., et al. (2024).
  Prithvi-EO-2.0: A Versatile Multi-Temporal Foundation Model for Earth
  Observation Applications. arXiv:2412.02732.
- **Link:** [huggingface.co/ibm-nasa-geospatial/Prithvi-EO-2.0-300M](https://huggingface.co/ibm-nasa-geospatial/Prithvi-EO-2.0-300M)

### 5.3 Sen1Floods11
- **License:** the publisher's repository does not state a license.
  Do **not** redistribute the dataset or derived label files from this
  repository; download it from the source. Contact Cloud to Street
  (support@cloudtostreet.info) before any commercial use.
- **Citation:** Bonafilia, D., Tellman, B., Anderson, T., Issenberg, E. (2020).
  Sen1Floods11: a georeferenced dataset to train and test deep learning flood
  algorithms for Sentinel-1. IEEE/CVF CVPR Workshops.
- **Note:** the imagery inside Sen1Floods11 is Copernicus Sentinel data, so the
  notice in 4.1 also applies.
- **Link:** [github.com/cloudtostreet/Sen1Floods11](https://github.com/cloudtostreet/Sen1Floods11)

---

## 6. Services and front-end assets

- **Element 84 Earth Search.** A free STAC API offered on a best-effort basis
  with no service guarantee; Element 84 suggests a private catalog for
  production. [Repository](https://github.com/Element84/earth-search)
- **CARTO basemaps and OpenStreetMap.** The dashboard's Dark Matter vector
  style loads without a key today, but CARTO recommends a free API key and may
  extend its key requirement to vector styles. Free use is capped per month
  (5,000,000 tile requests for non-commercial use; 1,000,000 for commercial use
  from 1 December 2026). Attribution to OpenStreetMap and CARTO must be
  prominent. Map data are © OpenStreetMap contributors under the ODbL. Set
  `SATPI_BASEMAP_API_KEY` to supply a key, or `SATPI_BASEMAP_STYLE_URL` to use
  another provider. [CARTO basemap terms](https://www.carto.com/legal/basemap-terms/) ·
  [CARTO basemap FAQ](https://docs.carto.com/faqs/carto-basemaps) ·
  [OpenStreetMap copyright](https://www.openstreetmap.org/copyright)
- **MapLibre GL JS** (BSD-3-Clause), loaded from the unpkg CDN.
- **Google Earth Engine** (optional, not used by the code). Free only for
  noncommercial and research use; commercial and operational government use
  requires a paid license. Keep Earth Engine in the research path only.
  [Earth Engine noncommercial terms](https://earthengine.google.com/noncommercial)

---

## 7. Sources considered but not used

- **GPM IMERG** precipitation: dropped in favour of MRMS (1 km, 2 min), which
  suits flash-flood nowcasting better.
- **MODIS / VIIRS** near-real-time flood products and **GOES** imagery: named
  in the original concept; not ingested by the current code. If added, they are
  NOAA/NASA open data under the terms in 4.2 and 4.3.
- **GFS / NBM** ensembles and **Landsat**: supported by the `gfs` forcing kind
  and named in the architecture; not enabled in the reference config. Both are
  U.S. government open data.
- **PlanetScope**: commercial imagery; excluded to keep the project open.

---

## 8. Privacy and responsible use

- 311 reports and NFIP claims describe events at or near private property.
  SatPI uses them only as training evidence. **Never publish raw report or
  claim points**; aggregate to census block or coarser before display.
- Do not commit any downloaded records to this repository. The `.gitignore`
  excludes `data/`, model checkpoints and common raster, archive and document
  formats.
- Alerts and maps are decision support. They supplement, and never replace,
  official National Weather Service warnings or FEMA regulatory flood maps.

---

## 9. Review status

Terms were read from the providers' pages on 25 November 2026. Items to confirm
before external publication:

| Item | Status |
|---|---|
| OpenFEMA terms page | Could not be loaded during review; disclaimer wording taken from OpenFEMA's documented requirement as reproduced by rOpenSci's `rfema` package. Re-read the terms page. |
| HLS S30 v2.0 DOI | Landing page could not be loaded during review; confirm the DOI on the LP DAAC page. |
| Sen1Floods11 license | Not stated by the publisher. |
| PA DEP AML inventory license | Not stated by the distributor. |
| Culvert inventory | Source not yet selected. |

---

## 10. Adding a data source

A pull request that adds an ingestor or a new `kind` must also add a row to
Section 2 and an entry to Section 4 with the provider, license, attribution and
a link to the terms. `tests/test_data_sources.py` fails if a configured kind
has no entry here.

---

## 11. Disclaimer

All data are provided by their respective owners without warranty. Mention of
a provider does not imply that provider's endorsement of SatPI. SatPI's outputs
are research products, not official forecasts, warnings or regulatory maps.
