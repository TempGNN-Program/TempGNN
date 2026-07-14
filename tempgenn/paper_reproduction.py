from __future__ import annotations

import csv
import math
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List


DATASETS = ["WK", "MC", "RT", "LM", "WT", "GT"]
MODELS = ["JODIE", "TGN", "TGAT", "APAN"]
REFERENCE_INPUTS = Path(__file__).resolve().parents[1] / "reference_inputs" / "paper_figure_values.csv"

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
        toolchain="Xilinx Vitis 2023.2 for the packaged AE path; paper target 225 MHz",
        reproduction_status=(
            "The repository supplies a bounded Q10 forward-path implementation, XRT host, build flow, "
            "and fresh U280 measurement harness. It is not the complete paper implementation."
        ),
        key_settings="8-dimensional Q10 diagnostic path; batch-size-1000 real-stream prefixes in the U280 workflow",
        notes="Paper reference figures and fresh U280 diagnostic measurements are stored in separate directories.",
    ),
    PlatformNote(
        name="MATG",
        platform="Xilinx Alveo U280",
        toolchain="Independent Vitis-HLS 2023.2 reproduction informed by the MATG paper",
        reproduction_status=(
            "Independent bounded implementation of the documented MATG-style pruning and LUT time-encoding "
            "mechanisms; freshly runnable on U280, but not the authors' complete stack or a paper-equivalent rerun."
        ),
        key_settings="bounded degree scan, neighbor pruning, LUT time encoding, fixed-point forward path",
        notes="Its measured rows are generated only by the fresh U280 workflow, never copied into reference figures.",
    ),
    PlatformNote(
        name="ViTeGNN",
        platform="Xilinx Alveo U280",
        toolchain="Independent Vitis-HLS 2023.2 reproduction informed by the ViTeGNN paper",
        reproduction_status=(
            "Independent bounded implementation of documented lightweight-attention and retained-neighbor "
            "mechanisms; freshly runnable on U280, but not the authors' complete lat/bal/thpt stack."
        ),
        key_settings="four retained neighbors, lightweight attention, fixed-point forward path",
        notes="Its measured rows are generated only by the fresh U280 workflow, never copied into reference figures.",
    ),
    PlatformNote(
        name="RTGA",
        platform="Xilinx Alveo U280",
        toolchain="Independent Vitis-HLS 2023.2 reproduction informed by the RTGA paper",
        reproduction_status=(
            "Independent bounded implementation of documented temporal-tree scheduling and temporal-aware "
            "caching mechanisms; freshly runnable on U280, but not the authors' complete stack."
        ),
        key_settings="temporal-tree traversal, redundancy-aware selection, temporal-aware cache, fixed-point path",
        notes="Its measured rows are generated only by the fresh U280 workflow, never copied into reference figures.",
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


def _figure_rows(figure_id: str) -> List[Dict[str, object]]:
    if figure_id not in FIGURE_IDS:
        raise ValueError(f"unknown paper figure id: {figure_id}")
    return [dict(row) for row in _reference_rows() if row["figure"] == figure_id]


@lru_cache(maxsize=1)
def _reference_rows() -> tuple[Dict[str, object], ...]:
    if not REFERENCE_INPUTS.is_file():
        raise FileNotFoundError(f"paper reference input is missing: {REFERENCE_INPUTS}")

    parsed: list[Dict[str, object]] = []
    with REFERENCE_INPUTS.open(newline="", encoding="utf-8") as handle:
        for line_number, raw in enumerate(csv.DictReader(handle), start=2):
            figure = raw.get("figure", "")
            if figure not in FIGURE_IDS:
                raise ValueError(f"{REFERENCE_INPUTS}:{line_number}: unknown figure {figure!r}")
            if raw.get("source_kind") not in {"exact_workbook_value", "vector_geometry_digitization"}:
                raise ValueError(f"{REFERENCE_INPUTS}:{line_number}: invalid source kind")

            value = float(raw["value"])
            if not math.isfinite(value):
                raise ValueError(f"{REFERENCE_INPUTS}:{line_number}: non-finite value")

            row: Dict[str, object] = dict(raw)
            row["value"] = value
            x_value = raw.get("x", "")
            if x_value != "":
                parsed_x = float(x_value)
                row["x"] = int(parsed_x) if parsed_x.is_integer() else parsed_x
            else:
                row.pop("x", None)
            parsed.append(row)

    present = {str(row["figure"]) for row in parsed}
    if present != FIGURE_IDS:
        missing = sorted(FIGURE_IDS - present)
        raise ValueError(f"paper reference input is incomplete; missing figures: {missing}")
    return tuple(parsed)
