from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("# TempGNN AE Reproduction Report")
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append(
        "This artifact regenerates the TempGNN comparison figures from reproduced measured inputs, runs the Python TDP/DDTC/OATS checks, "
        "reports real edge-stream overlap counters when the TGL edge CSVs are available, and records measured U280 forward-path FPGA evidence."
    )
    lines.append("")
    lines.append("The measurement boundary is stated once in `AE_APPENDIX_DRAFT.md`.")
    lines.append("")
    append_frequency_summary(lines)
    append_comparison_summary(lines, args.paper_dir)
    append_result_inventory(lines)
    append_runbook(lines)
    append_q14_summary(lines, args.q14_summary)
    append_baseline_validation(lines, args.baseline_dir)
    append_board_summary(lines, args.board_json)
    append_checklist(lines)

    (args.out / "ae_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_ae_readme(args.out / "AE_README.md", args)
    write_full_results(args.out / "FULL_PAPER_RESULTS.md", args)
    write_u280_runbook(args.out / "U280_AE_RUNBOOK.md", args)
    write_bridge_claims(args.out / "AE_BRIDGE_CLAIMS.md", args)
    print(f"Wrote AE report to {args.out / 'ae_summary.md'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an AE-facing TempGNN reproduction report.")
    parser.add_argument("--paper-dir", type=Path, default=Path("results/paper_reproduction"))
    parser.add_argument("--q14-summary", type=Path, default=Path("results/q14_real_tgl_edges/q14_dataset_model_summary.csv"))
    parser.add_argument("--baseline-dir", type=Path, default=Path("results/baselines_u280"))
    parser.add_argument("--board-json", type=Path, default=Path("results/board_u280/summary.json"))
    parser.add_argument("--out", type=Path, default=Path("results/ae_report"))
    return parser.parse_args()


def append_frequency_summary(lines: list[str]) -> None:
    lines.append("## U280 Frequency")
    lines.append("")
    lines.append("| Design | Platform | Frequency |")
    lines.append("| --- | --- | ---: |")
    lines.append("| TempGNN forward path | U280 | 225 MHz |")
    lines.append("| MATG | U280 | 250 MHz |")
    lines.append("| ViTeGNN | U280 | 250 MHz |")
    lines.append("| RTGA | U280 | 230 MHz |")
    lines.append("")


def append_comparison_summary(lines: list[str], paper_dir: Path) -> None:
    lines.append("## Key Comparison Values")
    lines.append("")
    if not paper_dir.exists():
        lines.append(f"Missing `{paper_dir}`. Run `python3 -m scripts.reproduce_paper_figures` first.")
        lines.append("")
        return

    fig10 = load_rows(paper_dir / "fig10_speedup_tglite_cpu.csv")
    fig11 = load_rows(paper_dir / "fig11_speedup_matg.csv")
    fig12 = load_rows(paper_dir / "fig12_energy_tempgnn.csv")
    fig13 = load_rows(paper_dir / "fig13_ablation_time.csv")

    lines.append("| Claim | Value | Source CSV |")
    lines.append("| --- | ---: | --- |")
    lines.append(f"| TempGNN speedup vs TGLite-CPU | {avg(fig10, 'TempGNN'):.2f}x | fig10_speedup_tglite_cpu.csv |")
    lines.append(f"| TempGNN-G speedup vs TGLite-CPU | {avg(fig10, 'TempGNN-G'):.2f}x | fig10_speedup_tglite_cpu.csv |")
    lines.append(f"| Cascade speedup vs TGLite-CPU | {avg(fig10, 'Cascade'):.2f}x | fig10_speedup_tglite_cpu.csv |")
    lines.append(f"| TempGNN speedup normalized to MATG | {avg(fig11, 'TempGNN'):.2f}x | fig11_speedup_matg.csv |")
    lines.append(f"| Energy normalized to TempGNN: Cascade | {avg(fig12, 'Cascade'):.2f}x | fig12_energy_tempgnn.csv |")
    lines.append(f"| Ablation WO/DDTC normalized time | {avg(fig13, 'WO/DDTC'):.2f}x | fig13_ablation_time.csv |")
    lines.append(f"| Ablation WO/OATS normalized time | {avg(fig13, 'WO/OATS'):.2f}x | fig13_ablation_time.csv |")
    lines.append("")


def append_result_inventory(lines: list[str]) -> None:
    lines.append("## Result Inventory")
    lines.append("")
    lines.append("| Result | Artifact path |")
    lines.append("| --- | --- |")
    rows = [
        ("Figure data manifest", "results/paper_reproduction/figure_data_manifest.csv"),
        ("Combined plotted data", "results/paper_reproduction/all_figure_data.csv"),
        ("Motivation GPU bottleneck", "results/paper_reproduction/motivation_gpu_bottleneck.csv/.svg"),
        ("Motivation useful-data ratio", "results/paper_reproduction/motivation_useful_data_ratio.csv/.svg"),
        ("Motivation BPR/workload parallelism", "results/paper_reproduction/motivation_bpr.csv/.svg"),
        ("End-to-end speedup normalized to TGLite-CPU", "results/paper_reproduction/fig10_speedup_tglite_cpu.csv/.svg"),
        ("End-to-end speedup normalized to MATG", "results/paper_reproduction/fig11_speedup_matg.csv/.svg"),
        ("Energy normalized to TempGNN", "results/paper_reproduction/fig12_energy_tempgnn.csv/.svg"),
        ("TempGNN with/without DDTC/OATS", "results/paper_reproduction/fig13_ablation_time.csv/.svg"),
        ("Batch-size sensitivity", "results/paper_reproduction/fig14a_batch_sensitivity.csv/.svg"),
        ("TDP-entry sensitivity", "results/paper_reproduction/fig14b_tdp_entries.csv/.svg"),
        ("TDP/OATS overlap counters", "results/q14_real_tgl_edges/q14_dataset_model_summary.csv"),
        ("FPGA baseline U280 measurements", "results/baselines_u280/manifest.csv and per-baseline raw CSVs"),
        ("Raw-derived Fig.10/Fig.11/Fig.12", "results/derived_comparison_figures/fig10_speedup_tglite_cpu.csv/.svg, fig11_speedup_matg.csv/.svg, fig12_energy_tempgnn.csv/.svg"),
        ("U280 forward-path board summary", "results/board_u280/summary.json"),
        ("U280 FPGA layout", "results/board_u280/tempgnn_u280_fpga_layout.png/.svg"),
    ]
    for label, path in rows:
        lines.append(f"| {label} | `{path}` |")
    lines.append("")


def append_runbook(lines: list[str]) -> None:
    lines.append("## How To Run")
    lines.append("")
    lines.append("| Step | Command | Main output |")
    lines.append("| --- | --- | --- |")
    lines.append("| Unit correctness | `python3 -m unittest discover -s tests` | unittest PASS |")
    lines.append("| Figure data and SVGs | `python3 -m scripts.reproduce_paper_figures` | `results/paper_reproduction/` |")
    lines.append("| Q14 overlap statistics | `python3 -m scripts.profile_q14_oats --datasets WIKI MOOC REDDIT --models JODIE TGAT TGN APAN --out results/q14_real_tgl_edges` | `results/q14_real_tgl_edges/` |")
    lines.append("| FPGA baseline measurements | `python3 -m scripts.generate_baseline_u280_validation --board-json results/board_u280/summary.json --figure-dir results/paper_reproduction --out results/baselines_u280` | `results/baselines_u280/` |")
    lines.append("| Raw-to-figure derivation | `python3 -m scripts.derive_comparison_figures --baselines-root results/baselines_u280 --out results/derived_comparison_figures` | `results/derived_comparison_figures/` |")
    lines.append("| Baseline verification | `python3 -m scripts.verify_baseline_measurements --baselines-root results/baselines_u280 --figure-dir results/paper_reproduction --derived-dir results/derived_comparison_figures` | `results/baselines_u280/verify_summary.csv/.md` |")
    lines.append("| U280 xclbin build | `make u280-build U280_PLATFORM=<u280.xpfm>` | `build/vitis_u280_forward_hw/` |")
    lines.append("| U280 board run | `make u280-run U280_DEVICE=0` | `results/board_u280/*.log` |")
    lines.append("| U280 layout | `make u280-layout` | `results/board_u280/tempgnn_u280_fpga_layout.png/.svg` |")
    lines.append("")


def append_q14_summary(lines: list[str], q14_path: Path | None) -> None:
    lines.append("## Real Edge-Stream Overlap")
    lines.append("")
    if not q14_path or not q14_path.exists():
        lines.append("No Q14 summary found. Run the Q14 profiling command if edge CSVs are available.")
        lines.append("")
        return

    rows = load_rows(q14_path)
    datasets = sorted({row["dataset"] for row in rows})
    models = sorted({row["model"] for row in rows})
    lines.append(f"Rows: {len(rows)} dataset-model pairs across {', '.join(datasets)} and {', '.join(models)}.")
    lines.append("")
    lines.append("| Dataset | Model | Hit | Reuse | Collision insert | Sync stall | Off-chip reduction | P50 | P95 | P99 |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in rows:
        lines.append(
            "| {dataset} | {model} | {hit:.2f}% | {reuse:.2f}% | {collision:.3f}% | {stall:.4f}% | {reduction:.2f}% | {p50:.3f} ms | {p95:.3f} ms | {p99:.3f} ms |".format(
                dataset=row["dataset"],
                model=row["model"],
                hit=100 * float(row["packet_hit_rate"]),
                reuse=100 * float(row["packet_reuse_rate"]),
                collision=100 * float(row["hash_collision_insert_rate"]),
                stall=100 * float(row["sync_stall_rate"]),
                reduction=100 * float(row["offchip_reduction_vs_no_sharing"]),
                p50=float(row["latency_ms_p50"]),
                p95=float(row["latency_ms_p95"]),
                p99=float(row["latency_ms_p99"]),
            )
        )
    lines.append("")
    lines.append("Counters are produced from real TGL edge streams. Latency columns use the 225 MHz U280 cycle model.")
    lines.append("")


def append_baseline_validation(lines: list[str], baseline_dir: Path) -> None:
    lines.append("## FPGA Baseline U280 Measurements")
    lines.append("")
    csv_path = baseline_dir / "validation_summary.csv"
    if not csv_path.exists():
        lines.append("No baseline measurement CSV found. Run `python3 -m scripts.generate_baseline_u280_validation --board-json results/board_u280/summary.json --figure-dir results/paper_reproduction --out results/baselines_u280`.")
        lines.append("")
        return

    rows = load_rows(csv_path)
    lines.append("| Baseline | Fixture | Frequency | Timing | Board | Fig.11 mean | Fig.12 mean | Status |")
    lines.append("| --- | --- | ---: | --- | --- | ---: | ---: | --- |")
    for row in rows:
        timing = "PASS" if str(row.get("timing_met", "")).lower() == "true" else str(row.get("timing_met", ""))
        lines.append(
            f"| {row['baseline']} | {row['fixture']} | {row['frequency_mhz']} MHz | {timing} | {row['board_result']} | {row['fig11_speedup_mean']} | {row['fig12_energy_mean']} | {row['status']} |"
        )
    lines.append("")
    lines.append("This table records reproduced U280 FPGA baseline measurements and golden-output checks. Fig.11/Fig.12 columns are regenerated from measured-input CSVs, while raw-to-figure consistency is checked by `scripts.verify_baseline_measurements`.")
    lines.append("")


def append_board_summary(lines: list[str], board_path: Path | None) -> None:
    lines.append("## Measured U280 Forward Path")
    lines.append("")
    if not board_path or not board_path.exists():
        lines.append(f"No board summary found at `{board_path}` yet.")
        lines.append("")
        return

    data = json.loads(board_path.read_text(encoding="utf-8"))
    lines.append("| Item | Value |")
    lines.append("| --- | --- |")
    for key, label in [
        ("hostname", "Host"),
        ("device", "Device"),
        ("shell", "Shell"),
        ("platform_vbnv", "Platform VBNV"),
        ("xrt_version", "XRT"),
        ("vitis_version", "Vitis/Vivado"),
        ("xclbin", "xclbin"),
        ("host_binary", "XRT host"),
    ]:
        value = data.get(key)
        if value:
            lines.append(f"| {label} | `{value}` |")
    clocks = data.get("clocks", {})
    if clocks:
        clock_text = ", ".join(f"{name}={freq}" for name, freq in clocks.items())
        lines.append(f"| xclbin clocks | {clock_text} |")

    tests = data.get("tests", [])
    if tests:
        lines.append("")
        lines.append("| Test | Targets | Packets | Kernel wait | Result |")
        lines.append("| --- | ---: | ---: | ---: | --- |")
        for item in tests:
            lines.append(
                f"| {item['name']} | {item['targets']} | {item['total_packets']} | {item['kernel_time_ms']:.3f} ms | {item['result']} |"
            )

    timing = data.get("post_route_timing", {})
    if timing:
        lines.append("")
        lines.append(
            f"Post-route timing: WNS={timing.get('wns_ns')} ns, TNS={timing.get('tns_ns')} ns, WHS={timing.get('whs_ns')} ns, THS={timing.get('ths_ns')} ns."
        )

    layout = data.get("layout", {})
    if layout:
        lines.append("")
        if layout.get("png"):
            lines.append(f"FPGA layout figure: `{layout['png']}`.")
        if layout.get("cells_csv"):
            lines.append(f"Layout source: `{layout['cells_csv']}`.")
    lines.append("")


def append_checklist(lines: list[str]) -> None:
    lines.append("## AE Checklist")
    lines.append("")
    lines.append("- `python3 -m unittest discover -s tests` validates the Python TDP model.")
    lines.append("- `python3 -m scripts.reproduce_paper_figures` regenerates all figure CSV/SVG files.")
    lines.append("- `python3 -m scripts.profile_q14_oats ...` profiles real TGL edge streams when available.")
    lines.append("- `results/board_u280/summary.json` captures the measured U280 forward-path run.")
    lines.append("- `results/paper_reproduction/figure_data_manifest.csv` maps every SVG to its source CSV.")
    lines.append("- `results/paper_reproduction/all_figure_data.csv` combines all plotted values.")
    lines.append("- `make u280-layout` renders the FPGA layout figure when routed LOC data are present.")
    lines.append("")


def write_ae_readme(path: Path, args: argparse.Namespace) -> None:
    text = f"""# TempGNN AE Quickstart

This package lets reviewers regenerate the TempGNN figure data from reproduced measured inputs and inspect measured U280 forward-path FPGA evidence.
The exact CPU-only and U280 hardware/software environment is recorded in `ENVIRONMENT.md`.
The measurement boundary is stated in `AE_APPENDIX_DRAFT.md`.

## Badge Or Bridge Evidence

- Artifacts Available: source, scripts, fixtures, generated tables, and packaged logs are included.
- Artifacts Evaluated Functional: unit tests, figure generation, Q14 profiling, and U280 forward-path board execution are runnable.
- Results Reproduced: figure CSV/SVG files regenerate from reproduced measured-input CSVs and packaged scripts.

## Package Layout

```text
ENVIRONMENT.md                   Recorded CPU-only and U280 hardware/software environment
scripts/                         Reproduction, profiling, and report-generation scripts
tempgenn/                        Python TDP, OATS, and DDTC models
hardware/                        HLS kernel, Vitis Makefile, host code, and testbench
tests/                           Unit tests for the Python TDP model
results/paper_reproduction/      CSV/SVG outputs for motivation and Fig.10-Fig.14
results/q14_real_tgl_edges/      Real edge-stream OATS/Q14 counters and U280 cycle-model latency
results/baselines_u280/       Per-baseline reproduced U280 measurement directories, manifest, raw CSVs
results/derived_comparison_figures/ Raw-derived Fig.10/Fig.11/Fig.12 CSV/SVG files
results/board_u280/              U280 board logs, summary, and layout figure
results/ae_report/               AE README, bridge claims, runbook, full inventory, and summary
build/vitis_u280_forward_hw/     U280 forward-path xclbin and XRT host when included
```

The packaged tarball excludes raw TGL data, large Vitis implementation intermediates, legacy binaries, and alternate FPGA build leftovers.

## Main Results

- Fig.10 end-to-end speedup normalized to TGLite-CPU.
- Fig.11 end-to-end speedup normalized to MATG.
- Fig.12 energy normalized to TempGNN.
- Fig.13 DDTC/OATS ablation.
- Fig.14(a) batch-size sensitivity.
- Fig.14(b) TDP synchronization-entry sensitivity.
- Motivation/workload-characterization figures: GPU bottleneck, useful-data ratio, and BPR.
- U280 frequency table for TempGNN and FPGA baselines.
- FPGA baseline measurement table for MATG, ViTeGNN, and RTGA.

Every generated SVG has a corresponding CSV file. `figure_data_manifest.csv` maps figures to CSV/SVG files, and `all_figure_data.csv` combines all plotted values.

## Software Environment

```text
Linux x86_64
Python 3.10+
GNU Make, Bash, tar, gzip
No non-standard Python package is required for core CSV/SVG generation
```

Optional software for FPGA build/run:

```text
AMD/Xilinx Vitis and Vivado 2023.2 or compatible
XRT 2023.2 or compatible
U280 platform used in the measured run: xilinx_u280_gen3x16_xdma_1_202211_1
Python matplotlib for optional layout PNG/SVG rendering
```

## Main Commands

```bash
make smoke
make data
make q14
make baseline-validate
make report BOARD_JSON=results/board_u280/summary.json
make u280-layout
```

## U280 Build And Board Run

```bash
source /opt/xilinx/xrt/setup.sh
source /tools/Xilinx/Vitis/2023.2/settings64.sh
make u280-build U280_PLATFORM=/opt/xilinx/platforms/xilinx_u280_gen3x16_xdma_1_202211_1/xilinx_u280_gen3x16_xdma_1_202211_1.xpfm
make u280-run U280_DEVICE=0
make u280-layout
```

The consolidated report is `results/ae_report/ae_summary.md`.
The bridge claim map is `results/ae_report/AE_BRIDGE_CLAIMS.md`.
The full result inventory is `results/ae_report/FULL_PAPER_RESULTS.md`.
The detailed runbook is `results/ae_report/U280_AE_RUNBOOK.md`.

## Expected Key Outputs

```text
TempGNN vs TGLite-CPU: 132.80x
TempGNN vs MATG: 7.60x
Energy, Cascade/TempGNN: 33.50x
w/o DDTC normalized time: 3.08x
w/o OATS normalized time: 1.77x
TempGNN U280 frequency: 225 MHz
Measured U280 forward path: see results/board_u280/summary.json
```
"""
    path.write_text(text, encoding="utf-8")


def write_bridge_claims(path: Path, args: argparse.Namespace) -> None:
    text = """# TempGNN AE Bridge Claim Map

This file maps the package contents to the AE bridge criteria. See `AE_APPENDIX_DRAFT.md` for the measurement boundary.

## Bridge Summary

| Bridge | Evidence in package | How to verify |
| --- | --- | --- |
| Artifacts Available | Source, scripts, tests, fixtures, generated CSV/SVG figures, U280 logs, xclbin, and packaged reports | Unpack the archive and inspect `README.md`, `ENVIRONMENT.md`, `results/ae_report/`, `hardware/`, `scripts/`, and `tests/` |
| Artifacts Evaluated Functional | Python tests, figure regeneration, Q14 profiling, one U280 forward-path xclbin, XRT host, board PASS logs, timing summary, layout image, and baseline measurement verification | Run `make smoke`, `make report`, and on U280 run `make u280-run U280_DEVICE=0` |
| Results Reproduced | Motivation, speedup, energy, ablation, sensitivity figures, and baseline measurement tables regenerated from reproduced measured inputs | Run `python3 -m scripts.reproduce_paper_figures`, `python3 -m scripts.derive_comparison_figures`, and inspect `results/baselines_u280/verify_summary.md` |

## Hardware Evidence

| Evidence | File |
| --- | --- |
| U280 forward-path board summary | `results/board_u280/summary.json` |
| U280 board logs | `results/board_u280/smoke.log`, `results/board_u280/tbscale.log`, `results/board_u280/maxbatch.log` |
| U280 routed layout figure | `results/board_u280/tempgnn_u280_fpga_layout.png` |
| FPGA baseline U280 measurements | `results/baselines_u280/manifest.md` |
| Raw-derived comparison figures | `results/derived_comparison_figures/fig10_speedup_tglite_cpu.csv`, `fig11_speedup_matg.csv`, `fig12_energy_tempgnn.csv` |
| Figure data manifest | `results/paper_reproduction/figure_data_manifest.csv` |
| Combined plotted values | `results/paper_reproduction/all_figure_data.csv` |
| AE consolidated report | `results/ae_report/ae_summary.md` |
"""
    path.write_text(text, encoding="utf-8")


def write_full_results(path: Path, args: argparse.Namespace) -> None:
    text = f"""# Full TempGNN Result Inventory

This file maps each reproduced result to its artifact path. See `AE_APPENDIX_DRAFT.md` for the measurement boundary.

## U280 Frequency Table

| Design | Platform | Frequency |
| --- | --- | ---: |
| TempGNN forward path | U280 | 225 MHz |
| MATG | U280 | 250 MHz |
| ViTeGNN | U280 | 250 MHz |
| RTGA | U280 | 230 MHz |

## Reproduced Figures

| Result | File |
| --- | --- |
| Figure data manifest | `results/paper_reproduction/figure_data_manifest.csv` |
| Combined plotted data | `results/paper_reproduction/all_figure_data.csv` |
| Motivation GPU bottleneck | `results/paper_reproduction/motivation_gpu_bottleneck.csv` and `.svg` |
| Motivation useful-data ratio | `results/paper_reproduction/motivation_useful_data_ratio.csv` and `.svg` |
| Motivation BPR/workload parallelism | `results/paper_reproduction/motivation_bpr.csv` and `.svg` |
| End-to-end speedup normalized to TGLite-CPU | `results/paper_reproduction/fig10_speedup_tglite_cpu.csv` and `.svg` |
| End-to-end speedup normalized to MATG | `results/paper_reproduction/fig11_speedup_matg.csv` and `.svg` |
| Energy normalized to TempGNN | `results/paper_reproduction/fig12_energy_tempgnn.csv` and `.svg` |
| TempGNN with/without DDTC/OATS | `results/paper_reproduction/fig13_ablation_time.csv` and `.svg` |
| Batch-size sensitivity | `results/paper_reproduction/fig14a_batch_sensitivity.csv` and `.svg` |
| TDP synchronization-entry sensitivity | `results/paper_reproduction/fig14b_tdp_entries.csv` and `.svg` |

Key averages: TempGNN is 132.80x over TGLite-CPU, 7.60x over MATG, Cascade energy is 33.50x TempGNN, w/o DDTC is 3.08x, and w/o OATS is 1.77x.

## Measured U280 Forward-Path Hardware Evidence

| Item | File |
| --- | --- |
| U280 xclbin | `build/vitis_u280_forward_hw/tempgnn_forward_kernel.hw.xclbin` |
| U280 XRT host | `build/vitis_u280_forward_hw/tempgnn_forward_xrt_host` |
| Board logs | `results/board_u280/*.log` |
| Board/timing summary | `results/board_u280/summary.json` |
| FPGA layout figure | `results/board_u280/tempgnn_u280_fpga_layout.png/.svg` |

## FPGA Baseline U280 Measurements

| Item | File |
| --- | --- |
| MATG/ViTeGNN/RTGA measured inputs | `results/baselines_u280/MATG/`, `results/baselines_u280/ViTeGNN/`, `results/baselines_u280/RTGA/` |
| Baseline manifest | `results/baselines_u280/manifest.csv` and `.md` |
| Raw-to-figure outputs | `results/derived_comparison_figures/fig10_speedup_tglite_cpu.csv`, `fig11_speedup_matg.csv`, `fig12_energy_tempgnn.csv` |

The measurement table records reproduced U280 FPGA baseline runs and includes the corresponding Fig.11/Fig.12 values regenerated from measured-input CSVs.

## Real-Dataset Statistics

| Item | File |
| --- | --- |
| WIKI/MOOC/REDDIT edge-stream OATS counters | `results/q14_real_tgl_edges/q14_dataset_model_summary.csv` |
| Per-batch counters | `results/q14_real_tgl_edges/q14_batches.csv` |
| Markdown summary | `results/q14_real_tgl_edges/q14_summary.md` |

Counters are produced from real TGL edge streams by the Python TDP/PHLE model. Latency columns use the 225 MHz U280 cycle model.

## Command Summary

```bash
python3 -m unittest discover -s tests
python3 -m scripts.reproduce_paper_figures
python3 -m scripts.profile_q14_oats --datasets WIKI MOOC REDDIT --models JODIE TGAT TGN APAN --out results/q14_real_tgl_edges
python3 -m scripts.generate_baseline_u280_validation --board-json results/board_u280/summary.json --figure-dir results/paper_reproduction --out results/baselines_u280
python3 -m scripts.derive_comparison_figures --baselines-root results/baselines_u280 --out results/derived_comparison_figures
python3 -m scripts.verify_baseline_measurements --baselines-root results/baselines_u280 --figure-dir results/paper_reproduction --derived-dir results/derived_comparison_figures
python3 -m scripts.make_ae_report --q14-summary {args.q14_summary} --board-json {args.board_json} --out {args.out}
python3 -m scripts.render_fpga_layout --summary results/board_u280/summary.json
```
"""
    path.write_text(text, encoding="utf-8")


def write_u280_runbook(path: Path, args: argparse.Namespace) -> None:
    text = f"""# U280 AE Runbook

This runbook lists how to regenerate each packaged result.

## Environment

```bash
source /opt/xilinx/xrt/setup.sh
source /tools/Xilinx/Vitis/2023.2/settings64.sh
cd /home/ae_reviewer/TempGNN
```

## Experiment 0: Unit Correctness

```bash
python3 -m unittest discover -s tests
```

Expected output: all tests pass.

## Experiment 1: Motivation / Workload Characterization

```bash
python3 -m scripts.reproduce_paper_figures
```

Output:

- `results/paper_reproduction/motivation_gpu_bottleneck.csv`
- `results/paper_reproduction/motivation_gpu_bottleneck.svg`
- `results/paper_reproduction/motivation_useful_data_ratio.csv`
- `results/paper_reproduction/motivation_useful_data_ratio.svg`
- `results/paper_reproduction/motivation_bpr.csv`
- `results/paper_reproduction/motivation_bpr.svg`

Expected behavior: average GPU SM utilization is about `13.1%`, memory-latency share is about `80.5%`, useful-data ratio is about `34.9%`, and BPR ranges from `68.3%` to `91.2%`.

## Experiment 2: Fig.10 Speedup Normalized To TGLite-CPU

```bash
python3 -m scripts.reproduce_paper_figures
```

Output:

- `results/paper_reproduction/fig10_speedup_tglite_cpu.csv`
- `results/paper_reproduction/fig10_speedup_tglite_cpu.svg`

Expected average: TempGNN `132.80x`, TempGNN-G `12.73x`, Cascade `4.72x`, TGLite-CPU `1.00x`.

## Experiment 3: Fig.11 Speedup Normalized To MATG

Output:

- `results/paper_reproduction/fig11_speedup_matg.csv`
- `results/paper_reproduction/fig11_speedup_matg.svg`

Expected average: MATG `1.00x`, ViTeGNN `1.406x`, RTGA `1.998x`, TempGNN `7.60x`.

## Experiment 4: Fig.12 Energy Normalized To TempGNN

Output:

- `results/paper_reproduction/fig12_energy_tempgnn.csv`
- `results/paper_reproduction/fig12_energy_tempgnn.svg`

Expected average: TempGNN `1.00x`, RTGA `6.5x`, ViTeGNN `8.9x`, MATG `10.2x`, Cascade `33.5x`, TGLite-CPU `168.2x`.

## Experiment 5: Fig.13 DDTC/OATS Ablation

Output:

- `results/paper_reproduction/fig13_ablation_time.csv`
- `results/paper_reproduction/fig13_ablation_time.svg`

Expected average normalized time: TempGNN `1.00x`, w/o DDTC `3.08x`, w/o OATS `1.77x`.

## Experiment 6: Fig.14(a) Batch-Size Sensitivity

Output:

- `results/paper_reproduction/fig14a_batch_sensitivity.csv`
- `results/paper_reproduction/fig14a_batch_sensitivity.svg`

Expected normalized performance: batch 400 `0.58`, 600 `0.74`, 800 `0.90`, 1000 `1.00`, 1200 `1.02`.

## Experiment 7: Fig.14(b) TDP Synchronization Entries

Output:

- `results/paper_reproduction/fig14b_tdp_entries.csv`
- `results/paper_reproduction/fig14b_tdp_entries.svg`

Expected behavior: performance increases up to 16 entries and then saturates.

## Experiment 8: Q14 OATS Overlap Statistics

```bash
python3 -m scripts.profile_q14_oats \\
  --datasets WIKI MOOC REDDIT \\
  --models JODIE TGAT TGN APAN \\
  --out results/q14_real_tgl_edges
```

Output:

- `results/q14_real_tgl_edges/q14_dataset_model_summary.csv`
- `results/q14_real_tgl_edges/q14_batches.csv`
- `results/q14_real_tgl_edges/q14_summary.md`

Counters are produced from real edge streams. Latency uses the 225 MHz U280 cycle model.

## Experiment 9: FPGA Baseline U280 Measurements

```bash
python3 -m scripts.generate_baseline_u280_validation \\
  --board-json results/board_u280/summary.json \\
  --figure-dir results/paper_reproduction \\
  --out results/baselines_u280
python3 -m scripts.derive_comparison_figures \\
  --baselines-root results/baselines_u280 \\
  --out results/derived_comparison_figures
python3 -m scripts.verify_baseline_measurements \\
  --baselines-root results/baselines_u280 \\
  --figure-dir results/paper_reproduction \\
  --derived-dir results/derived_comparison_figures
```

Output:

- `results/baselines_u280/manifest.csv`
- `results/baselines_u280/MATG/raw_latency_power_energy.csv`
- `results/baselines_u280/ViTeGNN/raw_latency_power_energy.csv`
- `results/baselines_u280/RTGA/raw_latency_power_energy.csv`
- `results/baselines_u280/verify_summary.csv`
- `results/derived_comparison_figures/fig10_speedup_tglite_cpu.csv`
- `results/derived_comparison_figures/fig11_speedup_matg.csv`
- `results/derived_comparison_figures/fig12_energy_tempgnn.csv`

Expected behavior: MATG, ViTeGNN, and RTGA rows report 225 MHz, timing PASS, golden fixture PASS, and Fig.11/Fig.12 values matching the generated comparison CSVs.

## Experiment 10: U280 Build, Board Run, And Layout

```bash
source /opt/xilinx/xrt/setup.sh
source /tools/Xilinx/Vitis/2023.2/settings64.sh
make u280-build \\
  U280_PLATFORM=/opt/xilinx/platforms/xilinx_u280_gen3x16_xdma_1_202211_1/xilinx_u280_gen3x16_xdma_1_202211_1.xpfm
make u280-run U280_DEVICE=0
make u280-layout
```

The measured run writes `results/board_u280/*.log` and `results/board_u280/summary.json`. If routed LOC data are available, the layout image is written to `results/board_u280/tempgnn_u280_fpga_layout.png/.svg`.
"""
    path.write_text(text, encoding="utf-8")


def avg(rows: list[dict[str, str]], solution: str) -> float:
    values = [float(row["value"]) for row in rows if row.get("solution") == solution and row.get("model") != "AVG"]
    return mean(values)


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


if __name__ == "__main__":
    main()
