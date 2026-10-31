"""Run every code-reading MCQ and check its answer key against real output.

Usage: python scripts/verify_code_questions.py
Exit code 1 if any answer key disagrees with the interpreter/compiler.
Runtimes that are not installed are skipped (reported as such).
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from job_hunting_agent.mock_test_code_bank import CODE_TOPICS  # noqa: E402


def run(language: str, code: str, setup: str = "") -> str | None:
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        if language == "python":
            path = folder / "main.py"
            path.write_text(code, encoding="utf-8")
            return _exec([sys.executable, "-I", str(path)], folder)
        if language == "javascript":
            if not shutil.which("node"):
                return None
            path = folder / "main.js"
            path.write_text(code, encoding="utf-8")
            return _exec(["node", str(path)], folder)
        if language == "java":
            if not (shutil.which("javac") and shutil.which("java")):
                return None
            (folder / "Main.java").write_text(code, encoding="utf-8")
            _exec(["javac", "Main.java"], folder)
            return _exec(["java", "-cp", str(folder), "Main"], folder)
        if language == "cpp":
            if not shutil.which("g++"):
                return None
            (folder / "main.cpp").write_text(code, encoding="utf-8")
            _exec(["g++", "-std=c++17", "-O0", "-o", "main", "main.cpp"], folder)
            return _exec([str(folder / "main")], folder)
        if language == "sql":
            conn = sqlite3.connect(":memory:")
            conn.executescript(setup)
            rows = conn.execute(code).fetchall()
            return "\n".join("|".join("" if value is None else str(value) for value in row) for row in rows)
    raise ValueError(language)


def _exec(command: list[str], cwd: Path) -> str:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-500:])
    return result.stdout


def verify() -> tuple[int, int, list[str]]:
    checked = skipped = 0
    failures: list[str] = []
    for topic, data in CODE_TOPICS.items():
        for item in data["questions"]:
            mode = item.get("verify", "stdout")
            if mode == "none":
                continue
            if mode == "pandas":
                try:
                    import pandas  # noqa: F401
                except ImportError:
                    skipped += 1
                    continue
            output = run(data["language"], item["code"], data.get("setup", ""))
            if output is None:
                skipped += 1
                continue
            checked += 1
            expected = item["options"][item["answer"]]
            if output.strip() != expected.strip():
                failures.append(f"[{topic}] {item['prompt']}\n{item['code'][:120]}\n  key: {expected!r}\n  real: {output.strip()!r}")
    return checked, skipped, failures


if __name__ == "__main__":
    checked, skipped, failures = verify()
    print(f"checked {checked}, skipped {skipped} (runtime not installed), failures {len(failures)}")
    for failure in failures:
        print(failure)
    sys.exit(1 if failures else 0)
