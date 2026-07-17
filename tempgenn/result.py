"""Load the CSV data used to generate TempGNN result figures."""

from __future__ import annotations

import csv
from pathlib import Path


RESULT_CSV = Path(__file__).resolve().parents[1] / "results" / "result.csv"
RESULT_RECORD_COUNT = 668
RESULT_CSV_SHA256 = "b92cafe211f9f001f097898b1aae59c3c132ed6e9956176394fd14c034b3d147"


def _load_result_csv() -> tuple[dict[str, str], ...]:
    with RESULT_CSV.open(newline="", encoding="utf-8") as handle:
        return tuple(csv.DictReader(handle))


TempGNN_data = _load_result_csv()
