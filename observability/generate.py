"""Thirty days of daily loads for three sources, with four incidents planted on the last day.

Day 30 incidents:
1. raw.payments: the upstream team renamed `amount_gbp` to `amount` (breaking schema change).
2. raw.orders: volume drops ~60% (partial upstream outage).
3. raw.orders: 8% of rows arrive without a customer_id.
4. raw.customers: the daily load did not run, so the newest data is 31 hours old.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

START = datetime(2026, 10, 1, 2, 0)
DAYS = 30


def _orders(rng, day, n, null_pct=0.0):
    rows = []
    for i in range(n):
        rows.append({"order_id": f"o{day:02d}{i:05d}",
                     "customer_id": None if rng.random() < null_pct else f"c{rng.randint(1, 5000)}",
                     "order_ts": (START + timedelta(days=day, minutes=rng.randint(0, 1439))).isoformat(),
                     "status": rng.choice(["placed", "paid", "shipped", "cancelled"]),
                     "amount_gbp": round(rng.uniform(5, 400), 2)})
    return rows


def _payments(rng, orders, rename=False):
    key = "amount" if rename else "amount_gbp"
    return [{"payment_id": f"p{o['order_id'][1:]}", "order_id": o["order_id"],
             "method": rng.choice(["card", "paypal", "apple_pay"]), key: o["amount_gbp"],
             "captured_ts": o["order_ts"]} for o in orders if o["status"] != "cancelled"]


def _customers(rng, day, n):
    return [{"customer_id": f"c{day:02d}{i:04d}", "country": rng.choice(["UK", "IE", "PT", "ES", "DE"]),
             "segment": rng.choice(["consumer", "business"]),
             "created_ts": (START + timedelta(days=day, minutes=rng.randint(0, 1439))).isoformat()} for i in range(n)]


def _tickets(rng, day, n):
    return [{"ticket_id": f"t{day:02d}{i:04d}", "priority": rng.choice(["low", "medium", "high"]),
             "created_ts": (START + timedelta(days=day, minutes=rng.randint(0, 1439))).isoformat()} for i in range(n)]


def generate(out_dir: str | Path, seed: int = 8) -> Path:
    rng = random.Random(seed)
    out = Path(out_dir)
    loads = []  # load log: dataset, day, loaded_at, file
    for day in range(DAYS):
        last = day == DAYS - 1
        n_orders = int(rng.gauss(2000, 80) * (0.4 if last else 1))
        orders = _orders(rng, day, n_orders, null_pct=0.08 if last else 0.001)
        payments = _payments(rng, orders, rename=last)
        batches = {"raw.orders": orders, "raw.payments": payments,
                   "raw.tickets": _tickets(rng, day, int(rng.gauss(600, 30)))}
        if not last:  # the customers load fails on the last day
            batches["raw.customers"] = _customers(rng, day, int(rng.gauss(150, 12)))
        for dataset, rows in batches.items():
            path = out / dataset / f"day={day:02d}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            loads.append({"dataset": dataset, "day": day, "rows": len(rows),
                          "loaded_at": (START + timedelta(days=day, hours=1)).isoformat(), "file": str(path)})
    (out / "load_log.json").write_text(json.dumps(loads, indent=1), encoding="utf-8")
    (out / "run_time.txt").write_text((START + timedelta(days=DAYS - 1, hours=3)).isoformat(), encoding="utf-8")
    return out
