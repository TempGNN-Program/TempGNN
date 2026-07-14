from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from scripts.reproduce_paper_figures import _write_grouped_bar_svg


DATASETS = ["WK", "MC", "RT", "LM", "WT", "GT"]
MODELS = ["JODIE", "TGN", "TGAT", "APAN"]
U280_CORE_SOLUTIONS = ["MATG", "ViTeGNN", "RTGA", "TempGNN"]


def derive_u280_core(baselines_root: Path, out_dir: Path) -> dict[str, Path]:
    """Derive the FPGA-only core comparison from a fresh U280 reviewer run."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tempgnn_rows = load_rows(baselines_root / "raw_tempgnn_u280.csv")
    baseline_rows = []
    for name in ["MATG", "ViTeGNN", "RTGA"]:
        baseline_rows.extend(load_rows(baselines_root / name / "raw_latency_power_energy.csv"))
    rows = baseline_rows + tempgnn_rows

    outputs = {
        "fig11_speedup_matg": out_dir / "fig11_speedup_matg.csv",
        "fig12_energy_tempgnn": out_dir / "fig12_energy_tempgnn.csv",
    }
    fig11 = derive_fig11(rows)
    fig12 = derive_fig12(rows, solutions=U280_CORE_SOLUTIONS)
    write_csv(outputs["fig11_speedup_matg"], fig11)
    write_csv(outputs["fig12_energy_tempgnn"], fig12)
    _write_grouped_bar_svg(
        out_dir / "fig11_speedup_matg.svg",
        fig11,
        U280_CORE_SOLUTIONS,
        "Fig.11 End-to-end speedup normalized to MATG (fresh U280 run)",
    )
    _write_grouped_bar_svg(
        out_dir / "fig12_energy_tempgnn.svg",
        fig12,
        U280_CORE_SOLUTIONS,
        "Fig.12 Energy normalized to TempGNN (fresh U280 subset)",
    )
    return outputs


def derive_fig11(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    by_key = index_rows(rows, "latency_ms")
    out = []
    for dataset in DATASETS:
        for model in MODELS:
            base = by_key[(dataset, model, "MATG")]
            for solution in U280_CORE_SOLUTIONS:
                value = base / by_key[(dataset, model, solution)]
                out.append(row("fig11_speedup_matg", dataset, model, solution, value))
    return with_averages(out)


def derive_fig12(
    rows: list[dict[str, str]],
    solutions: list[str] | tuple[str, ...] = U280_CORE_SOLUTIONS,
) -> list[dict[str, object]]:
    by_key = index_rows(rows, "energy_mj")
    out = []
    for dataset in DATASETS:
        for model in MODELS:
            base = by_key[(dataset, model, "TempGNN")]
            for solution in solutions:
                value = by_key[(dataset, model, solution)] / base
                out.append(row("fig12_energy_tempgnn", dataset, model, solution, value))
    return with_averages(out)


def index_rows(rows: Iterable[dict[str, str]], field: str) -> dict[tuple[str, str, str], float]:
    indexed = {}
    for item in rows:
        value = item.get(field, "")
        if value == "":
            continue
        indexed[(item["dataset"], item["model"], item["solution"])] = float(value)
    return indexed


def row(figure: str, dataset: str, model: str, solution: str, value: float) -> dict[str, object]:
    return {
        "dataset": dataset,
        "figure": figure,
        "model": model,
        "solution": solution,
        "value": round(value, 4),
    }


def with_averages(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[float]] = {}
    for item in rows:
        grouped.setdefault((str(item["figure"]), str(item["solution"])), []).append(float(item["value"]))
    output = list(rows)
    for (figure, solution), values in grouped.items():
        output.append(
            {
                "dataset": "AVG",
                "figure": figure,
                "model": "AVG",
                "solution": solution,
                "value": round(sum(values) / len(values), 4),
            }
        )
    return output


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = ["dataset", "figure", "model", "solution", "value"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
