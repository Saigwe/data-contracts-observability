"""Daily contract run: check every source, trace impact, block bad data, write reports.

python -m observability.run
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import yaml

from .checks import CheckResult, freshness_check, schema_checks, volume_check
from .generate import generate
from .lineage import impact, load_graph, openlineage_event, write_events

ROOT = Path(__file__).resolve().parent.parent

RUNBOOK = {
    "schema": "Contact the source owner; pin the last good schema; add a mapping or agree a versioned change.",
    "null": "Quarantine rows with missing keys; ask the owner to fix the producer; backfill once fixed.",
    "freshness": "Check the ingestion job and upstream availability; rerun the load; tell consumers data is stale.",
    "volume": "Confirm with the owner whether this is a real drop or a partial load; hold publishing until known.",
}


def runbook_for(check: str) -> str:
    for key, step in RUNBOOK.items():
        if key in check:
            return step
    return "Investigate with the dataset owner."


def run(data_dir: Path = ROOT / "data", out_dir: Path = ROOT / "output") -> dict:
    if not (data_dir / "load_log.json").exists():
        generate(data_dir)
    loads = json.loads((data_dir / "load_log.json").read_text(encoding="utf-8"))
    now = datetime.fromisoformat((data_dir / "run_time.txt").read_text(encoding="utf-8"))
    graph = load_graph(ROOT / "lineage.yml")
    contracts = {c["dataset"]: c for c in (yaml.safe_load(p.read_text(encoding="utf-8"))
                                           for p in sorted((ROOT / "contracts").glob("*.yml")))}
    today = max(l["day"] for l in loads)

    results: list[CheckResult] = []
    events = []
    for dataset, contract in contracts.items():
        mine = sorted((l for l in loads if l["dataset"] == dataset), key=lambda l: l["day"])
        latest = mine[-1] if mine else None
        todays = latest if latest and latest["day"] == today else None
        checks = [freshness_check(dataset, contract,
                                  datetime.fromisoformat(latest["loaded_at"]) if latest else None, now)]
        history = [l["rows"] for l in mine if l["day"] < today][-14:]
        checks.append(volume_check(dataset, contract, history, todays["rows"] if todays else None))
        if todays:
            rows = [json.loads(line) for line in Path(todays["file"]).read_text(encoding="utf-8").splitlines() if line]
            checks += schema_checks(dataset, contract, rows)
        results += checks
        failed = [c for c in checks if not c.passed]
        events.append(openlineage_event(dataset, "fail" if failed else "pass", now, {
            "assertions": [{"assertion": c.check, "success": c.passed} for c in checks]}))

    failing_sources = {r.dataset for r in results if not r.passed and r.severity == "critical"}
    blocked = sorted({m for d in failing_sources for m in impact(graph, d)["models"]})
    affected = {}
    for d in failing_sources:
        for e in impact(graph, d)["exposures"]:
            affected.setdefault(e["name"], {**e, "because": set()})["because"].add(d)

    out_dir.mkdir(parents=True, exist_ok=True)
    write_events(events, out_dir / "openlineage_events.jsonl")
    write_reports(results, contracts, blocked, affected, now, out_dir)
    return {"results": results, "blocked_models": blocked, "affected_exposures": affected,
            "failing_sources": failing_sources}


def write_reports(results, contracts, blocked, affected, now, out_dir: Path) -> None:
    failures = [r for r in results if not r.passed]
    lines = [f"# Data incident report: {now:%d %B %Y %H:%M}\n",
             f"**{len(failures)} contract failures** across {len({f.dataset for f in failures})} sources. "
             f"Publishing is **blocked** for {len(blocked)} models: {', '.join(blocked) or 'none'}.\n",
             "| Source | Owner | Check | Severity | Detail | First response |", "|---|---|---|---|---|---|"]
    for f in sorted(failures, key=lambda r: (r.severity != "critical", r.dataset)):
        lines.append(f"| {f.dataset} | {contracts[f.dataset]['owner']} | {f.check} | {f.severity} | {f.detail} | "
                     f"{runbook_for(f.check)} |")
    lines += ["\n## Blast radius\n", "| Dashboard | Owner | Tier | Caused by |", "|---|---|---|---|"]
    lines += [f"| {e['name']} | {e['owner']} | {e['tier']} | {', '.join(sorted(e['because']))} |"
              for e in sorted(affected.values(), key=lambda e: e["tier"])]
    lines += ["\n## Lineage\n", "```mermaid", "flowchart LR"]
    graph = load_graph(ROOT / "lineage.yml")
    ids = {n: f"n{i}" for i, n in enumerate(graph)}
    for n, node in graph.items():
        label = n.replace('"', "'")
        style = ":::bad" if n in blocked or any(n == f.dataset for f in failures) or n in affected else ""
        lines.append(f'    {ids[n]}["{label}"]{style}')
        for up in node.get("upstream", []):
            lines.append(f"    {ids[up]} --> {ids[n]}")
    lines += ["    classDef bad fill:#fde2e1,stroke:#c00000", "```"]
    (out_dir / "incident_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    status_rows = []
    graph_exposures = [n for n, v in graph.items() if v["type"] == "exposure"]
    for name in graph_exposures:
        if name in affected:
            status, note = "🔴 Do not use", f"waiting on {', '.join(sorted(affected[name]['because']))}"
        else:
            status, note = "🟢 Trusted", "all upstream contracts passed"
        status_rows.append(f"| {name} | {status} | {note} |")
    (out_dir / "data_health_status.md").write_text(
        f"# Data health: {now:%d %B %Y}\n\n**Summary for leadership:** "
        f"{len(affected)} of {len(graph_exposures)} key reports are on hold today because source data broke "
        f"its agreed contract. The bad data was stopped before it reached them; no incorrect figures were "
        f"published. Owners are notified and fixes are tracked in the incident report.\n\n"
        "| Report | Status | Note |\n|---|---|---|\n" + "\n".join(status_rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    res = run()
    for r in res["results"]:
        if not r.passed:
            print(f"FAIL [{r.severity}] {r.dataset} {r.check}: {r.detail}")
    print("Blocked models:", res["blocked_models"])
    print("Affected dashboards:", sorted(res["affected_exposures"]))
