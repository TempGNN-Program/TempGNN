from __future__ import annotations

import hashlib
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import scripts.reproduce_paper_figures as figure_script
import tempgenn.paper_reproduction as paper
from tempgenn.result import RESULT_CSV_SHA256


class ResultDataTests(unittest.TestCase):
    def test_reference_table_is_complete_and_source_labeled(self) -> None:
        rows = paper.reference_rows()

        self.assertEqual(668, len(rows))
        self.assertEqual(paper.FIGURE_IDS, {row["figure"] for row in rows})
        self.assertEqual(
            {"exact_workbook_value", "vector_geometry_digitization"},
            {row["source_kind"] for row in rows},
        )
        self.assertTrue(all(isinstance(row["value"], float) for row in rows))
        self.assertEqual("result.csv", paper.reference_input_path().name)
        self.assertEqual(64, len(RESULT_CSV_SHA256))
        self.assertEqual(RESULT_CSV_SHA256, paper.reference_csv_sha256())
        self.assertFalse(hasattr(paper, "_scaled_grid"))

    def test_figure10_uses_exact_workbook_blocks(self) -> None:
        values = {
            (row["model"], row["dataset"], row["solution"]): row["value"]
            for row in paper.figure10_rows()
        }
        self.assertEqual(128.4, values[("JODIE", "WK", "TempGNN")])
        self.assertEqual(130.5, values[("TGAT", "WK", "TempGNN")])
        self.assertEqual(115.6, values[("APAN", "WK", "TempGNN")])
        self.assertEqual(132.8, values[("AVG", "AVG", "TempGNN")])

    def test_reference_averages_are_explicit_source_rows(self) -> None:
        fig11 = {
            row["solution"]: row
            for row in paper.figure11_rows()
            if row["model"] == "AVG" and row["dataset"] == "AVG"
        }
        self.assertEqual(7.7889, fig11["TempGNN"]["value"])
        self.assertEqual("vector_geometry_digitization", fig11["TempGNN"]["source_kind"])

        fig13 = {
            row["solution"]: row["value"]
            for row in paper.figure13_rows()
            if row["model"] == "AVG" and row["dataset"] == "AVG"
        }
        self.assertEqual({"TempGNN": 1.0, "WO/DDTC": 3.08, "WO/OATS": 1.77}, fig13)

    def test_sensitivity_series_are_not_collapsed(self) -> None:
        fig14a = paper.figure14_batch_rows()
        self.assertEqual({"MATG", "ViTeGNN", "RTGA", "TempGNN"}, {row["solution"] for row in fig14a})
        self.assertEqual(20, len(fig14a))
        self.assertEqual(42, len(paper.figure14_sync_rows()))

    def test_ae_package_includes_regenerable_paper_outputs(self) -> None:
        root = Path(__file__).resolve().parents[1]
        package_script = (root / "scripts" / "package_ae.sh").read_text(encoding="utf-8")
        self.assertIn("  results/paper_reproduction\n", package_script)
        self.assertIn("required_paper_outputs=(", package_script)
        self.assertNotIn("  results/q14_real_tgl_edges\n", package_script)
        self.assertTrue((root / "results" / "result.csv").is_file())
        self.assertTrue((root / "tempgenn" / "result.py").is_file())
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "paper_reproduction"
            with mock.patch.object(figure_script, "OUT_DIR", output):
                figure_script.main()
            generated = output / "all_figure_data.csv"
            self.assertTrue(generated.is_file())
            self.assertEqual(
                RESULT_CSV_SHA256,
                hashlib.sha256((root / "results" / "result.csv").read_bytes()).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
