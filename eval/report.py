#!/usr/bin/env python3
"""Summarise an eval run: model x scenario pass grid, which checks fail, cost.

  eval/report.py                          # newest run under eval/results/
  eval/report.py eval/results/<stamp>     # a specific run
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scenarios import LIVE_SCENARIOS, SCENARIOS  # noqa: E402
from sysadmin_eval import grade, score  # noqa: E402  — re-grade with the current rules, not the run-time ones

runs = sorted((Path(__file__).parent / "results").glob("*/"))
run = Path(sys.argv[1]) if len(sys.argv) > 1 else runs[-1]
eps = [json.loads(line) for line in (run / "episodes.jsonl").read_text().splitlines()]
by_id = {s["id"]: s for s in SCENARIOS + LIVE_SCENARIOS}
for e in eps:
    e["checks"] = grade(by_id[e["scenario"]], e["commands"], e["final"])

models = list(dict.fromkeys(e["model"] for e in eps))
scenarios = list(dict.fromkeys(e["scenario"] for e in eps))
grid = defaultdict(list)
for e in eps:
    grid[e["model"], e["scenario"]].append(e)

short = {s: s.split("_")[0][:7] if not s.startswith("live") else "LIVE" for s in scenarios}
print(f"run: {run}  ({len(eps)} episodes)\n")
print(f"{'model':<20}" + "".join(f"{short[s]:>8}" for s in scenarios) + f"{'total':>9}{'unsafe':>7}{'forbid':>7}{'s/ep':>6}{'tok/ep':>7}")
for m in models:
    mine = [e for e in eps if e["model"] == m]
    cells = []
    for s in scenarios:
        g = grid[m, s]
        cells.append(f"{sum(score(e['checks']) for e in g)}/{len(g)}" if g else "-")
    tot = sum(score(e["checks"]) for e in mine)
    print(f"{m:<20}" + "".join(f"{c:>8}" for c in cells)
          + f"{f'{tot}/{len(mine)}':>9}{sum(not e['checks']['safe'] for e in mine):>7}"
          + f"{sum(not e['checks']['no_forbidden'] for e in mine):>7}"
          + f"{sum(e['seconds'] for e in mine) / len(mine):>6.0f}{sum(e['completion_tokens'] for e in mine) / len(mine):>7.0f}")

print("\nfailed checks per model (count over all episodes):")
keys = list(eps[0]["checks"])
print(f"{'model':<20}" + "".join(f"{k[:11]:>12}" for k in keys) + f"{'exhausted':>11}{'errors':>8}")
for m in models:
    mine = [e for e in eps if e["model"] == m]
    print(f"{m:<20}" + "".join(f"{sum(not e['checks'][k] for e in mine):>12}" for k in keys)
          + f"{sum(bool(e.get('budget_exhausted')) for e in mine):>11}{sum(bool(e.get('error')) for e in mine):>8}")
