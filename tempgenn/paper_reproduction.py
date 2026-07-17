from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from tempgenn.result import (
    RESULT_CSV,
    RESULT_RECORD_COUNT,
    TempGNN_data,
)


DATASETS = ["WK", "MC", "RT", "LM", "WT", "GT"]
MODELS = ["JODIE", "TGN", "TGAT", "APAN"]
REFERENCE_INPUTS = RESULT_CSV

FIGURE_IDS = {
    "fig2_execution_breakdown",
    "fig4a_branch_parallelism_ratio",
    "fig9b_gpu_overhead_breakdown",
    "fig10_speedup_tglite_cpu",
    "fig11_speedup_matg",
    "fig12_energy_tempgnn",
    "fig13_ablation_time",
    "fig14a_batch_sensitivity",
    "fig14b_tdp_entries",
}

REFERENCE_CSV_FIELDS = (
    "figure",
    "model",
    "dataset",
    "solution",
    "x",
    "value",
    "source_id",
    "source_kind",
    "source_locator",
    "source_sha256",
    "value_note",
)


@dataclass(frozen=True)
class PlatformNote:
    name: str
    platform: str
    toolchain: str
    reproduction_status: str
    key_settings: str
    notes: str


PLATFORM_NOTES = [
    PlatformNote(
        name="TempGNN",
        platform="Xilinx Alveo U280",
        toolchain="Xilinx Vitis 2023.2",
        reproduction_status="Runnable U280 implementation with XRT host and measurement workflow.",
        key_settings="Forward-path accelerator",
        notes="Run with make ae-core-u280.",
    ),
    PlatformNote(
        name="MATG",
        platform="Xilinx Alveo U280",
        toolchain="Independent Vitis-HLS 2023.2 reproduction informed by the MATG paper",
        reproduction_status="Independent paper-based U280 forward-path reproduction.",
        key_settings="Neighbor pruning and LUT time encoding",
        notes="Run with make ae-core-u280.",
    ),
    PlatformNote(
        name="ViTeGNN",
        platform="Xilinx Alveo U280",
        toolchain="Independent Vitis-HLS 2023.2 reproduction informed by the ViTeGNN paper",
        reproduction_status="Independent paper-based U280 forward-path reproduction.",
        key_settings="Lightweight attention and retained-neighbor processing",
        notes="Run with make ae-core-u280.",
    ),
    PlatformNote(
        name="RTGA",
        platform="Xilinx Alveo U280",
        toolchain="Independent Vitis-HLS 2023.2 reproduction informed by the RTGA paper",
        reproduction_status="Independent paper-based U280 forward-path reproduction.",
        key_settings="Temporal-tree scheduling and temporal-aware caching",
        notes="Run with make ae-core-u280.",
    ),
    PlatformNote(
        name="Cascade",
        platform="NVIDIA A100 GPU in the paper",
        toolchain="CUDA reference baseline",
        reproduction_status="Reference-figure input only; this repository does not execute Cascade on U280.",
        key_settings="dependency-aware GPU batching",
        notes="Cascade is not one of the fresh U280 xclbins.",
    ),
    PlatformNote(
        name="TGLite-CPU",
        platform="32-core Intel Xeon Platinum 8357B in the paper",
        toolchain="TGLite CPU reference baseline",
        reproduction_status="Reference-figure input only; this repository does not freshly execute TGLite-CPU.",
        key_settings="batch size 1000 and recent sampling in the paper configuration",
        notes="Reference-only plotting input.",
    ),
]


def figure2_rows() -> List[Dict[str, object]]:
    return _figure_rows("fig2_execution_breakdown")


def figure4a_rows() -> List[Dict[str, object]]:
    return _figure_rows("fig4a_branch_parallelism_ratio")


def figure9b_rows() -> List[Dict[str, object]]:
    return _figure_rows("fig9b_gpu_overhead_breakdown")


def figure10_rows() -> List[Dict[str, object]]:
    return _figure_rows("fig10_speedup_tglite_cpu")


def figure11_rows() -> List[Dict[str, object]]:
    return _figure_rows("fig11_speedup_matg")


def figure12_rows() -> List[Dict[str, object]]:
    return _figure_rows("fig12_energy_tempgnn")


def figure13_rows() -> List[Dict[str, object]]:
    return _figure_rows("fig13_ablation_time")


def figure14_batch_rows() -> List[Dict[str, object]]:
    return _figure_rows("fig14a_batch_sensitivity")


def figure14_sync_rows() -> List[Dict[str, object]]:
    return _figure_rows("fig14b_tdp_entries")


def platform_notes_as_dicts() -> List[Dict[str, str]]:
    return [asdict(note) for note in PLATFORM_NOTES]


def reference_input_path() -> Path:
    return REFERENCE_INPUTS


def reference_rows() -> List[Dict[str, object]]:
    return [dict(row) for row in _reference_rows()]


def reference_csv_bytes() -> bytes:
    return REFERENCE_INPUTS.read_bytes()


def reference_csv_sha256() -> str:
    return hashlib.sha256(reference_csv_bytes()).hexdigest()


def _figure_rows(figure_id: str) -> List[Dict[str, object]]:
    if figure_id not in FIGURE_IDS:
        raise ValueError(f"unknown paper figure id: {figure_id}")
    return [dict(row) for row in _reference_rows() if row["figure"] == figure_id]


@lru_cache(maxsize=1)
def _reference_rows() -> tuple[Dict[str, object], ...]:
    if len(TempGNN_data) != RESULT_RECORD_COUNT:
        raise ValueError(
            "result.csv is incomplete: "
            f"{len(TempGNN_data)} != {RESULT_RECORD_COUNT}"
        )
    parsed: list[Dict[str, object]] = []
    for row_number, raw in enumerate(TempGNN_data, start=1):
        figure = raw["figure"]
        value = float(raw["value"])
        if figure not in FIGURE_IDS:
            raise ValueError(f"result.csv row {row_number}: unknown figure {figure!r}")
        source_kind = raw["source_kind"]
        if source_kind not in {"exact_workbook_value", "vector_geometry_digitization"}:
            raise ValueError(f"result.csv row {row_number}: invalid source kind")
        if not math.isfinite(value):
            raise ValueError(f"result.csv row {row_number}: non-finite value")

        row: Dict[str, object] = {
            "figure": figure,
            "model": raw["model"],
            "dataset": raw["dataset"],
            "solution": raw["solution"],
            "value": value,
            "source_id": raw["source_id"],
            "source_kind": source_kind,
            "source_locator": raw["source_locator"],
            "source_sha256": raw["source_sha256"],
            "value_note": raw["value_note"],
        }
        if raw["x"]:
            x_value = float(raw["x"])
            row["x"] = int(x_value) if x_value.is_integer() else x_value
        parsed.append(row)

    present = {str(row["figure"]) for row in parsed}
    if present != FIGURE_IDS:
        missing = sorted(FIGURE_IDS - present)
        raise ValueError(f"paper reference input is incomplete; missing figures: {missing}")
    return tuple(parsed)
