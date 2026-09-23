"""Regression checks for the reproducible, five-minute AML export."""

import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SCRIPT = ROOT / "run_pipeline.py"
LIMIT_SECONDS = 300
EXPECTED_EXPORTS = {
    "nodes_roles.csv",
    "clusters.csv",
    "top_nodes.csv",
    "metrics.parquet",
    "report.md",
}
RUNTIME_LINE = re.compile(r"(?m)^Время расчёта: [0-9]+(?:\.[0-9]+)? с$".encode())
GID_LITERAL = re.compile(r"(?<!\d)\d{18}(?!\d)")


def _stable_bytes(path):
    contents = path.read_bytes()
    if path.name == "report.md":
        contents, count = RUNTIME_LINE.subn("Время расчёта: <runtime> с".encode(), contents)
        if count != 1:
            raise AssertionError("report.md must contain exactly one runtime line")
    return contents


class PipelineTests(unittest.TestCase):
    def test_pipeline_finishes_within_five_minutes_and_is_deterministic(self):
        with tempfile.TemporaryDirectory(prefix="aml-pipeline-test-") as temp:
            export_dirs = [Path(temp) / "first", Path(temp) / "second"]
            for export_dir in export_dirs:
                started = time.monotonic()
                try:
                    result = subprocess.run(
                        [sys.executable, str(SCRIPT), "--data", str(DATA), "--out", str(export_dir)],
                        cwd=ROOT,
                        capture_output=True,
                        text=True,
                        timeout=LIMIT_SECONDS,
                        check=False,
                    )
                except subprocess.TimeoutExpired as exc:
                    self.fail(f"pipeline exceeded {LIMIT_SECONDS} seconds: {exc}")
                elapsed = time.monotonic() - started
                self.assertEqual(result.returncode, 0, f"{result.stdout}\n{result.stderr}")
                self.assertLess(elapsed, LIMIT_SECONDS, f"pipeline took {elapsed:.1f} seconds")

            first_files = {p.relative_to(export_dirs[0]) for p in export_dirs[0].rglob("*") if p.is_file()}
            second_files = {p.relative_to(export_dirs[1]) for p in export_dirs[1].rglob("*") if p.is_file()}
            self.assertTrue(EXPECTED_EXPORTS.issubset({str(p) for p in first_files}))
            self.assertEqual(first_files, second_files, "successive runs produced different file sets")
            for name in sorted(first_files):
                with self.subTest(export=str(name)):
                    self.assertEqual(
                        _stable_bytes(export_dirs[0] / name),
                        _stable_bytes(export_dirs[1] / name),
                        f"{name} differs between successive runs",
                    )

    def test_pipeline_contains_no_hardcoded_18_digit_gid(self):
        offenders = []
        for path in sorted((ROOT / "pipeline").rglob("*.py")):
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if GID_LITERAL.search(line):
                    offenders.append(f"{path.relative_to(ROOT)}:{line_number}")
        self.assertFalse(offenders, "18-digit literal(s) found: " + ", ".join(offenders))


if __name__ == "__main__":
    unittest.main()
