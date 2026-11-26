"""USGS NWIS instantaneous-values ingestor (stage + discharge).

API docs: https://waterservices.usgs.gov/docs/instantaneous-values/
Parameter codes: 00065 = gage height (ft), 00060 = discharge (cfs).
Values are normalized to SI (meters, m^3/s) on ingest so every downstream
component works in one unit system regardless of region.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import structlog

from satpi.ingestion.base import Asset, BaseIngestor, register

log = structlog.get_logger()

FT_TO_M = 0.3048
CFS_TO_CMS = 0.028316846592

PARAM_STAGE = "00065"
PARAM_DISCHARGE = "00060"


@register("usgs_iv")
class UsgsInstantaneousValues(BaseIngestor):
    @classmethod
    def default_endpoint(cls) -> str:
        return "https://waterservices.usgs.gov/nwis/iv/"

    def fetch(
        self,
        start: datetime,
        end: datetime,
        station_ids: list[str] | None = None,
        **kwargs: Any,
    ) -> Iterable[Asset]:
        if not station_ids:
            log.warning("usgs.no_stations_configured")
            return
        resp = self._get(
            self.endpoint,
            sites=",".join(station_ids),
            parameterCd=f"{PARAM_STAGE},{PARAM_DISCHARGE}",
            startDT=start.astimezone(UTC).isoformat(),
            endDT=end.astimezone(UTC).isoformat(),
            format="json",
        )
        body = resp.json()
        for series in body.get("value", {}).get("timeSeries", []):
            site = series["sourceInfo"]["siteCode"][0]["value"]
            param = series["variable"]["variableCode"][0]["value"]
            unit_scale, var_name = {
                PARAM_STAGE: (FT_TO_M, "stage_m"),
                PARAM_DISCHARGE: (CFS_TO_CMS, "discharge_cms"),
            }.get(param, (1.0, f"param_{param}"))
            points = [
                {
                    "t": v["dateTime"],
                    var_name: float(v["value"]) * unit_scale,
                    "qc": v.get("qualifiers", []),
                }
                for block in series.get("values", [])
                for v in block.get("value", [])
                if v.get("value") not in (None, "", "-999999")
            ]
            if not points:
                continue
            yield Asset(
                source="usgs_iv",
                asset_id=f"{site}:{var_name}:{start.isoformat()}",
                timestamp=end,
                payload=points,
                meta={"station_id": site, "variable": var_name, "n": len(points)},
            )
        log.info("usgs.fetch_complete", stations=len(station_ids))
