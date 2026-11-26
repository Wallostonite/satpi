"""Alerting rules engine.

Evaluates the study area's AlertRules against each cycle's exceedance fields.
Alerts are decision support supplementing NWS warnings — every payload carries
that framing (governance requirement).

Zones are named geometries registered as boolean masks on the product grid;
the geo pipeline materializes them from vector files at bootstrap. Here the
engine is pure: masks in, alert decisions out — trivially testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
import structlog

from satpi.config import AlertRule

log = structlog.get_logger()

DISCLAIMER = "Decision-support product. Supplements, never replaces, official NWS warnings."


@dataclass
class Alert:
    rule_name: str
    zone: str
    triggered_at: str
    zone_probability: float
    threshold: float
    channels: list[str]
    disclaimer: str = DISCLAIMER


def evaluate_rules(
    rules: list[AlertRule],
    exceedance: np.ndarray,
    zone_masks: dict[str, np.ndarray],
) -> list[Alert]:
    """A rule fires when the mean exceedance probability inside its zone
    crosses the configured threshold."""
    alerts: list[Alert] = []
    now = datetime.now(UTC).isoformat()
    for rule in rules:
        mask = zone_masks.get(rule.geometry)
        if mask is None:
            log.warning("alerts.unknown_zone", rule=rule.name, zone=rule.geometry)
            continue
        if mask.shape != exceedance.shape:
            raise ValueError(
                f"zone {rule.geometry} mask shape {mask.shape} != field {exceedance.shape}"
            )
        if not mask.any():
            continue
        p = float(exceedance[mask].mean())
        if p >= rule.probability_threshold:
            alerts.append(
                Alert(
                    rule_name=rule.name,
                    zone=rule.geometry,
                    triggered_at=now,
                    zone_probability=round(p, 4),
                    threshold=rule.probability_threshold,
                    channels=list(rule.channels),
                )
            )
            log.info("alerts.triggered", rule=rule.name, p=round(p, 3))
    return alerts
