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

    q14_rows = read_csv(args.q14_summary) if args.q14_summary.is_file() else []
    run = latest_run(args.runs_dir)
    verification = None
    provenance = None
    if run is not None:
        verification = json.loads((run / "verification.json").read_text(encoding="utf-8"))
        provenance = json.loads((run / "provenance.json").read_text(encoding="utf-8"))
    return {
        "averages": averages,
        "board": board,
        "q14_rows": q14_rows,
        "run": run,
        "verification": verification,
        "provenance": provenance,
    }


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


def summary_document(state: dict[str, object]) -> str:
    averages = state["averages"]
    run = state["run"]
    board = state["board"]
    lines = [
        "# TempGNN AE Reproduction Report",
        "",
        "## Scope",
        "",
        "The figure command regenerates paper-reference CSV/SVG records from source-labeled Python constants; it does not rerun CPU, GPU, or FPGA baselines. The one-command U280 path executes four distinct xclbins and writes new latency, total-board-power, checksum, and provenance evidence before regenerating this report. MATG, ViTeGNN, and RTGA are independent paper-based forward-path reproductions, not the baseline authors' complete original stacks.",
        "The fresh command is a bounded mechanism-level comparison on real-dataset prefixes. Each xclbin link request is cross-checked against the Vivado-connected kernel clock and nonnegative post-route WNS/TNS. Every implementation must keep one stable timing-closed clock across its rows; raw latency is compared without frequency rescaling. It is not paper-equivalent: the packaged kernels use an 8-dimensional Q10 forward path and `xbutil` board power, while the paper specifies full models, default 32-bit floating point, full evaluation streams, and post-route Vivado power estimates.",
        "",
        "See `AE_APPENDIX_DRAFT.md` for the authoritative measurement boundary.",
        "",
        "## Code-Embedded Paper Reference Averages",
        "",
        "These are explicit AVG cells/bars from the source-labeled paper-reference input:",
        "",
        "| Record | Value |",
        "| --- | ---: |",
    ]
    labels = [
        ("tempgnn_vs_tglite", "TempGNN / TGLite-CPU speedup"),
        ("tempgnn_g_vs_tglite", "TempGNN-G / TGLite-CPU speedup"),
        ("cascade_vs_tglite", "Cascade / TGLite-CPU speedup"),
        ("tempgnn_vs_matg", "TempGNN / MATG plotted AVG bar"),
        ("cascade_energy", "Cascade / TempGNN energy"),
        ("wo_ddtc", "Without DDTC normalized time"),
        ("wo_oats", "Without OATS normalized time"),
    ]
    for key, label in labels:
        value = averages.get(key) if isinstance(averages, dict) else None
        lines.append(f"| {label} | {value:.2f}x |" if isinstance(value, float) else f"| {label} | unavailable |")
    lines.extend(
        [
            "",
            "The Fig.11 vector export contains a 7.7889x TempGNN/MATG AVG bar, while the paper prose reports 7.6x. The source discrepancy is preserved rather than overwritten.",
            "",
            "## Fresh U280 Status",
            "",
            f"Latest run: `{run.as_posix()}`" if isinstance(run, Path) else "Latest run: none",
            "",
            verification_table(state),
            "",
            "A numerical tolerance PASS does not establish the Results Reproduced bridge while provenance marks the method as not paper-equivalent. Reference CSV values are never substituted for measured rows.",
            "",
            "## Hardware",
            "",
            "Each comparison build uses the per-design timing-closed clock recorded in its raw rows and post-route evidence on `xilinx_u280_gen3x16_xdma_1_202211_1`; no frequency rescaling is applied.",
        ]
    )
    if isinstance(board, dict):
        timing = board.get("post_route_timing", {})
        lines.append(
            f"The original TempGNN sanity build reports WNS={timing.get('wns_ns')} ns and TNS={timing.get('tns_ns')} ns."
        )
    lines.extend(
        [
            "",
            "## Reviewer Command",
            "",
            "```bash",
            "source /opt/xilinx/xrt/setup.sh",
            "make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def quickstart_document(state: dict[str, object]) -> str:
    return f"""# TempGNN AE Quickstart

The recommended reviewer path is one command: `make ae-core-u280`. It
generates source-labeled paper-reference figures from code, executes TempGNN,
MATG, ViTeGNN, and RTGA as four distinct U280 xclbins, validates the fresh
measurement rows, derives the core comparison, and regenerates this report.
No CPU or GPU performance baseline is executed.

MATG, ViTeGNN, and RTGA are paper-based forward-path reproductions. Their implemented mechanisms and limitations are documented in `hardware/baselines/README.md`. This bounded Q10 path is not a paper-equivalent rerun of Fig.11/Fig.12.

Paper-reference inputs live as 668 structured records in
`tempgenn/paper_reference_data.py`. Every record identifies an exact workbook
value or a vector-geometry digitization; these records are never substituted
for fresh U280 measurements. The deterministic CSV/SVG outputs are included in
`results/paper_reproduction/` for direct inspection and are regenerated by the
same one-command path.

## Optional Software Checks

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
make smoke
make report
```

## U280

```bash
source /opt/xilinx/xrt/setup.sh
make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3
```

Fresh status: **{fresh_status(state)}**.

Raw rows, logs, per-sample power evidence, hashes, figures, and verification are written under `results/reviewer_u280_runs/<run-id>/`.
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
    return f"""# Full TempGNN Result Inventory

## Included, Regenerable Paper Figure Records

- `results/paper_reproduction/*.csv`
- `results/paper_reproduction/*.svg`
- `results/paper_reproduction/figure_data_manifest.csv`
- `results/paper_reproduction/paper_figure_values.csv`
- `results/paper_reproduction/all_figure_data.csv`
- `tempgenn/paper_reference_data.py`
- `reference_inputs/README.md`

The Python source records regenerate these source-labeled paper plotting
outputs. The CSV/SVG files are included in the AE archive for direct reviewer
inspection; they are deterministic paper-reference reconstructions, not fresh
hardware executions.

## Fresh U280 Mechanism Evidence

- Four artifacts: `artifacts/u280/TempGNN`, `MATG`, `ViTeGNN`, and `RTGA`
- Baseline source: `hardware/baselines/`
- Configuration: `configs/u280_core_reproduction.json`
- Latest timestamped run: `{latest}`
- Raw rows: `results/reviewer_u280_runs/<run-id>/raw/*/measurements.csv`
- Provenance: `results/reviewer_u280_runs/<run-id>/provenance.json`
- Derived figures: `results/reviewer_u280_runs/<run-id>/derived_comparison_figures/`
- Verification: `results/reviewer_u280_runs/<run-id>/verification.md`

## Additional Evidence

- TempGNN sanity board logs and layout: `results/board_u280/`
- Optional, not pre-packaged TGL edge-stream counters: `results/q14_real_tgl_edges/`
- Reviewer reports: `results/ae_report/`
"""


def runbook_document(state: dict[str, object]) -> str:
    return f"""# U280 AE Runbook

## Environment

```bash
source /tools/Xilinx/Vitis/2023.2/settings64.sh  # rebuild only
source /opt/xilinx/xrt/setup.sh
```

## Fast Checks

```bash
python3 -m unittest discover -s tests
python3 -m scripts.reproduce_paper_figures
make baseline-csim
```

The figure command regenerates the source-labeled paper-reference inputs. `baseline-csim` executes every paper-based kernel twice and requires bit-identical outputs and stats.

## Fresh Mechanism-Level Comparison

```bash
make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3
```

Preflight requires four distinct xclbin hashes. The measurement harness fetches deterministic prefixes from the six public real datasets, records source/sample hashes, cross-checks each xclbin link request against the Vivado-connected kernel clock and post-route WNS/TNS, calibrates a repeated-kernel window, validates repeat checksums, samples total U280 board power with `xbutil`, writes raw rows, derives measured Fig.11/Fig.12 comparison data, and compares it with code-embedded paper references. Each implementation must keep one timing-closed clock across its rows; clocks are recorded and latency is not frequency-rescaled. Synthetic fixtures are accepted only by C-sim and rejected by this workflow. The default target preserves a tolerance failure in `verification.md`; `make ae-core-u280-strict` additionally makes numerical mismatch fail the command.

This is not a paper-equivalent rerun because the reduced Q10 kernels, deterministic stand-in weights, bounded prefixes, and power method differ from the paper methodology.

Current recorded tolerance status: **{fresh_status(state)}**.

## Optional Rebuild

```bash
make u280-build U280_PLATFORM=/opt/xilinx/platforms/xilinx_u280_gen3x16_xdma_1_202211_1/xilinx_u280_gen3x16_xdma_1_202211_1.xpfm
make u280-baseline-build
```

Rebuilding can take multiple hours. Packaged xclbins allow board evaluation without Vivado/Vitis.
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
