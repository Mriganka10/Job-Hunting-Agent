"""Print job-recommendation quality on the labelled corpus.

Usage:
    python scripts/evaluate_job_relevance.py            # table
    python scripts/evaluate_job_relevance.py --json     # machine-readable

Exits with status 1 when a quality gate fails, so it can gate a deployment.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from job_hunting_agent.relevance_eval import evaluate_all  # noqa: E402

GATES = {"macro_precision": 0.95, "macro_recall": 0.9, "macro_ndcg_at_10": 0.9}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = parser.parse_args()
    report = evaluate_all()
    failures = [name for name, minimum in GATES.items() if float(report[name]) < minimum]
    if report["total_leaks"]:
        failures.append("total_leaks")
    if args.json:
        print(json.dumps({**report, "profiles": [asdict(item) for item in report["profiles"]], "failed_gates": failures}, indent=2))
    else:
        print(f"{'profile':28} {'precision':>9} {'recall':>7} {'nDCG@10':>8}  leaks / missed")
        for item in report["profiles"]:
            print(f"{item.key:28} {item.precision:9.2f} {item.recall:7.2f} {item.ndcg_at_10:8.2f}  {list(item.leaks) or '-'} / {list(item.missed) or '-'}")
        print(f"\nmacro precision {report['macro_precision']:.3f} | recall {report['macro_recall']:.3f} | "
              f"nDCG@10 {report['macro_ndcg_at_10']:.3f} | leaks {report['total_leaks']}")
        print("PASS" if not failures else f"FAIL: {', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
