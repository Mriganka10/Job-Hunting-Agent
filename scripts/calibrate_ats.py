from __future__ import annotations

import argparse
import json
from pathlib import Path

from job_hunting_agent.ats_calibration import load_calibration_manifest, run_calibration_benchmark, run_calibration_cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the role-diverse ATS calibration benchmark.")
    parser.add_argument("--output", type=Path, help="Optional path for the full JSON result.")
    parser.add_argument("--manifest", type=Path, help="Optional JSON manifest of consented private resumes and expected score bands.")
    args = parser.parse_args()
    result = run_calibration_cases(load_calibration_manifest(args.manifest)) if args.manifest else run_calibration_benchmark()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    summary = {key: value for key, value in result.items() if key != "results"}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
