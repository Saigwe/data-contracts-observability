"""Contract checks: schema, quality rules, freshness and volume. Each returns CheckResult objects."""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime

TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "timestamp": lambda v: isinstance(v, str) and _is_ts(v),
}


def _is_ts(v: str) -> bool:
    try:
        datetime.fromisoformat(v)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class CheckResult:
    dataset: str
    check: str
    passed: bool
    severity: str      # critical (blocks publishing) | warning
    detail: str


def schema_checks(dataset: str, contract: dict, rows: list[dict]) -> list[CheckResult]:
    out = []
    columns = set().union(*(r.keys() for r in rows)) if rows else set()
    expected = set(contract["schema"])
    missing, extra = expected - columns, columns - expected
    out.append(CheckResult(dataset, "schema: expected columns present", not missing, "critical",
                           f"missing {sorted(missing)}" + (f"; unexpected {sorted(extra)}" if extra else "")
                           if missing else "all contract columns present"))
    for col, rule in contract["schema"].items():
        if col in missing:
            continue
        values = [r.get(col) for r in rows]
        non_null = [v for v in values if v is not None]
        null_pct = 100 * (len(values) - len(non_null)) / max(len(values), 1)
        limit = rule.get("max_null_pct", 0.0 if rule.get("required") else 100.0)
        if null_pct > limit:
            out.append(CheckResult(dataset, f"{col}: null rate", False, "critical",
                                   f"{null_pct:.1f}% nulls (contract allows {limit}%)"))
        bad_type = [v for v in non_null if not TYPE_CHECKS[rule["type"]](v)]
        if bad_type:
            out.append(CheckResult(dataset, f"{col}: type {rule['type']}", False, "critical",
                                   f"{len(bad_type)} values of the wrong type, e.g. {bad_type[0]!r}"))
        if rule.get("unique") and len(set(non_null)) != len(non_null):
            out.append(CheckResult(dataset, f"{col}: unique", False, "critical",
                                   f"{len(non_null) - len(set(non_null))} duplicates"))
        if "allowed" in rule:
            bad = {v for v in non_null if v not in rule["allowed"]}
            if bad:
                out.append(CheckResult(dataset, f"{col}: allowed values", False, "warning", f"unexpected {sorted(bad)}"))
        if "min" in rule or "max" in rule:
            nums = [v for v in non_null if TYPE_CHECKS["number"](v)]
            lo, hi = rule.get("min", float("-inf")), rule.get("max", float("inf"))
            out_of_range = [v for v in nums if not lo <= v <= hi]
            if out_of_range:
                out.append(CheckResult(dataset, f"{col}: range", False, "warning",
                                       f"{len(out_of_range)} values outside [{lo}, {hi}]"))
    return out


def freshness_check(dataset: str, contract: dict, last_loaded: datetime | None, now: datetime) -> CheckResult:
    if last_loaded is None:
        return CheckResult(dataset, "freshness", False, "critical", "never loaded")
    age_h = (now - last_loaded).total_seconds() / 3600
    sla = contract["freshness_sla_hours"]
    return CheckResult(dataset, "freshness", age_h <= sla, "critical",
                       f"newest load is {age_h:.0f}h old (SLA {sla}h)")


def volume_check(dataset: str, contract: dict, history: list[int], today: int | None) -> CheckResult:
    """Robust z-score of today's row count against the trailing loads (median and MAD, so one bad day can't
    distort the baseline)."""
    if today is None or len(history) < 7:
        return CheckResult(dataset, "volume", True, "warning", "not enough history")
    med = statistics.median(history)
    mad = statistics.median(abs(h - med) for h in history) or 1
    z = 0.6745 * (today - med) / mad
    limit = contract["volume"]["max_abs_z"]
    return CheckResult(dataset, "volume", abs(z) <= limit, "critical",
                       f"{today:,} rows vs typical {med:,.0f} (robust z = {z:+.1f}, limit ±{limit})")
