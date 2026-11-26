"""Satellite scene discovery via STAC, plus NOAA open-data forcing ingestors.

Discovery is separated from download: `SatelliteDiscovery` finds new scenes
intersecting the study area and registers them as catalog assets; the
preprocessing workers download and process asset hrefs on their own schedule.
This keeps ingestion cheap and lets the platform scale scene processing
horizontally.

All sources here are global (STAC/Sentinel) or CONUS NOAA buckets; regions
outside CONUS disable the NOAA forcing kinds in config and register
generic_grib/generic_zarr sources instead.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

import structlog

from satpi.config import BoundingBox
from satpi.ingestion.base import Asset, BaseIngestor, register

log = structlog.get_logger()


@register("stac_satellite")
class SatelliteDiscovery(BaseIngestor):
    """Query a STAC API for new scenes over the AOI."""

    @classmethod
    def default_endpoint(cls) -> str:
        return "https://earth-search.aws.element84.com/v1"

    def fetch(
        self,
        start: datetime,
        end: datetime,
        bbox: BoundingBox | None = None,
        collection: str = "sentinel-1-grd",
        max_items: int = 200,
        **kwargs: Any,
    ) -> Iterable[Asset]:
        if bbox is None:
            raise ValueError("bbox is required for satellite discovery")
        payload = {
            "collections": [collection],
            "bbox": list(bbox.as_tuple()),
            "datetime": f"{start.isoformat()}Z/{end.isoformat()}Z".replace("+00:00Z", "Z"),
            "limit": min(max_items, 200),
        }
        resp = self.client.post(f"{self.endpoint}/search", json=payload)
        resp.raise_for_status()
        for feat in resp.json().get("features", []):
            props = feat.get("properties", {})
            yield Asset(
                source=f"stac:{collection}",
                asset_id=feat["id"],
                timestamp=datetime.fromisoformat(props["datetime"].replace("Z", "+00:00")),
                payload={k: v.get("href") for k, v in feat.get("assets", {}).items()},
                meta={
                    "collection": collection,
                    "platform": props.get("platform"),
                    "cloud_cover": props.get("eo:cloud_cover"),
                    "sar:polarizations": props.get("sar:polarizations"),
                    "geometry": feat.get("geometry"),
                },
            )


@register("mrms_qpe")
class MrmsQpe(BaseIngestor):
    """MRMS quantitative precipitation estimates from the NOAA AWS bucket.

    Yields hrefs of GRIB2 objects for the window; decoding happens in the
    forcing worker (requires the geo extra) so the core stays light.
    """

    @classmethod
    def default_endpoint(cls) -> str:
        return "https://noaa-mrms-pds.s3.amazonaws.com"

    def fetch(
        self,
        start: datetime,
        end: datetime,
        product: str = "MultiSensor_QPE_01H_Pass2",
        **kwargs: Any,
    ) -> Iterable[Asset]:
        from datetime import timedelta

        # MRMS objects are keyed by product/date; hourly products post one file/hour.
        t = start.replace(minute=0, second=0, microsecond=0)
        while t <= end:
            key = (
                f"CONUS/{product}_00.00/{t:%Y%m%d}/"
                f"MRMS_{product}_00.00_{t:%Y%m%d-%H%M%S}.grib2.gz"
            )
            yield Asset(
                source="mrms_qpe",
                asset_id=key,
                timestamp=t,
                payload={"href": f"{self.endpoint}/{key}"},
                meta={"product": product},
            )
            t += timedelta(hours=1)


@register("nwm")
class NationalWaterModel(BaseIngestor):
    """NWM channel output hrefs (short_range) from the NOAA AWS bucket."""

    @classmethod
    def default_endpoint(cls) -> str:
        return "https://noaa-nwm-pds.s3.amazonaws.com"

    def fetch(
        self, start: datetime, end: datetime, horizon_hours: int = 18, **kwargs: Any
    ) -> Iterable[Asset]:
        cycle = start.replace(minute=0, second=0, microsecond=0)
        for fhr in range(1, horizon_hours + 1):
            key = (
                f"nwm.{cycle:%Y%m%d}/short_range/"
                f"nwm.t{cycle:%H}z.short_range.channel_rt.f{fhr:03d}.conus.nc"
            )
            yield Asset(
                source="nwm",
                asset_id=key,
                timestamp=cycle,
                payload={"href": f"{self.endpoint}/{key}"},
                meta={"forecast_hour": fhr, "cycle": cycle.isoformat()},
            )
