"""Ingestion framework.

Each external data source implements `BaseIngestor`. Ingestors are registered
by `kind` string, so a StudyArea config can enable/disable/swap sources with no
pipeline-code changes — the key to portability across regions.

Production behaviors baked in:
- bounded retries with exponential backoff + jitter (tenacity)
- explicit timeouts on every request
- structured logging with source/region context
- idempotent writes keyed by (source, asset_id) so re-runs are safe
"""

from __future__ import annotations

import abc
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

log = structlog.get_logger()

_REGISTRY: dict[str, type[BaseIngestor]] = {}


def register(kind: str):
    """Class decorator: register an ingestor under a config `kind` string."""

    def deco(cls: type[BaseIngestor]) -> type[BaseIngestor]:
        _REGISTRY[kind] = cls
        cls.kind = kind
        return cls

    return deco


def get_ingestor(kind: str) -> type[BaseIngestor]:
    try:
        return _REGISTRY[kind]
    except KeyError as e:
        known = sorted(_REGISTRY)
        raise KeyError(f"No ingestor registered for kind={kind!r}. Known: {known}") from e


@dataclass
class Asset:
    """A single ingested item, normalized for the platform catalog."""

    source: str
    asset_id: str
    timestamp: datetime
    payload: Any  # parsed content or a local file path for large binaries
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.asset_id}"


class BaseIngestor(abc.ABC):
    """Abstract ingestor. Subclasses implement `fetch`."""

    kind: ClassVar[str] = "base"
    timeout_s: ClassVar[float] = 30.0

    def __init__(self, endpoint: str = "", **kwargs: Any) -> None:
        self.endpoint = endpoint or self.default_endpoint()
        self.options = kwargs
        self._client: httpx.Client | None = None

    @classmethod
    def default_endpoint(cls) -> str:
        return ""

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.timeout_s,
                headers={"User-Agent": "satpi/0.1 (flood-intelligence-platform)"},
            )
        return self._client

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential_jitter(initial=1, max=20),
        reraise=True,
    )
    def _get(self, url: str, **params: Any) -> httpx.Response:
        resp = self.client.get(url, params=params or None)
        resp.raise_for_status()
        return resp

    @abc.abstractmethod
    def fetch(self, start: datetime, end: datetime, **kwargs: Any) -> Iterable[Asset]:
        """Yield Assets for the given time window."""

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
