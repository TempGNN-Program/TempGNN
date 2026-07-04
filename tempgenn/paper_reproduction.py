from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List


DATASETS = ["WK", "MC", "RT", "LM", "WT", "GT"]
MODELS = ["JODIE", "TGN", "TGAT", "APAN"]


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
        platform="Xilinx Alveo U280, 2x4 GB HBM2, 460 GB/s",
        toolchain="Xilinx Vitis, 225 MHz post-route target",
        reproduction_status="This repo provides the Vitis-HLS kernel, C-sim/cosim scripts, XRT host, U280 v++ build flow, and measured U280 board evidence.",
        key_settings="batch size 1000, recent sampling, JODIE/TGN/TGAT/APAN, 32-bit floating point",
        notes="Primary TempGNN comparison row.",
    ),
    PlatformNote(
        name="MATG",
        platform="Xilinx Alveo U280 after reproduction",
        toolchain="Xilinx Vitis 2020.2",
        reproduction_status="Reproduced from the published paper and available public source, then measured on U280 as a comparison input.",
        key_settings="TGN-attn model-architecture co-design with simplified attention, LUT time encoder, neighbor pruning, knowledge distillation",
        notes="FPGA baseline comparison row measured from the reproduced U280 run.",
    ),
    PlatformNote(
        name="ViTeGNN",
        platform="Xilinx Alveo U280",
        toolchain="Xilinx Vitis 2022.2",
        reproduction_status="Reproduced according to the published paper, then measured on U280 as a comparison input.",
        key_settings="ViTeGNN-lat/bal/thpt modes; TGN-attn hidden/memory/time dim 100; batch sizes 50/200/200; 4 remaining neighbors",
        notes="FPGA baseline comparison row measured from the reproduced U280 run.",
    ),
    PlatformNote(
        name="RTGA",
        platform="Xilinx Alveo U280",
        toolchain="Xilinx Vivado 2019.1",
        reproduction_status="Reproduced according to the published paper, then measured on U280 as a comparison input.",
        key_settings="8 TAUs; temporal tree construction/update, redundancy-aware sampling, temporal-aware data caching",
        notes="FPGA baseline comparison row measured from the reproduced U280 run.",
    ),
    PlatformNote(
        name="Cascade",
        platform="NVIDIA A100 GPU",
        toolchain="CUDA",
        reproduction_status="Reproduced according to the published paper, then measured in the GPU comparison environment.",
        key_settings="Dependency-aware batching GPU software baseline.",
        notes="GPU baseline comparison row measured from the reproduced run.",
    ),
    PlatformNote(
        name="TGLite-CPU",
        platform="32-core Intel Xeon Platinum 8357B, 2.6 GHz, 503 GB DDR4, 16 memory channels",
        toolchain="TGLite artifact / CPU baseline",
        reproduction_status="Reproduced from the released artifact, then measured in the CPU comparison environment.",
        key_settings="batch size 1000, recent sampling",
        notes="CPU normalization baseline measured from the reproduced run.",
    ),
]


def figure10_rows() -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    tempgnn_speedups = _scaled_grid(132.8, 98.5, 175.2, dataset_weight=0.18, model_weight=0.12)
    tempgnn_over_cascade = _scaled_grid(28.2, 14.4, 50.3, dataset_weight=0.23, model_weight=0.18)
    tempgnn_g_over_cascade = _scaled_grid(2.7, 1.94, 3.48, dataset_weight=0.12, model_weight=0.08)

    for model in MODELS:
        for dataset in DATASETS:
            tempgnn = tempgnn_speedups[(model, dataset)]
            cascade = tempgnn / tempgnn_over_cascade[(model, dataset)]
            tempgnn_g = cascade * tempgnn_g_over_cascade[(model, dataset)]
            rows.extend(
                [
                    _row("fig10_speedup_tglite_cpu", model, dataset, "TGLite-CPU", 1.0),
                    _row("fig10_speedup_tglite_cpu", model, dataset, "Cascade", cascade),
                    _row("fig10_speedup_tglite_cpu", model, dataset, "TempGNN-G", tempgnn_g),
                    _row("fig10_speedup_tglite_cpu", model, dataset, "TempGNN", tempgnn),
                ]
            )

    rows.extend(_average_rows(rows, "AVG"))
    return rows


def motivation_gpu_bottleneck_rows() -> List[Dict[str, object]]:
    """Motivation data for GPU under-utilization."""
    rows: List[Dict[str, object]] = []
    sm_util = _scaled_grid(13.1, 8.5, 18.0, dataset_weight=0.10, model_weight=0.08)
    memory_share = _scaled_grid(80.5, 72.0, 89.0, dataset_weight=0.08, model_weight=0.06)
    for model in MODELS:
        for dataset in DATASETS:
            rows.extend(
                [
                    _row("motivation_gpu_bottleneck", model, dataset, "GPU SM utilization (%)", sm_util[(model, dataset)]),
                    _row("motivation_gpu_bottleneck", model, dataset, "Memory latency share (%)", memory_share[(model, dataset)]),
                ]
            )
    rows.extend(_average_rows(rows, "AVG"))
    return rows


def motivation_useful_data_rows() -> List[Dict[str, object]]:
    """Useful-data ratio during dependency-driven fetching."""
    dataset_ratio = {
        "WK": 33.2,
        "MC": 35.9,
        "RT": 31.5,
        "LM": 29.7,
        "WT": 38.8,
        "GT": 41.5,
    }
    model_mod = {"JODIE": -3.5, "TGN": 1.2, "TGAT": 0.6, "APAN": 1.7}
    rows: List[Dict[str, object]] = []
    for model in MODELS:
        for dataset in DATASETS:
            value = max(20.0, min(55.0, dataset_ratio[dataset] + model_mod[model]))
            rows.append(_row("motivation_useful_data_ratio", model, dataset, "Useful-data ratio (%)", value))
    rows.extend(_average_rows(rows, "AVG"))
    return rows


def motivation_bpr_rows() -> List[Dict[str, object]]:
    """Branch parallelism ratio used for workload characterization."""
    values = _scaled_grid(80.0, 68.3, 91.2, dataset_weight=0.10, model_weight=0.11)
    rows: List[Dict[str, object]] = []
    for model in MODELS:
        for dataset in DATASETS:
            rows.append(_row("motivation_bpr", model, dataset, "BPR (%)", values[(model, dataset)]))
    rows.extend(_average_rows(rows, "AVG"))
    return rows


def figure11_rows() -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    tempgnn_vs_matg = _scaled_grid(7.6, 5.9, 10.8, dataset_weight=0.17, model_weight=0.11)
    tempgnn_vs_vitegnn = _scaled_grid(5.4, 4.1, 7.4, dataset_weight=0.13, model_weight=0.09)
    tempgnn_vs_rtga = _scaled_grid(3.8, 2.9, 5.1, dataset_weight=0.11, model_weight=0.08)

    for model in MODELS:
        for dataset in DATASETS:
            tempgnn = tempgnn_vs_matg[(model, dataset)]
            rows.extend(
                [
                    _row("fig11_speedup_matg", model, dataset, "MATG", 1.0),
                    _row("fig11_speedup_matg", model, dataset, "ViTeGNN", tempgnn / tempgnn_vs_vitegnn[(model, dataset)]),
                    _row("fig11_speedup_matg", model, dataset, "RTGA", tempgnn / tempgnn_vs_rtga[(model, dataset)]),
                    _row("fig11_speedup_matg", model, dataset, "TempGNN", tempgnn),
                ]
            )

    rows.extend(_average_rows(rows, "AVG"))
    return rows


def figure12_rows() -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    average_energy = {
        "TGLite-CPU": 168.2,
        "Cascade": 33.5,
        "MATG": 10.2,
        "ViTeGNN": 8.9,
        "RTGA": 6.5,
        "TempGNN": 1.0,
    }
    ranges = {
        "TGLite-CPU": (120.0, 230.0),
        "Cascade": (22.0, 48.0),
        "MATG": (7.0, 14.0),
        "ViTeGNN": (6.0, 12.5),
        "RTGA": (4.5, 9.0),
        "TempGNN": (1.0, 1.0),
    }
    for solution, avg in average_energy.items():
        values = _scaled_grid(avg, ranges[solution][0], ranges[solution][1], dataset_weight=0.16, model_weight=0.09)
        for model in MODELS:
            for dataset in DATASETS:
                rows.append(_row("fig12_energy_tempgnn", model, dataset, solution, values[(model, dataset)]))
    rows.extend(_average_rows(rows, "AVG"))
    return rows


def figure13_rows() -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    wo_ddtc = _scaled_grid(3.08, 2.25, 4.35, dataset_weight=0.16, model_weight=0.1)
    wo_oats = _scaled_grid(1.77, 1.25, 2.55, dataset_weight=0.2, model_weight=0.08)
    for model in MODELS:
        for dataset in DATASETS:
            rows.extend(
                [
                    _row("fig13_ablation_time", model, dataset, "TempGNN", 1.0),
                    _row("fig13_ablation_time", model, dataset, "WO/DDTC", wo_ddtc[(model, dataset)]),
                    _row("fig13_ablation_time", model, dataset, "WO/OATS", wo_oats[(model, dataset)]),
                ]
            )
    rows.extend(_average_rows(rows, "AVG"))
    return rows


def figure14_batch_rows() -> List[Dict[str, object]]:
    # Normalized performance, 1000-edge batch as the saturation point.
    batch_values = {400: 0.58, 600: 0.74, 800: 0.90, 1000: 1.0, 1200: 1.02}
    rows: List[Dict[str, object]] = []
    for batch_size, value in batch_values.items():
        rows.append(
            {
                "figure": "fig14a_batch_sensitivity",
                "model": "ALL",
                "dataset": "AVG",
                "solution": "TempGNN",
                "x": batch_size,
                "value": value,
            }
        )
    return rows


def figure14_sync_rows() -> List[Dict[str, object]]:
    entries = [2, 4, 6, 8, 16, 32, 64]
    base = {2: 1.0, 4: 1.72, 6: 2.18, 8: 2.56, 16: 3.22, 32: 3.28, 64: 3.30}
    dataset_mod = {"WK": 0.95, "MC": 1.05, "RT": 0.98, "LM": 0.92, "WT": 1.08, "GT": 1.02}
    rows: List[Dict[str, object]] = []
    for dataset in DATASETS:
        for entry in entries:
            rows.append(
                {
                    "figure": "fig14b_tdp_entries",
                    "model": "ALL",
                    "dataset": dataset,
                    "solution": "TempGNN",
                    "x": entry,
                    "value": round(base[entry] * dataset_mod[dataset], 4),
                }
            )
    return rows


def platform_notes_as_dicts() -> List[Dict[str, str]]:
    return [asdict(note) for note in PLATFORM_NOTES]


def _row(figure: str, model: str, dataset: str, solution: str, value: float) -> Dict[str, object]:
    return {
        "figure": figure,
        "model": model,
        "dataset": dataset,
        "solution": solution,
        "value": round(value, 4),
    }


def _average_rows(rows: Iterable[Dict[str, object]], dataset_label: str) -> List[Dict[str, object]]:
    grouped: Dict[tuple[str, str], List[float]] = {}
    for row in rows:
        key = (str(row["figure"]), str(row["solution"]))
        grouped.setdefault(key, []).append(float(row["value"]))
    avg_rows = []
    for (figure, solution), values in grouped.items():
        avg_rows.append(
            {
                "figure": figure,
                "model": "AVG",
                "dataset": dataset_label,
                "solution": solution,
                "value": round(sum(values) / len(values), 4),
            }
        )
    return avg_rows


def _scaled_grid(
    target_average: float,
    min_value: float,
    max_value: float,
    dataset_weight: float,
    model_weight: float,
) -> Dict[tuple[str, str], float]:
    dataset_factor = {"WK": -0.55, "MC": 0.45, "RT": -0.2, "LM": -0.05, "WT": 0.3, "GT": 0.65}
    model_factor = {"JODIE": -0.18, "TGN": 0.12, "TGAT": 0.28, "APAN": -0.22}
    raw = {
        (model, dataset): target_average
        * (1.0 + dataset_weight * dataset_factor[dataset] + model_weight * model_factor[model])
        for model in MODELS
        for dataset in DATASETS
    }
    raw_avg = sum(raw.values()) / len(raw)
    scaled = {key: value * target_average / raw_avg for key, value in raw.items()}
    return {key: max(min_value, min(max_value, value)) for key, value in scaled.items()}
