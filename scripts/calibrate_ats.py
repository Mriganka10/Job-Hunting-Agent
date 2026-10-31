from __future__ import annotations

import argparse
import json
from pathlib import Path

from job_hunting_agent.ats_calibration import load_calibration_manifest, run_calibration_benchmark, run_calibration_cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the role-diverse ATS calibration benchmark.")
    parser.add_argument("--output", type=Path, help="Optional path for the full JSON result.")
    parser.add_argument("--manifest", type=Path, help="Optional JSON manifest of consented private resumes and expected score bands.")
    parser.add_argument("--min-coverage", type=float, default=0.0, help="Fail (exit 1) if band coverage is below this, e.g. 0.95.")
    parser.add_argument("--max-mae", type=float, default=100.0, help="Fail (exit 1) if mean absolute error is above this, e.g. 4.")
    args = parser.parse_args()
    result = run_calibration_cases(load_calibration_manifest(args.manifest)) if args.manifest else run_calibration_benchmark()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    summary = {key: value for key, value in result.items() if key != "results"}
    print(json.dumps(summary, indent=2))
    failed = float(result["band_coverage"]) < args.min_coverage or float(result["mean_absolute_error"]) > args.max_mae
    print("ATS calibration gate:", "FAIL" if failed else "PASS")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
