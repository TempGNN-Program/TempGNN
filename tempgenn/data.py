from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from .graph import TemporalGraph


SRC_CANDIDATES = ("src", "source", "u", "from", "user", "user_id")
DST_CANDIDATES = ("dst", "destination", "v", "to", "item", "item_id")
TIME_CANDIDATES = ("ts", "time", "timestamp", "t")


def load_temporal_csv(
    path: str | Path,
    src_column: Optional[str] = None,
    dst_column: Optional[str] = None,
    time_column: Optional[str] = None,
    limit: Optional[int] = None,
) -> TemporalGraph:
    path = Path(path)
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV must include a header row")

        src_column = src_column or _infer_column(reader.fieldnames, SRC_CANDIDATES, "source")
        dst_column = dst_column or _infer_column(reader.fieldnames, DST_CANDIDATES, "destination")
        time_column = time_column or _infer_column(reader.fieldnames, TIME_CANDIDATES, "timestamp")

        events: List[Tuple[int, int, float]] = []
        for row_idx, row in enumerate(reader):
            if limit is not None and row_idx >= limit:
                break
            events.append(
                (
                    _parse_vertex(row[src_column]),
                    _parse_vertex(row[dst_column]),
                    float(row[time_column]),
                )
            )

    return TemporalGraph(events)


def _infer_column(fieldnames: Sequence[str], candidates: Iterable[str], role: str) -> str:
    lower_to_original = {name.lower(): name for name in fieldnames}
    for candidate in candidates:
        if candidate in lower_to_original:
            return lower_to_original[candidate]
    raise ValueError(
        f"Could not infer {role} column. Available columns: {', '.join(fieldnames)}"
    )


def _parse_vertex(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        try:
            numeric = float(value)
        except ValueError:
            return abs(hash(value)) % (2**31)
        if numeric.is_integer():
            return int(numeric)
        return abs(hash(value)) % (2**31)
