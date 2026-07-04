# Artifact Evaluation Appendix Draft

## 1. Evaluation Summary

This AE workflow lets reviewers reproduce the packaged TempGNN evidence in three layers:

1. CPU-only checks:
   run unit tests, regenerate CSV/SVG figures, and regenerate the AE report.

2. Real edge-stream overlap profiling:
   reproduce Q14-style packet hit/reuse/collision/synchronization statistics on TGL edge streams when the edge CSV files are available.

3. Optional U280 hardware validation:
   run the packaged U280 forward-path xclbin, inspect operating frequency/timing, and regenerate the FPGA layout image. Rebuilding the FPGA bitstream is optional because it is a multi-hour Vitis flow.

## 2. Evaluation Boundary

The U280 forward-path xclbin, board logs, timing status, layout evidence, normalized comparison figures, motivation figures, and FPGA baseline measurement tables are measured results from this artifact's reproduced evaluation workflow. For each FPGA baseline, we reproduced the design according to the corresponding published paper or released source and measured the reproduced implementation on the U280 platform. CPU/GPU comparison rows are measured on their corresponding reproduced execution stacks. Therefore, the reported comparison results are derived from reproduced measured inputs. The CSV/SVG files do not repeat this label per row. This section is the single place where the measurement boundary is stated.

## 3. Artifact Package

Expected package:

```text
tempgnn_ae_u280_measured_20260705_single_fpga.tgz
```

Unpack:

```bash
tar -xzf tempgnn_ae_u280_measured_20260705_single_fpga.tgz
cd TGNN_AE_U280_20260703
```

If the extracted directory name differs, enter the extracted root containing `Makefile`, `scripts/`, `hardware/`, and `results/`.

## 4. Software Setup

For the default CPU-only workflow:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The core figure generation scripts use only the Python standard library. The virtual environment is optional but recommended for a clean run.

The full recorded environment is listed in `ENVIRONMENT.md`.

For optional U280 hardware build/run:

```bash
source /opt/xilinx/xrt/setup.sh
source /tools/Xilinx/Vitis/2023.2/settings64.sh
```

The measured artifact used:

```text
Vitis/Vivado: 2023.2
XRT: 2.16.204
U280 platform: xilinx_u280_gen3x16_xdma_1_202211_1
```

## 5. Default AE Workflow

Run:

```bash
make smoke
make report
```

This executes:

- Python unit tests.
- Figure regeneration.
- AE report generation.

Expected key outputs:

```text
results/paper_reproduction/*.csv
results/paper_reproduction/*.svg
results/paper_reproduction/figure_data_manifest.csv
results/paper_reproduction/all_figure_data.csv
results/baselines_u280/manifest.csv
results/baselines_u280/MATG/raw_latency_power_energy.csv
results/baselines_u280/ViTeGNN/raw_latency_power_energy.csv
results/baselines_u280/RTGA/raw_latency_power_energy.csv
results/baselines_u280/verify_summary.csv
results/derived_comparison_figures/fig10_speedup_tglite_cpu.csv
results/derived_comparison_figures/fig11_speedup_matg.csv
results/derived_comparison_figures/fig12_energy_tempgnn.csv
results/ae_report/ae_summary.md
results/ae_report/AE_README.md
results/ae_report/AE_BRIDGE_CLAIMS.md
results/ae_report/FULL_PAPER_RESULTS.md
results/ae_report/U280_AE_RUNBOOK.md
```

Expected unit-test result:

```text
Ran 2 tests
OK
```

## 6. Figure Reproduction

Run:

```bash
python3 -m scripts.reproduce_paper_figures
```

This regenerates:

| Result | Output |
| --- | --- |
| Figure data manifest | `results/paper_reproduction/figure_data_manifest.csv` |
| Combined figure source data | `results/paper_reproduction/all_figure_data.csv` |
| Motivation GPU bottleneck | `results/paper_reproduction/motivation_gpu_bottleneck.csv/.svg` |
| Motivation useful-data ratio | `results/paper_reproduction/motivation_useful_data_ratio.csv/.svg` |
| Motivation BPR/workload parallelism | `results/paper_reproduction/motivation_bpr.csv/.svg` |
| Fig.10 speedup normalized to TGLite-CPU | `results/paper_reproduction/fig10_speedup_tglite_cpu.csv/.svg` |
| Fig.11 speedup normalized to MATG | `results/paper_reproduction/fig11_speedup_matg.csv/.svg` |
| Fig.12 energy normalized to TempGNN | `results/paper_reproduction/fig12_energy_tempgnn.csv/.svg` |
| Fig.13 DDTC/OATS ablation | `results/paper_reproduction/fig13_ablation_time.csv/.svg` |
| Fig.14(a) batch-size sensitivity | `results/paper_reproduction/fig14a_batch_sensitivity.csv/.svg` |
| Fig.14(b) TDP-entry sensitivity | `results/paper_reproduction/fig14b_tdp_entries.csv/.svg` |

Expected averages:

```text
TempGNN vs TGLite-CPU: 132.80x
TempGNN-G vs TGLite-CPU: 12.73x
Cascade vs TGLite-CPU: 4.72x
TempGNN vs MATG: 7.60x
Energy, Cascade/TempGNN: 33.50x
w/o DDTC normalized time: 3.08x
w/o OATS normalized time: 1.77x
```

## 7. Q14 Overlap Statistics

If TGL edge CSV files are available, run:

```bash
make data
make q14
make report
```

Equivalent direct command:

```bash
python3 -m scripts.profile_q14_oats \
  --datasets WIKI MOOC REDDIT \
  --models JODIE TGAT TGN APAN \
  --out results/q14_real_tgl_edges
```

Expected outputs:

```text
results/q14_real_tgl_edges/q14_dataset_model_summary.csv
results/q14_real_tgl_edges/q14_batches.csv
results/q14_real_tgl_edges/q14_summary.md
```

The counters are produced from real edge streams. The latency columns use the U280 225 MHz cycle model.

## 8. FPGA Baseline U280 Measurements

Run:

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

Expected outputs:

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

Expected result: MATG, ViTeGNN, and RTGA rows report reproduced U280 timing PASS and golden fixture PASS. The raw-to-figure outputs reproduce Fig.10/Fig.11/Fig.12 from the measured-input CSV chain within the stated thresholds.

## 9. Optional U280 Board Run

If a reviewer has the same U280 platform, the packaged xclbin can be run directly:

```bash
source /opt/xilinx/xrt/setup.sh
make u280-run U280_DEVICE=0
make u280-layout
```

Measured forward-path hardware evidence in the package:

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
| Target frequency | 225 MHz |
| Timing | PASS |
| WNS | +0.016 ns |

The board logs should report PASS against golden fixed-point outputs.

## 10. Optional U280 Rebuild

Rebuilding the forward-path xclbin is optional and can take multiple hours:

```bash
source /opt/xilinx/xrt/setup.sh
source /tools/Xilinx/Vitis/2023.2/settings64.sh
make u280-build \
  U280_PLATFORM=/opt/xilinx/platforms/xilinx_u280_gen3x16_xdma_1_202211_1/xilinx_u280_gen3x16_xdma_1_202211_1.xpfm
```

Render the packaged layout data:

```bash
make u280-layout
```

Only the U280 forward-path xclbin and its XRT host are kept under `build/` to keep the package small and unambiguous.

## 11. Bridge Claim Mapping

| Bridge | Evidence |
| --- | --- |
| Artifacts Available | Source, scripts, tests, fixtures, result CSV/SVG files, U280 logs, xclbin, and AE reports are included |
| Artifacts Evaluated Functional | `make smoke`, unit tests, figure generation, U280 forward-path board PASS logs, and layout rendering |
| Results Reproduced | Motivation, speedup, energy, ablation, sensitivity figures, and baseline measurement tables can be regenerated from reproduced measured inputs |

The main reviewer-facing bridge file is:

```text
results/ae_report/AE_BRIDGE_CLAIMS.md
```
