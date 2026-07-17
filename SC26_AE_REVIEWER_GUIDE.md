# TempGNN SC26 AE Reviewer Guide

This document is a reviewer-facing guide for evaluating the TempGNN artifact. It complements `AD_APPENDIX_DRAFT.md` and `AE_APPENDIX_DRAFT.md`.

## What This Artifact Demonstrates

The artifact demonstrates three things:

1. TempGNN and three paper-based FPGA baseline reproductions can be executed
   and checked on the same U280 through one command.
2. The paper-reference execution, workload, GPU-overhead, speedup, energy,
   ablation, and sensitivity inputs can be regenerated from source-labeled
   Python constants as CSV/SVG files without running CPU or GPU baselines.
3. A bounded FPGA mechanism comparison can be rerun using four distinct U280 xclbins:
   TempGNN plus independent paper-based MATG, ViTeGNN, and RTGA reproductions.
   The fresh path records timing, total board power, checksums, post-route
   evidence, real-dataset-prefix provenance, and diagnostic normalized rows.

The measurement boundary is stated once in `AE_APPENDIX_DRAFT.md`. The exact
optional software-check and U280 environments are recorded in `ENVIRONMENT.md`.

## Package

```text
pap142_tempgnn_sc26_ae_u280.tgz
```

Unpack:

```bash
tar -xzf pap142_tempgnn_sc26_ae_u280.tgz
cd pap142_tempgnn_sc26_ae
```

## Core One-Command U280 Path

This is the recommended reviewer workflow. Credentials for the anonymous U280
account are delivered through the conference's private AE channel.

```bash
bash scripts/run_all.sh u280-core
```

The wrapper loads `/opt/xilinx/xrt/setup.sh` when necessary and uses device 0
with three repetitions. The explicit `make ae-core-u280` form can override
`U280_CORE_DEVICE` or `U280_CORE_REPETITIONS`.

The command generates paper-reference figures from code, runs TempGNN, MATG,
ViTeGNN, and RTGA on U280, validates every fresh measurement row, derives the
measured core comparison figures, and regenerates the AE report. It does not
execute a CPU or GPU performance baseline.

The command exits nonzero on missing artifacts, failed goldens, unstable
outputs, incomplete measurements, invalid timing provenance, or a failed
required paper-match gate when the strict target is selected. The default
target records numerical mismatch without hiding it. On success it finishes by writing:

```text
results/reviewer_u280_runs/<run-id>/verification.md
results/ae_report/ae_summary.md
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

## Generate Paper Figures From Code

```bash
python3 -m scripts.reproduce_paper_figures
```

Outputs:

| Result | File |
| --- | --- |
| Reconstructed 668-row source table | `results/paper_reproduction/paper_figure_values.csv` |
| Figure data manifest | `results/paper_reproduction/figure_data_manifest.csv` |
| Combined figure source data | `results/paper_reproduction/all_figure_data.csv` |
| Fig.2 execution breakdown | `results/paper_reproduction/fig2_execution_breakdown.svg` |
| Fig.4(a) BPR | `results/paper_reproduction/fig4a_branch_parallelism_ratio.svg` |
| Fig.9(b) GPU overhead | `results/paper_reproduction/fig9b_gpu_overhead_breakdown.svg` |
| Fig.10 speedup vs TGLite-CPU | `results/paper_reproduction/fig10_speedup_tglite_cpu.svg` |
| Fig.11 speedup vs MATG | `results/paper_reproduction/fig11_speedup_matg.svg` |
| Fig.12 energy vs TempGNN | `results/paper_reproduction/fig12_energy_tempgnn.svg` |
| Fig.13 DDTC/OATS ablation | `results/paper_reproduction/fig13_ablation_time.svg` |
| Fig.14(a) batch sensitivity | `results/paper_reproduction/fig14a_batch_sensitivity.svg` |
| Fig.14(b) TDP-entry sensitivity | `results/paper_reproduction/fig14b_tdp_entries.svg` |

Expected averages include:

```text
TempGNN vs TGLite-CPU: 132.80x
TempGNN vs MATG, explicit plotted AVG bar: 7.7889x
Paper prose for TempGNN vs MATG: 7.6x
Energy, Cascade/TempGNN, explicit plotted AVG bar: 33.545x
w/o DDTC normalized time: 3.08x
w/o OATS normalized time: 1.77x
```

The 668 reference records are structured constants in
`tempgenn/paper_reference_data.py`. The deterministic CSV/SVG outputs,
including `paper_figure_values.csv`, are included under
`results/paper_reproduction/` for direct inspection and are regenerated in
place with the recorded migration hash. Exact workbook cells and values
digitized from vector geometry have different `source_kind` values. The Fig.11 plot/prose difference
is retained rather than silently forced to match.

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

## Fresh U280 Mechanism Comparison

Remote U280 credentials are delivered through the conference's private AE
channel after reviewer assignment. The public repository intentionally contains
no login names, passwords, institutional hostnames, or personal SSH keys.

```bash
source /opt/xilinx/xrt/setup.sh
make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3
```

Outputs:

```text
results/reviewer_u280_runs/<run-id>/provenance.json
results/reviewer_u280_runs/<run-id>/raw/*/measurements.csv
results/reviewer_u280_runs/<run-id>/baselines_u280/
results/reviewer_u280_runs/<run-id>/derived_comparison_figures/
results/reviewer_u280_runs/<run-id>/verification.md
```

The audited packaged final run is
`results/reviewer_u280_runs/20260717T024537Z/`. It contains 72 rows per
implementation and 288 rows total; every row passes golden, repeat, and timing
validation. The measured all-workload TempGNN/MATG average speedup is
`7.8889x`. Its paper-figure tolerance diagnostic remains FAIL and is retained.

Expected: preflight prints four different xclbin SHA256 values. Every raw row
has a kernel and embedding checksum, repeat-consistency status, board-power
samples, xclbin link request, Vivado-connected post-route clock, WNS/TNS, real
input URL, and input/fixture hashes. Each implementation must keep one
timing-closed clock across all rows; its actual clock remains in every row and
the workflow performs no frequency rescaling.
`verification.md` reports the
observed comparison error. The command never substitutes paper-reference
values. `make ae-core-u280-strict` adds the numerical paper-match gate and
makes a tolerance FAIL fail the command.

This path is not paper-equivalent: it uses bounded real-data prefixes,
8-dimensional Q10 kernels, deterministic stand-in weights, and `xbutil` power,
whereas the paper uses complete model configurations, default 32-bit floating
point, full evaluation streams, and post-route Vivado power estimates. It does
not currently assert the Results Reproduced bridge.

## TempGNN Sanity Validation

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
results/board_u280/tempgnn_21cu_wk_tgn_100iter.log
results/board_u280/tempgnn_21cu_input_switch.log
results/board_u280/tempgnn_u280_fpga_layout.png
```

Expected U280 forward-path values:

| Metric | Value |
| --- | ---: |
| Reviewer TempGNN frequency | 168 MHz (21 CUs) |
| Reviewer TempGNN timing | PASS |
| Reviewer TempGNN WNS/TNS | +0.002 ns / 0.0 ns |
| Delivered WK/TGN mean, 100 iterations | 1.412534 ms |
| Fresh all-workload TempGNN/MATG average | 7.8889x |
| Historical sanity frequency | 225 MHz |
| Historical sanity WNS | +0.016 ns |

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

## Packaged FPGA Artifacts

The historical TempGNN sanity logs and layout remain under
`results/board_u280/`. Four runnable, metadata-normalized comparison artifacts
are under `artifacts/u280/`, with separate xclbins and build provenance.
Baseline source and reproduction scope are documented in
`hardware/baselines/README.md`.

## Bridge Evidence

| Bridge | Evidence |
| --- | --- |
| Artifacts Available | source, scripts, tests, fixtures, generated CSV/SVG, figure-data CSVs, U280 logs, xclbin, and reports |
| Artifacts Evaluated Functional | unit tests, C-sim, four distinct U280 xclbins, checksum validation, post-route reports, and fresh power/latency rows |
| Results Reproduced | not currently asserted; the fresh four-xclbin path is mechanism-level evidence and is explicitly marked not paper-equivalent |

Reviewer-facing summary files:

```text
results/ae_report/AE_BRIDGE_CLAIMS.md
results/ae_report/ae_summary.md
results/ae_report/FULL_PAPER_RESULTS.md
results/ae_report/U280_AE_RUNBOOK.md
```
