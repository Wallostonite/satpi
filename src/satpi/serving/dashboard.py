"""Minimal operational dashboard, server-rendered.

Design intent: a hydrologist's ops room, not a marketing page. Deep river-water
palette, tabular numerals for readings, and one signature element — the gauge
strip across the top, styled like staff-gauge boards, red-lining when a station
passes flood stage. The full React/deck.gl client (see docs) replaces this in
the operational phase; this page keeps the pilot observable from day one.
"""

from __future__ import annotations

import json

from satpi.config import Settings, StudyArea

DATA_CREDIT = (
    "Data: NOAA MRMS, HRRR &amp; National Water Model; USGS NWIS; "
    "contains modified Copernicus Sentinel data. Not endorsed by NOAA, USGS, NASA or FEMA."
)


def render_dashboard(area: StudyArea, settings: Settings | None = None) -> str:
    settings = settings or Settings()
    style_url = settings.basemap_style_url
    if settings.basemap_api_key:
        sep = "&" if "?" in style_url else "?"
        style_url = f"{style_url}{sep}key={settings.basemap_api_key}"
    attribution = json.dumps(settings.basemap_attribution)
    center_lon = (area.bbox.west + area.bbox.east) / 2
    center_lat = (area.bbox.south + area.bbox.north) / 2
    gauges = json.dumps(
        [
            {"id": g.station_id, "name": g.name, "river": g.river, "flood_stage_m": g.flood_stage_m}
            for g in area.gauges
        ]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SatPI · {area.name}</title>
<link href="https://unpkg.com/maplibre-gl@4.5.0/dist/maplibre-gl.css" rel="stylesheet">
<script src="https://unpkg.com/maplibre-gl@4.5.0/dist/maplibre-gl.js"></script>
<style>
  :root {{
    --ink:#0b1720; --panel:#101f2b; --line:#1e3444; --silt:#8fa8b8;
    --water:#3ea6c9; --alert:#e4572e; --ok:#7fb069; --text:#dce8ef;
  }}
  * {{ box-sizing:border-box; margin:0; }}
  body {{ background:var(--ink); color:var(--text);
    font:14px/1.5 "Iosevka","IBM Plex Mono",ui-monospace,Menlo,monospace; }}
  header {{ padding:14px 20px 10px; border-bottom:1px solid var(--line);
    display:flex; align-items:baseline; gap:16px; flex-wrap:wrap; }}
  header h1 {{ font-size:15px; font-weight:600; letter-spacing:.08em; text-transform:uppercase; }}
  header .sub {{ color:var(--silt); font-size:12px; }}
  #gauge-strip {{ display:flex; gap:1px; background:var(--line);
    border-bottom:1px solid var(--line); overflow-x:auto; }}
  .gauge {{ flex:1 1 0; min-width:150px; background:var(--panel); padding:10px 14px; }}
  .gauge .river {{ font-size:11px; color:var(--silt); text-transform:uppercase;
    letter-spacing:.06em; }}
  .gauge .stage {{ font-size:22px; font-variant-numeric:tabular-nums; }}
  .gauge .stage small {{ font-size:11px; color:var(--silt); }}
  .gauge.flooding {{ box-shadow: inset 0 3px 0 var(--alert); }}
  .gauge.flooding .stage {{ color:var(--alert); }}
  main {{ display:grid; grid-template-columns: 1fr 320px; height: calc(100vh - 118px); }}
  #map {{ height:100%; }}
  aside {{ border-left:1px solid var(--line); padding:16px; overflow-y:auto;
    background:var(--panel); }}
  aside h2 {{ font-size:12px; letter-spacing:.08em; text-transform:uppercase;
    color:var(--silt); margin-bottom:8px; }}
  .kv {{ display:flex; justify-content:space-between; padding:4px 0;
    border-bottom:1px dotted var(--line); }}
  .kv b {{ font-variant-numeric:tabular-nums; font-weight:500; }}
  .badge {{ display:inline-block; padding:1px 8px; border-radius:2px; font-size:11px; }}
  .badge.ok {{ background:var(--ok); color:var(--ink); }}
  .badge.degraded {{ background:var(--alert); color:var(--ink); }}
  .note {{ margin-top:14px; font-size:11px; color:var(--silt); }}
  @media (max-width:800px) {{ main {{ grid-template-columns:1fr; grid-template-rows:55vh auto; }} }}
</style>
</head>
<body>
<header>
  <h1>SatPI Flood Intelligence</h1>
  <span class="sub">{area.name}</span>
  <span class="sub" id="cycle-time">awaiting first cycle</span>
</header>
<div id="gauge-strip"></div>
<main>
  <div id="map"></div>
  <aside>
    <h2>Latest cycle</h2>
    <div class="kv"><span>Status</span><b id="status">—</b></div>
    <div class="kv"><span>Wet fraction (&gt;15 cm)</span><b id="wet">—</b></div>
    <div class="kv"><span>Mass residual</span><b id="mass">—</b></div>
    <div class="kv"><span>Terrain violations</span><b id="terrain">—</b></div>
    <p class="note">Decision-support products. They supplement, and never replace,
    official National Weather Service warnings.</p>
    <p class="note">{DATA_CREDIT} Full credits: DATA_SOURCES.md.</p>
  </aside>
</main>
<script>
const GAUGES = {gauges};
const map = new maplibregl.Map({{
  container: 'map',
  style: {json.dumps(style_url)},
  attributionControl: false,
  center: [{center_lon}, {center_lat}], zoom: 8.3,
}});
map.addControl(new maplibregl.NavigationControl());
map.addControl(new maplibregl.AttributionControl({{
  compact: false, customAttribution: {attribution},
}}));

const strip = document.getElementById('gauge-strip');
for (const g of GAUGES) {{
  const el = document.createElement('div');
  el.className = 'gauge'; el.id = 'g-' + g.id;
  el.innerHTML = `<div class="river">${{g.river || g.name}}</div>
    <div class="stage">— <small>m</small></div>`;
  strip.appendChild(el);
}}

async function refresh() {{
  try {{
    const r = await fetch('/v1/products/latest');
    if (!r.ok) return;
    const p = await r.json();
    document.getElementById('cycle-time').textContent = 'cycle ' + p.cycle_time;
    document.getElementById('status').innerHTML =
      p.degraded ? '<span class="badge degraded">degraded (coarse)</span>'
                 : '<span class="badge ok">nominal</span>';
    document.getElementById('wet').textContent = (100 * p.wet_fraction).toFixed(2) + ' %';
    document.getElementById('mass').textContent =
      p.consistency.mass_conservation_residual.toFixed(4);
    document.getElementById('terrain').textContent = p.consistency.uphill_flow_violation.toFixed(4);
  }} catch (e) {{ /* API not up yet; retry on next tick */ }}
}}
refresh(); setInterval(refresh, 30000);
</script>
</body>
</html>"""
