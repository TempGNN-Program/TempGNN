from __future__ import annotations

import csv
import unittest

import tempgenn.paper_reproduction as paper


class PaperReferenceDataTests(unittest.TestCase):
    def test_reference_table_is_complete_and_source_labeled(self) -> None:
        with paper.reference_input_path().open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        self.assertEqual(668, len(rows))
        self.assertEqual(paper.FIGURE_IDS, {row["figure"] for row in rows})
        self.assertEqual(
            {"exact_workbook_value", "vector_geometry_digitization"},
            {row["source_kind"] for row in rows},
        )
        self.assertNotIn("nan", {row["value"].lower() for row in rows})
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


if __name__ == "__main__":
    unittest.main()
