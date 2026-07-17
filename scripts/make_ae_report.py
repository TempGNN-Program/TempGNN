from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    state = collect_state(args)
    (args.out / "ae_summary.md").write_text(summary_document(state), encoding="utf-8")
    (args.out / "AE_README.md").write_text(quickstart_document(state), encoding="utf-8")
    (args.out / "AE_BRIDGE_CLAIMS.md").write_text(bridge_document(state), encoding="utf-8")
    (args.out / "FULL_PAPER_RESULTS.md").write_text(inventory_document(state), encoding="utf-8")
    (args.out / "U280_AE_RUNBOOK.md").write_text(runbook_document(state), encoding="utf-8")
    print(f"Wrote AE report to {args.out / 'ae_summary.md'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the reviewer-facing TempGNN AE report.")
    parser.add_argument("--paper-dir", type=Path, default=Path("results/paper_reproduction"))
    parser.add_argument(
        "--q14-summary",
        type=Path,
        default=Path("results/q14_real_tgl_edges/q14_dataset_model_summary.csv"),
    )
    parser.add_argument("--board-json", type=Path, default=Path("results/board_u280/summary.json"))
    parser.add_argument(
        "--build-provenance",
        type=Path,
        default=Path("artifacts/u280/TempGNN/evidence/build_provenance.json"),
    )
    parser.add_argument("--runs-dir", type=Path, default=Path("results/reviewer_u280_runs"))
    parser.add_argument("--out", type=Path, default=Path("results/ae_report"))
    return parser.parse_args()


def collect_state(args: argparse.Namespace) -> dict[str, object]:
    averages: dict[str, float] = {}
    figure_specs = [
        ("fig10_speedup_tglite_cpu.csv", "TempGNN", "tempgnn_vs_tglite"),
        ("fig10_speedup_tglite_cpu.csv", "TempGNN-G", "tempgnn_g_vs_tglite"),
        ("fig10_speedup_tglite_cpu.csv", "Cascade", "cascade_vs_tglite"),
        ("fig11_speedup_matg.csv", "TempGNN", "tempgnn_vs_matg"),
        ("fig12_energy_tempgnn.csv", "Cascade", "cascade_energy"),
        ("fig13_ablation_time.csv", "WO/DDTC", "wo_ddtc"),
        ("fig13_ablation_time.csv", "WO/OATS", "wo_oats"),
    ]
    for filename, solution, key in figure_specs:
        path = args.paper_dir / filename
        if path.is_file():
            averages[key] = average_solution(path, solution)

    board = None
    if args.board_json.is_file():
        board = json.loads(args.board_json.read_text(encoding="utf-8"))

    build = None
    if args.build_provenance.is_file():
        build = json.loads(args.build_provenance.read_text(encoding="utf-8"))

    q14_rows = read_csv(args.q14_summary) if args.q14_summary.is_file() else []
    run = latest_run(args.runs_dir)
    verification = None
    provenance = None
    fresh_summary: dict[str, object] = {}
    if run is not None:
        verification = json.loads((run / "verification.json").read_text(encoding="utf-8"))
        provenance = json.loads((run / "provenance.json").read_text(encoding="utf-8"))
        fresh_summary = collect_fresh_summary(run)
    return {
        "averages": averages,
        "board": board,
        "build": build,
        "q14_rows": q14_rows,
        "run": run,
        "verification": verification,
        "provenance": provenance,
        "fresh_summary": fresh_summary,
    }


def collect_fresh_summary(run: Path) -> dict[str, object]:
    systems: dict[str, dict[str, float | int]] = {}
    for system in ("TempGNN", "MATG", "ViTeGNN", "RTGA"):
        path = run / "raw" / system / "measurements.csv"
        if not path.is_file():
            continue
        rows = read_csv(path)
        bad = sum(
            row.get("golden_validation") != "PASS"
            or row.get("repeat_consistency") != "PASS"
            or row.get("timing_met") != "PASS"
            for row in rows
        )
        systems[system] = {
            "rows": len(rows),
            "bad": bad,
            "mean_latency_ms": mean(float(row["latency_ms"]) for row in rows),
        }

    speedup = None
    figure = run / "derived_comparison_figures" / "fig11_speedup_matg.csv"
    if figure.is_file():
        for row in read_csv(figure):
            if (
                row.get("dataset") == "AVG"
                and row.get("model") == "AVG"
                and row.get("solution") == "TempGNN"
            ):
                speedup = float(row["value"])
                break
    return {"systems": systems, "tempgnn_matg_speedup": speedup}


def latest_run(runs_dir: Path) -> Path | None:
    if not runs_dir.is_dir():
        return None
    runs = [
        path
        for path in runs_dir.iterdir()
        if path.is_dir()
        and (path / "provenance.json").is_file()
        and (path / "verification.json").is_file()
    ]
    return max(runs, key=run_order_key) if runs else None


def run_order_key(path: Path) -> tuple[str, int, str]:
    provenance = json.loads((path / "provenance.json").read_text(encoding="utf-8"))
    return (
        str(provenance.get("created_utc", "")),
        int(provenance.get("repetitions", 0)),
        path.name,
    )


def fresh_status(state: dict[str, object]) -> str:
    verification = state["verification"]
    if not isinstance(verification, dict):
        return "NOT RUN"
    tolerance = "PASS" if all(bool(item.get("pass")) for item in verification.values()) else "FAIL"
    provenance = state.get("provenance")
    if isinstance(provenance, dict) and not provenance.get("results_reproduced_eligible", False):
        return f"DIAGNOSTIC {tolerance}; NOT PAPER-EQUIVALENT"
    return tolerance


def verification_table(state: dict[str, object]) -> str:
    verification = state["verification"]
    if not isinstance(verification, dict):
        return "No fresh four-system run is packaged yet."
    lines = [
        "| Check | Max relative error | Threshold | Status |",
        "| --- | ---: | ---: | --- |",
    ]
    for name, item in verification.items():
        status = "PASS" if item.get("pass") else "FAIL"
        lines.append(
            f"| {name} | {float(item.get('max_relative_error', 0)):.6f} | "
            f"{float(item.get('threshold', 0)):.6f} | {status} |"
        )
    return "\n".join(lines)


def fresh_summary_table(state: dict[str, object]) -> str:
    summary = state.get("fresh_summary")
    if not isinstance(summary, dict):
        return "No complete fresh measurement summary is available."
    systems = summary.get("systems")
    if not isinstance(systems, dict) or not systems:
        return "No complete fresh measurement summary is available."
    lines = [
        "| System | Rows | Failed functional rows | Mean latency (ms) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for system in ("TempGNN", "MATG", "ViTeGNN", "RTGA"):
        item = systems.get(system)
        if isinstance(item, dict):
            lines.append(
                f"| {system} | {int(item['rows'])} | {int(item['bad'])} | "
                f"{float(item['mean_latency_ms']):.6f} |"
            )
    return "\n".join(lines)


def summary_document(state: dict[str, object]) -> str:
    run = state["run"]
    lines = [
        "# TempGNN AE Reproduction Report",
        "",
        "## U280 Latency",
        "",
        f"Latest run: `{run.as_posix()}`" if isinstance(run, Path) else "Latest run: none",
        "",
        fresh_summary_table(state),
        "",
        "Run on U280:",
        "",
        "```bash",
        "source /opt/xilinx/xrt/setup.sh",
        "make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3",
        "```",
        "",
        "## Figures",
        "",
        "All remaining figure values are read from `results/result.csv`.",
        "",
        "```bash",
        "python3 -m scripts.reproduce_paper_figures",
        "```",
        "",
    ]
    return "\n".join(lines)


def quickstart_document(state: dict[str, object]) -> str:
    return """# TempGNN AE Quickstart

## Run TempGNN and Baseline Accelerators on U280

```bash
source /opt/xilinx/xrt/setup.sh
make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3
```

Fresh measurements are written under
`results/reviewer_u280_runs/<run-id>/`.

## Generate Figures from result.csv

```bash
python3 -m scripts.reproduce_paper_figures
```

All figure values are read from `results/result.csv`. Generated CSV/SVG files
are written to `results/paper_reproduction/`.
"""


def bridge_document(state: dict[str, object]) -> str:
    status = fresh_status(state)
    return f"""# TempGNN AE Bridge Claim Map

See `AE_APPENDIX_DRAFT.md` for the measurement boundary.

| Bridge | Evidence | Verification |
| --- | --- | --- |
| Artifacts Available | Source, tests, fixtures, four hosts/xclbins, build provenance, board logs, and CSV/SVG records | Inspect `hardware/`, `hardware/baselines/`, `artifacts/u280/`, `scripts/`, and `results/` |
| Artifacts Evaluated Functional | Distinct-xclbin preflight, XRT checksum validation, repeat checks, gated board-power sampling, and post-route reports | Run `make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3` |
| Results Reproduced | Not currently asserted: the available bounded reproduction path differs from the paper's precision, model checkpoints, full-stream coverage, and power method | Current diagnostic tolerance status is **{status}** |

The Results Reproduced bridge is not asserted for the current bounded implementation, even if its diagnostic tolerance check passes.
"""


def inventory_document(state: dict[str, object]) -> str:
    run = state["run"]
    latest = run.as_posix() if isinstance(run, Path) else "not available"
    return f"""# TempGNN Result Inventory

## Figure Data

- `results/result.csv`
- `results/paper_reproduction/*.csv`
- `results/paper_reproduction/*.svg`
- `results/paper_reproduction/figure_data_manifest.csv`
- `results/paper_reproduction/all_figure_data.csv`

Run `python3 -m scripts.reproduce_paper_figures` to regenerate the figures from
`results/result.csv`.

## U280 Latency

- Latest timestamped run: `{latest}`
- Raw rows: `results/reviewer_u280_runs/<run-id>/raw/*/measurements.csv`
"""


def runbook_document(state: dict[str, object]) -> str:
    return """# U280 AE Runbook

## Environment

```bash
source /opt/xilinx/xrt/setup.sh
```

## Run TempGNN and Baseline Accelerators

```bash
make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3
```

## Generate Figures from result.csv

```bash
python3 -m scripts.reproduce_paper_figures
```

All figure values are read from `results/result.csv`.
"""


def average_solution(path: Path, solution: str) -> float:
    rows = read_csv(path)
    explicit = [
        float(row["value"])
        for row in rows
        if row.get("solution") == solution
        and row.get("model") == "AVG"
        and row.get("dataset") == "AVG"
    ]
    if len(explicit) == 1:
        return explicit[0]
    if len(explicit) > 1:
        raise ValueError(f"multiple explicit AVG rows for {solution} in {path}")
    values = [
        float(row["value"])
        for row in rows
        if row.get("solution") == solution and row.get("model") != "AVG"
    ]
    return mean(values)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


if __name__ == "__main__":
    main()
