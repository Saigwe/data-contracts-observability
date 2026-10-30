# 3-minute walkthrough: Data Contracts & Observability

A timed script for a Loom recording of about 3 minutes (screen plus camera bubble, 1080p). Say it in your own words; the lines are a guide, not a teleprompter.

**Open these tabs before you press record:** README, `contracts/`, `observability/checks.py`, `lineage.yml`, `observability/lineage.py`, `output/incident_report.md`, `output/data_health_status.md`, `tests/test_observability.py`, GitHub Actions.

| Time | On screen | What to say |
|---|---|---|
| 0:00–0:20 | Portfolio card, then the README headline | The worst way to find a broken pipeline is a director asking why the revenue number looks wrong. Here, four upstream breakages on one morning were caught before reaching the board's dashboard. |
| 0:20–0:45 | `contracts/` YAML | Each dataset has a contract agreed with its source team: schema, quality rules, a freshness SLA and normal volume. It lives in git and changes through pull requests. |
| 0:45–1:10 | README incidents table | Four problems planted in simulated loads: a renamed column, a partial outage with 60% of orders missing, 6% of orders with no customer, and a daily load that never ran. |
| 1:10–1:35 | `observability/checks.py` | Each is caught by a different check. Volume uses the median and median absolute deviation of the last 14 loads, so one bad day can't redefine normal; the outage scores a robust z of minus 10. Critical failures block; warnings only alert. |
| 1:35–2:00 | `lineage.yml` and `lineage.py` | Lineage maps sources to models to dashboards. A circuit breaker stops only the affected models publishing, so the healthy Support SLA dashboard keeps running. |
| 2:00–2:25 | `output/incident_report.md` | Engineers get every failure with its owner, severity and first runbook step, and the blast radius by dashboard tier, tier one first so the CFO hears first. |
| 2:25–2:45 | `output/data_health_status.md` | Leadership gets plain English: three of four reports on hold, and confirmation that no incorrect figures were published. It also writes OpenLineage events for tools like DataHub. |
| 2:45–3:00 | `tests/`, then the README top | Six tests, including that every planted incident is found and the breaker blocks only what's affected. Links are under the video. |

## Recording checklist
- Close email, chat and notifications. Zoom the browser to 125% so code is readable.
- Run `python -m observability.run` once before recording so the outputs are fresh.
- Keep to one take per section; Loom lets you trim. Aim for 2:45 to 3:10.
- Show real numbers on screen as you say them; never estimate on camera.
- Say "simulated data with planted problems" when you introduce it. This is a skills demonstration, not a rebuild of client work.

## After recording
1. Copy the Loom share link.
2. In `README.md`, replace the walkthrough line with `- [x] [3-minute Loom walkthrough](<your Loom link>)` and add the link under the title.
3. Add the link to this project's card on saigwe.github.io.
