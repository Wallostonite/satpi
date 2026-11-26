"""Tiered label store.

Flood labels come in three reliability tiers (see architecture doc §2.2):
  Tier 1 — hand-validated satellite masks for major events (gold)
  Tier 2 — GFM-generated masks, analyst spot-checked (silver)
  Tier 3 — weak point/polygon evidence: 311 reports, NFIP claims, LSRs (bronze)

The store is append-only and versioned: labels are never mutated, only
superseded, so every training run's exact label set is reconstructible
(governance requirement). Storage is JSON-lines on the local data root for the
pilot; the interface is deliberately narrow so a PostGIS/GeoParquet backend
drops in for the operational phase.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

Tier = Literal[1, 2, 3]

# Default per-tier loss weights; learned per-source reliability (config) can
# refine tier-3 weights further.
TIER_WEIGHTS: dict[Tier, float] = {1: 1.0, 2: 0.7, 3: 0.35}


@dataclass
class LabelRecord:
    label_id: str
    tier: Tier
    event_id: str  # e.g. "ida-2021"
    geometry_ref: str  # path/URI to mask raster or vector evidence
    source: str
    reliability: float
    created_at: str
    study_area_id: str
    superseded_by: str | None = None
    meta: dict = field(default_factory=dict)


class LabelStore:
    def __init__(self, root: Path, study_area_id: str) -> None:
        self.path = Path(root) / "labels" / f"{study_area_id}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.study_area_id = study_area_id

    def add(
        self,
        tier: Tier,
        event_id: str,
        geometry_ref: str,
        source: str,
        reliability: float | None = None,
        meta: dict | None = None,
    ) -> LabelRecord:
        if tier not in (1, 2, 3):
            raise ValueError("tier must be 1, 2, or 3")
        rec = LabelRecord(
            label_id=uuid.uuid4().hex,
            tier=tier,
            event_id=event_id,
            geometry_ref=geometry_ref,
            source=source,
            reliability=TIER_WEIGHTS[tier] if reliability is None else float(reliability),
            created_at=datetime.now(UTC).isoformat(),
            study_area_id=self.study_area_id,
            meta=meta or {},
        )
        with open(self.path, "a") as f:
            f.write(json.dumps(asdict(rec)) + "\n")
        return rec

    def supersede(self, old_label_id: str, new: LabelRecord) -> None:
        """Append-only supersession: write a tombstone pointer, never edit."""
        with open(self.path, "a") as f:
            f.write(
                json.dumps(
                    {"label_id": old_label_id, "superseded_by": new.label_id, "tombstone": True}
                )
                + "\n"
            )

    def active(self, event_id: str | None = None, tier: Tier | None = None) -> list[LabelRecord]:
        records: dict[str, LabelRecord] = {}
        tombstoned: set[str] = set()
        if not self.path.exists():
            return []
        with open(self.path) as f:
            for line in f:
                obj = json.loads(line)
                if obj.get("tombstone"):
                    tombstoned.add(obj["label_id"])
                    continue
                records[obj["label_id"]] = LabelRecord(**obj)
        out = [r for lid, r in records.items() if lid not in tombstoned]
        if event_id is not None:
            out = [r for r in out if r.event_id == event_id]
        if tier is not None:
            out = [r for r in out if r.tier == tier]
        return sorted(out, key=lambda r: r.created_at)
