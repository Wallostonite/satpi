"""Structural causal model (SCM) for scenario analysis.

Design decision: the causal graph is *encoded from hydrologic domain knowledge*,
not discovered from data. Data-driven discovery (PCMCI, in causal/discovery.py,
requires the `causal` extra) is used only to adjudicate uncertain edges before
they are admitted here.

The SCM is deliberately thin: hydraulic node mechanisms delegate to the same
Layer-2 components used for forecasting (solver + downscaler), which guarantees
counterfactual maps are consistent with forecast maps. What this module owns is
the graph, the intervention semantics, and validation that a requested query is
answerable.

Region portability: the *default* graph below encodes drivers common to any
rain-driven flood regime; region configs extend it (e.g., SW PA adds the
mining-drainage node) via `add_mechanism`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import networkx as nx

Mechanism = Callable[[dict[str, Any]], Any]


DEFAULT_EDGES: list[tuple[str, str]] = [
    ("precipitation", "soil_moisture"),
    ("precipitation", "runoff"),
    ("soil_moisture", "runoff"),
    ("imperviousness", "runoff"),
    ("runoff", "tributary_discharge"),
    ("tributary_discharge", "mainstem_stage"),
    ("upstream_inflow", "mainstem_stage"),
    ("drainage_capacity", "urban_inundation"),
    ("runoff", "urban_inundation"),
    ("mainstem_stage", "inundation"),
    ("tributary_discharge", "inundation"),
    ("urban_inundation", "inundation"),
    ("conveyance_infrastructure", "inundation"),
]


@dataclass
class Intervention:
    """do(node := value) — hard intervention, or a multiplicative shift."""

    node: str
    value: Any = None
    scale: float | None = None  # e.g. scale=0.8 => reduce node output by 20%

    def __post_init__(self) -> None:
        if (self.value is None) == (self.scale is None):
            raise ValueError("provide exactly one of value= or scale=")


@dataclass
class ScmResult:
    outputs: dict[str, Any]
    interventions: list[Intervention]
    is_counterfactual: bool
    provenance: dict[str, Any] = field(default_factory=dict)


class StructuralCausalModel:
    def __init__(self, edges: list[tuple[str, str]] | None = None) -> None:
        self.graph = nx.DiGraph(edges if edges is not None else list(DEFAULT_EDGES))
        if not nx.is_directed_acyclic_graph(self.graph):
            raise ValueError("causal graph must be a DAG")
        self.mechanisms: dict[str, Mechanism] = {}

    # -- construction ---------------------------------------------------- #

    def add_mechanism(
        self,
        node: str,
        fn: Mechanism,
        parents: list[str] | None = None,
    ) -> None:
        """Attach the structural equation for `node`. New nodes (with their
        parent edges) may be introduced here — this is how region configs
        extend the default graph (e.g., mining drainage in SW PA)."""
        if parents:
            for p in parents:
                self.graph.add_edge(p, node)
            if not nx.is_directed_acyclic_graph(self.graph):
                raise ValueError(f"adding {node} with parents {parents} creates a cycle")
        self.mechanisms[node] = fn

    def validate(self, targets: list[str]) -> None:
        """A query is answerable iff every non-exogenous ancestor of every
        target has a mechanism. Fails fast with the missing set."""
        needed: set[str] = set()
        for t in targets:
            if t not in self.graph:
                raise KeyError(f"unknown node {t!r}")
            needed |= nx.ancestors(self.graph, t) | {t}
        endogenous = {n for n in needed if self.graph.in_degree(n) > 0}
        missing = endogenous - set(self.mechanisms)
        if missing:
            raise ValueError(f"no mechanism for nodes: {sorted(missing)}")

    # -- inference ------------------------------------------------------- #

    def run(
        self,
        exogenous: dict[str, Any],
        targets: list[str],
        interventions: list[Intervention] | None = None,
    ) -> ScmResult:
        """Evaluate targets in topological order under optional interventions.

        Interventions sever the node from its parents (do-operator): a `value`
        intervention pins the node; a `scale` intervention post-multiplies the
        mechanism output (soft intervention, used for e.g. 'reduce
        imperviousness by 20%' where the node is a field, handled by the
        mechanism contract).
        """
        interventions = interventions or []
        self.validate(targets)
        pinned = {iv.node: iv for iv in interventions}
        values: dict[str, Any] = dict(exogenous)

        for node in nx.topological_sort(self.graph):
            iv = pinned.get(node)
            if iv is not None and iv.value is not None:
                values[node] = iv.value  # hard do()
                continue
            if node in values and node not in self.mechanisms:
                continue  # exogenous input
            if node in self.mechanisms:
                parent_vals = {p: values[p] for p in self.graph.predecessors(node) if p in values}
                out = self.mechanisms[node](parent_vals)
                if iv is not None and iv.scale is not None:
                    out = _scale(out, iv.scale)
                values[node] = out

        return ScmResult(
            outputs={t: values[t] for t in targets},
            interventions=interventions,
            is_counterfactual=bool(interventions),
            provenance={"nodes_evaluated": [n for n in self.graph if n in values]},
        )

    def compare(
        self,
        exogenous: dict[str, Any],
        targets: list[str],
        interventions: list[Intervention],
    ) -> dict[str, dict[str, Any]]:
        """Baseline vs. intervention — the Scenario Studio primitive."""
        base = self.run(exogenous, targets)
        alt = self.run(exogenous, targets, interventions)
        return {"baseline": base.outputs, "scenario": alt.outputs}


def _scale(x: Any, s: float) -> Any:
    try:
        return x * s
    except TypeError as e:
        raise TypeError(
            f"scale intervention requires a scalable node output, got {type(x).__name__}"
        ) from e


def pseudo_global_warming_delta(
    precip_field: Any, delta_temp_c: float, cc_rate: float = 0.07
) -> Any:
    """Clausius–Clapeyron scaling of precipitation intensity for PGW
    counterfactuals (~7%/°C default). Applied to *forcing*, then run through
    the ordinary chain — clearly a scenario product, never a forecast."""
    return precip_field * (1.0 + cc_rate) ** delta_temp_c
