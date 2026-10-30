from datetime import datetime
from pathlib import Path

import pytest

from observability.checks import freshness_check, schema_checks, volume_check
from observability.generate import generate
from observability.lineage import downstream, impact, load_graph
from observability.run import ROOT, run

CONTRACT = {"freshness_sla_hours": 6, "volume": {"max_abs_z": 4},
            "schema": {"id": {"type": "string", "required": True, "unique": True},
                       "amount": {"type": "number", "required": True, "min": 0},
                       "status": {"type": "string", "required": True, "allowed": ["a", "b"]}}}


def test_schema_checks_catch_each_rule():
    rows = [{"id": "1", "amount": 5, "status": "a"}, {"id": "1", "amount": -1, "status": "z"},
            {"id": None, "amount": "x", "status": "b"}]
    failed = {r.check for r in schema_checks("t", CONTRACT, rows) if not r.passed}
    assert {"id: null rate", "id: unique", "amount: type number", "amount: range",
            "status: allowed values"} <= failed


def test_missing_column_is_critical():
    res = schema_checks("t", CONTRACT, [{"id": "1", "amount_v2": 5, "status": "a"}])
    first = res[0]
    assert not first.passed and first.severity == "critical" and "amount" in first.detail


def test_freshness_and_volume():
    now = datetime(2026, 10, 2, 12)
    assert freshness_check("t", CONTRACT, datetime(2026, 10, 2, 8), now).passed
    assert not freshness_check("t", CONTRACT, datetime(2026, 10, 1, 12), now).passed
    history = [1000, 1010, 990, 1005, 995, 1002, 998, 1001]
    assert volume_check("t", CONTRACT, history, 1003).passed
    assert not volume_check("t", CONTRACT, history, 400).passed


def test_impact_analysis_follows_lineage():
    graph = load_graph(ROOT / "lineage.yml")
    assert "fct_revenue_daily" in downstream(graph, "raw.payments")
    names = {e["name"] for e in impact(graph, "raw.customers")["exposures"]}
    assert names == {"Customer segmentation report", "Executive revenue dashboard"}


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    base = tmp_path_factory.mktemp("obs")
    return run(generate(base / "data"), base / "out"), base


def test_all_planted_incidents_detected(result):
    res, _ = result
    fails = {(r.dataset, r.check) for r in res["results"] if not r.passed}
    assert ("raw.payments", "schema: expected columns present") in fails
    assert ("raw.orders", "volume") in fails
    assert ("raw.orders", "customer_id: null rate") in fails
    assert ("raw.customers", "freshness") in fails
    assert not any(d == "raw.tickets" for d, _ in fails)            # healthy source stays green


def test_circuit_breaker_blocks_only_affected(result):
    res, base = result
    assert "fct_revenue_daily" in res["blocked_models"]
    assert "stg_tickets" not in res["blocked_models"]
    assert "Support SLA dashboard" not in res["affected_exposures"]
    status = (base / "out" / "data_health_status.md").read_text(encoding="utf-8")
    assert "Support SLA dashboard | 🟢 Trusted" in status
    assert Path(base / "out" / "openlineage_events.jsonl").read_text().count('"eventType": "FAIL"') == 3
