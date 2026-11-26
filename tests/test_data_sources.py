"""Every data source the platform can ingest must be credited in DATA_SOURCES.md.

Adding an ingestor or enabling a new source `kind` in a study-area config
without documenting its license and attribution fails this test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from satpi.config import StudyArea
from satpi.ingestion import base

ROOT = Path(__file__).resolve().parents[1]
CREDITS = (ROOT / "DATA_SOURCES.md").read_text()
CONFIGS = sorted((ROOT / "configs" / "study_areas").glob("*.yaml"))


def _configured_kinds() -> set[str]:
    kinds: set[str] = set()
    for path in CONFIGS:
        area = StudyArea.from_yaml(path)
        kinds |= {f.kind for f in area.forcing}
        kinds |= {s.kind for s in area.satellites}
        kinds |= {w.kind for w in area.weak_labels}
    return kinds


@pytest.mark.parametrize("kind", sorted(_configured_kinds() | set(base._REGISTRY)))
def test_every_source_kind_is_credited(kind):
    assert f"`{kind}`" in CREDITS, f"add `{kind}` to DATA_SOURCES.md (license + attribution)"


@pytest.mark.parametrize(
    "notice",
    [
        "Contains modified Copernicus Sentinel data",
        "but is not endorsed by FEMA",
        "licensed CC BY",
        "https://doi.org/10.5066/F7P55KJN",
        "OpenStreetMap",
    ],
)
def test_required_attribution_present(notice):
    assert notice in CREDITS
