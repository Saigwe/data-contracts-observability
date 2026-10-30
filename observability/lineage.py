"""Lineage graph, impact analysis and OpenLineage-style events."""
from __future__ import annotations

import json
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path

import yaml


def load_graph(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["nodes"]


def downstream(graph: dict, start: str) -> list[str]:
    """Every node that depends on `start`, breadth-first."""
    children: dict[str, list[str]] = {}
    for name, node in graph.items():
        for up in node.get("upstream", []):
            children.setdefault(up, []).append(name)
    seen, queue, order = {start}, deque([start]), []
    while queue:
        for child in children.get(queue.popleft(), []):
            if child not in seen:
                seen.add(child)
                order.append(child)
                queue.append(child)
    return order


def impact(graph: dict, dataset: str) -> dict:
    nodes = downstream(graph, dataset)
    return {"models": [n for n in nodes if graph[n]["type"] == "model"],
            "exposures": [{"name": n, "owner": graph[n]["owner"], "tier": graph[n]["tier"]}
                          for n in nodes if graph[n]["type"] == "exposure"]}


def openlineage_event(dataset: str, status: str, run_time: datetime, facets: dict) -> dict:
    """Minimal OpenLineage RunEvent describing a contract-check run on one dataset."""
    return {
        "eventType": "COMPLETE" if status == "pass" else "FAIL",
        "eventTime": run_time.isoformat() + "Z",
        "producer": "https://github.com/Saigwe/data-contracts-observability",
        "run": {"runId": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{dataset}{run_time}"))},
        "job": {"namespace": "data-contracts", "name": f"contract_check.{dataset}"},
        "inputs": [{"namespace": "warehouse", "name": dataset,
                    "facets": {"dataQualityAssertions": {"assertions": facets["assertions"]}}}],
        "outputs": [],
    }


def write_events(events: list[dict], path: Path) -> None:
    path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
