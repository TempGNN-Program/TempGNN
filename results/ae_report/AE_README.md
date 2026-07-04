# TempGNN AE Quickstart

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
