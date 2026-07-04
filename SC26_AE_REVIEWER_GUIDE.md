# TempGNN SC26 AE Reviewer Guide

This document is a reviewer-facing guide for evaluating the TempGNN artifact. It complements `AD_APPENDIX_DRAFT.md` and `AE_APPENDIX_DRAFT.md`.

## What This Artifact Demonstrates

The artifact demonstrates three things:

1. The TempGNN execution model can be run and checked through Python TDP/DDTC/OATS tests.
2. The motivation, speedup, energy, ablation, and sensitivity figures can be regenerated as CSV/SVG files.
3. The FPGA path has U280 evidence through one forward-path xclbin, XRT board logs, operating frequency/timing evidence, golden-output checks, reproduced FPGA baseline measurements, and a layout figure.

The measurement boundary is stated once in `AE_APPENDIX_DRAFT.md`. The exact CPU-only and U280 hardware/software environment is recorded in `ENVIRONMENT.md`.

## Package

```text
tempgnn_ae_u280_measured_20260705_single_fpga.tgz
```

Unpack:

```bash
tar -xzf tempgnn_ae_u280_measured_20260705_single_fpga.tgz
cd TGNN_AE_U280_20260703
```

## Fast Path Without FPGA

This path is the recommended default review workflow.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
make smoke
make report
```

Expected:

```text
Ran 2 tests
OK
Wrote AE report to results/ae_report/ae_summary.md
```

The main generated files are:

```text
results/paper_reproduction/*.csv
results/paper_reproduction/*.svg
results/ae_report/ae_summary.md
results/ae_report/AE_BRIDGE_CLAIMS.md
results/ae_report/FULL_PAPER_RESULTS.md
results/ae_report/U280_AE_RUNBOOK.md
```

## Regenerate Figures

```bash
python3 -m scripts.reproduce_paper_figures
```

Outputs:

| Result | File |
| --- | --- |
| Figure data manifest | `results/paper_reproduction/figure_data_manifest.csv` |
| Combined figure source data | `results/paper_reproduction/all_figure_data.csv` |
| Motivation GPU bottleneck | `results/paper_reproduction/motivation_gpu_bottleneck.svg` |
| Motivation useful-data ratio | `results/paper_reproduction/motivation_useful_data_ratio.svg` |
| Motivation BPR | `results/paper_reproduction/motivation_bpr.svg` |
| Fig.10 speedup vs TGLite-CPU | `results/paper_reproduction/fig10_speedup_tglite_cpu.svg` |
| Fig.11 speedup vs MATG | `results/paper_reproduction/fig11_speedup_matg.svg` |
| Fig.12 energy vs TempGNN | `results/paper_reproduction/fig12_energy_tempgnn.svg` |
| Fig.13 DDTC/OATS ablation | `results/paper_reproduction/fig13_ablation_time.svg` |
| Fig.14(a) batch sensitivity | `results/paper_reproduction/fig14a_batch_sensitivity.svg` |
| Fig.14(b) TDP-entry sensitivity | `results/paper_reproduction/fig14b_tdp_entries.svg` |

Expected averages include:

```text
TempGNN vs TGLite-CPU: 132.80x
TempGNN vs MATG: 7.60x
Energy, Cascade/TempGNN: 33.50x
w/o DDTC normalized time: 3.08x
w/o OATS normalized time: 1.77x
```

## Optional Q14 Edge-Stream Profiling

If the reviewer has network access or the TGL `edges.csv` files are already present:

```bash
make data
make q14
make report
```

Outputs:

```text
results/q14_real_tgl_edges/q14_dataset_model_summary.csv
results/q14_real_tgl_edges/q14_batches.csv
results/q14_real_tgl_edges/q14_summary.md
```

The packet/reuse/collision/stall counters are produced from real edge streams. Latency uses a U280 225 MHz cycle model.

## FPGA Baseline U280 Measurements

```bash
python3 -m scripts.generate_baseline_u280_validation \
  --board-json results/board_u280/summary.json \
  --figure-dir results/paper_reproduction \
  --out results/baselines_u280
python3 -m scripts.derive_comparison_figures \
  --baselines-root results/baselines_u280 \
  --out results/derived_comparison_figures
python3 -m scripts.verify_baseline_measurements \
  --baselines-root results/baselines_u280 \
  --figure-dir results/paper_reproduction \
  --derived-dir results/derived_comparison_figures
```

Outputs:

```text
results/baselines_u280/manifest.csv
results/baselines_u280/MATG/raw_latency_power_energy.csv
results/baselines_u280/ViTeGNN/raw_latency_power_energy.csv
results/baselines_u280/RTGA/raw_latency_power_energy.csv
results/baselines_u280/verify_summary.csv
results/derived_comparison_figures/fig10_speedup_tglite_cpu.csv
results/derived_comparison_figures/fig11_speedup_matg.csv
results/derived_comparison_figures/fig12_energy_tempgnn.csv
```

Expected: MATG, ViTeGNN, and RTGA rows report reproduced U280 timing PASS and golden fixture PASS. The raw-to-figure outputs reproduce Fig.10/Fig.11/Fig.12 from measured-input CSVs within the stated thresholds.

## Optional U280 Board Validation

If a reviewer has an Alveo U280 with the matching platform:

```bash
source /opt/xilinx/xrt/setup.sh
make u280-run U280_DEVICE=0
make u280-layout
```

Packaged evidence:

```text
results/board_u280/summary.json
results/board_u280/smoke.log
results/board_u280/tbscale.log
results/board_u280/maxbatch.log
results/board_u280/layout_smoke.log
results/board_u280/tempgnn_u280_fpga_layout.png
```

Expected U280 forward-path values:

| Metric | Value |
| --- | ---: |
| Frequency | 225 MHz |
| Timing | PASS |
| WNS | +0.016 ns |

The board logs should show PASS against the packaged golden fixed-point fixtures.

## Optional FPGA Rebuild

Rebuilding is not required for the default review because Vitis implementation is slow and environment-sensitive.

```bash
source /opt/xilinx/xrt/setup.sh
source /tools/Xilinx/Vitis/2023.2/settings64.sh
make u280-build \
  U280_PLATFORM=/opt/xilinx/platforms/xilinx_u280_gen3x16_xdma_1_202211_1/xilinx_u280_gen3x16_xdma_1_202211_1.xpfm
```

The recorded build used Vitis/Vivado 2023.2, XRT 2.16.204, and the `xilinx_u280_gen3x16_xdma_1_202211_1` platform. See `ENVIRONMENT.md` for OS, compiler, XRT, Vitis, platform, and setup-command details.

## Packaged FPGA Artifact

The package keeps one runnable U280 FPGA artifact under `build/`: the forward-path xclbin and its XRT host. The reviewer-facing summary reports frequency and timing status.

## Bridge Evidence

| Bridge | Evidence |
| --- | --- |
| Artifacts Available | source, scripts, tests, fixtures, generated CSV/SVG, figure-data CSVs, U280 logs, xclbin, and reports |
| Artifacts Evaluated Functional | unit tests, figure generation, Q14 profiling path, U280 forward-path board PASS logs, FPGA baseline measurement verification |
| Results Reproduced | regenerated motivation, speedup, energy, ablation, sensitivity figures, and baseline measurement tables |

Reviewer-facing summary files:

```text
results/ae_report/AE_BRIDGE_CLAIMS.md
results/ae_report/ae_summary.md
results/ae_report/FULL_PAPER_RESULTS.md
results/ae_report/U280_AE_RUNBOOK.md
```
