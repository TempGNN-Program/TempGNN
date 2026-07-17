from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.make_ae_report import inventory_document, latest_run, summary_document


class MakeAeReportTests(unittest.TestCase):
    def test_latest_run_uses_provenance_time_instead_of_directory_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runs = Path(temporary)
            smoke = self.write_run(
                runs / "pap142_u280_smoke_20260715T052052Z",
                created_utc="2026-07-15T05:30:09+00:00",
                repetitions=1,
            )
            measured = self.write_run(
                runs / "pap142_u280_measured_20260715T052052Z",
                created_utc="2026-07-15T05:52:26+00:00",
                repetitions=3,
            )

            self.assertGreater(smoke.name, measured.name)
            self.assertEqual(latest_run(runs), measured)
            state = {
                "averages": {},
                "board": None,
                "build": None,
                "run": Path("results/reviewer_u280_runs/final"),
                "verification": {},
                "provenance": {},
            }
            self.assertIn("results/reviewer_u280_runs/final", summary_document(state))
            self.assertIn("results/reviewer_u280_runs/final", inventory_document(state))

    @staticmethod
    def write_run(path: Path, *, created_utc: str, repetitions: int) -> Path:
        path.mkdir()
        (path / "provenance.json").write_text(
            json.dumps({"created_utc": created_utc, "repetitions": repetitions}),
            encoding="utf-8",
        )
        (path / "verification.json").write_text("{}\n", encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()
