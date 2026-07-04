# Artifact Description Appendix Draft

## 1. Summary Of Experiments Reported

This artifact supports the TempGNN evaluation with three evidence layers:

1. A runnable software model for TDP construction, DDTC scheduling, OATS packet reuse, and real edge-stream overlap profiling.
2. A U280 forward-path FPGA artifact with HLS source, XRT host code, golden fixtures, board logs, timing evidence, and layout rendering.
3. Regenerated CSV/SVG outputs for the motivation, speedup, energy, ablation, sensitivity, and FPGA baseline measurement results.

The artifact is intended to support:

- Artifacts Available.
- Artifacts Evaluated Functional.
- Results Reproduced for the packaged figure outputs.

The measurement boundary for the figure outputs is stated in `AE_APPENDIX_DRAFT.md`.

Prepared AE tarball:

```text
tempgnn_ae_u280_measured_20260705_single_fpga.tgz
```

The exact CPU-only and U280 hardware/software environment is recorded in `ENVIRONMENT.md`.

## 2. Artifact Location

GitHub repository:

```text
https://github.com/TempGNN-Program/TempGNN
```

Reviewer-downloadable AE package:

```text
https://github.com/TempGNN-Program/TempGNN/raw/main/ae_export/tempgnn_ae_u280_measured_20260705_single_fpga.tgz
```

For badge submission, the GitHub repository should be referenced together with a DOI-backed archive such as Zenodo, Figshare, or the conference artifact repository.

## 3. Baseline Experimental Setup And Modifications

### Hardware

The measured FPGA hardware evidence uses:

- FPGA board: AMD/Xilinx Alveo U280.
- Device: `xcu280-fsvh2892-2L-e`.
- Platform: `xilinx_u280_gen3x16_xdma_1_202211_1`.
- Shell: `xilinx_u280_gen3x16_xdma_base_1`.
- Host used in the recorded run: `u280-ae-host`.

The measured forward-path U280 build is the single packaged FPGA version. It uses a 225 MHz kernel target and meets timing:

| Metric | Value |
| --- | ---: |
| Target frequency | 225 MHz |
| WNS | +0.016 ns |
| TNS | 0.0 ns |
| WHS | +0.006 ns |
| Timing status | PASS |

### Operating System And Toolchain

The recorded U280 run used:

- Linux x86_64.
- AMD/Xilinx Vitis/Vivado 2023.2.
- XRT 2.16.204.
- Platform package `xilinx_u280_gen3x16_xdma_1_202211_1`.

Typical U280 setup commands:

```bash
source /opt/xilinx/xrt/setup.sh
source /tools/Xilinx/Vitis/2023.2/settings64.sh
```

The default Python-only workflow requires:

- Python 3.10 or newer.
- GNU Make.
- Bash.

The core CSV/SVG generation path uses only the standard Python library. Optional layout rendering can use matplotlib when PNG/SVG layout regeneration is requested.

### Applications And Baselines

The artifact contains:

- TempGNN Python reference model for TDP, DDTC, and OATS.
- Vitis HLS source for the TempGNN hardware path.
- XRT host code and golden hardware fixtures.
- Figure-generation scripts for MATG, ViTeGNN, RTGA, Cascade, TGLite-CPU, TempGNN-G, and TempGNN comparisons.
- U280 reproduced FPGA baseline measurement evidence for MATG, ViTeGNN, and RTGA.

### Models And Datasets

The figure outputs cover four TGNN models:

- JODIE.
- TGAT.
- TGN.
- APAN.

Dataset labels:

- Wikipedia or WK.
- MOOC or MC.
- Reddit or RT.
- LastFM or LM.
- WikiTalk or WT.
- GDELT or GT.

The Q14 overlap-statistics profiling path uses real TGL edge streams when the TGL edge CSV files are available. In the packaged run, WIKI, MOOC, and REDDIT profiling outputs are included. Full raw datasets are not included in the tarball.

## 4. Evaluation Methodology

The artifact reports three types of results:

1. U280 forward-path hardware evidence:
   xclbin, operating frequency/timing reports, XRT board logs, golden-output PASS checks, and FPGA layout rendering.

2. Real edge-stream profiling:
   packet hit rate, reuse rate, collision behavior, synchronization stalls, and off-chip access reduction from TGL edge streams. Latency for this path uses a U280 225 MHz cycle model.

3. Regenerated figure outputs:
   motivation figures and Fig.10-Fig.14 CSV/SVG files.

4. FPGA baseline measurements:
   MATG, ViTeGNN, and RTGA reproduced U280 measurement inputs with corresponding Fig.11/Fig.12 values.

Main regenerated outputs:

- `results/paper_reproduction/figure_data_manifest.csv`.
- `results/paper_reproduction/all_figure_data.csv`.
- `results/paper_reproduction/motivation_gpu_bottleneck.csv/.svg`.
- `results/paper_reproduction/motivation_useful_data_ratio.csv/.svg`.
- `results/paper_reproduction/motivation_bpr.csv/.svg`.
- `results/paper_reproduction/fig10_speedup_tglite_cpu.csv/.svg`.
- `results/paper_reproduction/fig11_speedup_matg.csv/.svg`.
- `results/paper_reproduction/fig12_energy_tempgnn.csv/.svg`.
- `results/paper_reproduction/fig13_ablation_time.csv/.svg`.
- `results/paper_reproduction/fig14a_batch_sensitivity.csv/.svg`.
- `results/paper_reproduction/fig14b_tdp_entries.csv/.svg`.
- `results/baselines_u280/manifest.csv/.md`.
- `results/baselines_u280/MATG/raw_latency_power_energy.csv`.
- `results/baselines_u280/ViTeGNN/raw_latency_power_energy.csv`.
- `results/baselines_u280/RTGA/raw_latency_power_energy.csv`.
- `results/derived_comparison_figures/fig10_speedup_tglite_cpu.csv/.svg`.
- `results/derived_comparison_figures/fig11_speedup_matg.csv/.svg`.
- `results/derived_comparison_figures/fig12_energy_tempgnn.csv/.svg`.

## 5. Artifact Package Contents

Important package directories:

```text
ENVIRONMENT.md                   Recorded CPU-only and U280 hardware/software environment
scripts/                         Reproduction, profiling, report, and packaging scripts
tempgenn/                        Python TDP, OATS, and DDTC models
hardware/                        HLS kernel, Vitis Makefile, host code, and testbench
tests/                           Unit tests
results/paper_reproduction/      Regenerated CSV/SVG figures
results/q14_real_tgl_edges/      Real edge-stream overlap/Q14 profiling outputs
results/baselines_u280/       Per-baseline reproduced U280 measurement directories, manifest, raw CSVs
results/derived_comparison_figures/ Raw-derived Fig.10/Fig.11/Fig.12 CSV/SVG files
results/board_u280/              U280 forward-path logs, summary, layout figure
results/ae_report/               AE README, bridge claims, runbook, and summaries
build/vitis_u280_forward_hw/     Packaged U280 forward-path xclbin and XRT host
```

Large raw TGL datasets, Vitis implementation intermediates, legacy non-U280 binaries, and alternate FPGA build leftovers are excluded.

## 6. Notes On Reproducibility

The default AE workflow is CPU-only and can regenerate all CSV/SVG figures, run unit tests, profile real-edge overlap statistics when data are present, and regenerate the AE report.

The U280 workflow can either use the packaged xclbin/logs or rerun Vitis build and board execution if a reviewer has compatible U280 access. Rebuilding the FPGA design is not required for the default AE path because Vitis implementation can take multiple hours and depends on platform, license, and server configuration.
