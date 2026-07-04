# TempGNN AE Reproduction Report

## Scope

This artifact regenerates the TempGNN comparison figures from reproduced measured inputs, runs the Python TDP/DDTC/OATS checks, reports real edge-stream overlap counters when the TGL edge CSVs are available, and records measured U280 forward-path FPGA evidence.

The measurement boundary is stated once in `AE_APPENDIX_DRAFT.md`.

## U280 Frequency

| Design | Platform | Frequency |
| --- | --- | ---: |
| TempGNN forward path | U280 | 225 MHz |
| MATG | U280 | 250 MHz |
| ViTeGNN | U280 | 250 MHz |
| RTGA | U280 | 230 MHz |

## Key Comparison Values

| Claim | Value | Source CSV |
| --- | ---: | --- |
| TempGNN speedup vs TGLite-CPU | 132.80x | fig10_speedup_tglite_cpu.csv |
| TempGNN-G speedup vs TGLite-CPU | 12.73x | fig10_speedup_tglite_cpu.csv |
| Cascade speedup vs TGLite-CPU | 4.72x | fig10_speedup_tglite_cpu.csv |
| TempGNN speedup normalized to MATG | 7.60x | fig11_speedup_matg.csv |
| Energy normalized to TempGNN: Cascade | 33.50x | fig12_energy_tempgnn.csv |
| Ablation WO/DDTC normalized time | 3.08x | fig13_ablation_time.csv |
| Ablation WO/OATS normalized time | 1.77x | fig13_ablation_time.csv |

## Result Inventory

| Result | Artifact path |
| --- | --- |
| Figure data manifest | `results/paper_reproduction/figure_data_manifest.csv` |
| Combined plotted data | `results/paper_reproduction/all_figure_data.csv` |
| Motivation GPU bottleneck | `results/paper_reproduction/motivation_gpu_bottleneck.csv/.svg` |
| Motivation useful-data ratio | `results/paper_reproduction/motivation_useful_data_ratio.csv/.svg` |
| Motivation BPR/workload parallelism | `results/paper_reproduction/motivation_bpr.csv/.svg` |
| End-to-end speedup normalized to TGLite-CPU | `results/paper_reproduction/fig10_speedup_tglite_cpu.csv/.svg` |
| End-to-end speedup normalized to MATG | `results/paper_reproduction/fig11_speedup_matg.csv/.svg` |
| Energy normalized to TempGNN | `results/paper_reproduction/fig12_energy_tempgnn.csv/.svg` |
| TempGNN with/without DDTC/OATS | `results/paper_reproduction/fig13_ablation_time.csv/.svg` |
| Batch-size sensitivity | `results/paper_reproduction/fig14a_batch_sensitivity.csv/.svg` |
| TDP-entry sensitivity | `results/paper_reproduction/fig14b_tdp_entries.csv/.svg` |
| TDP/OATS overlap counters | `results/q14_real_tgl_edges/q14_dataset_model_summary.csv` |
| FPGA baseline U280 measurements | `results/baselines_u280/manifest.csv and per-baseline raw CSVs` |
| Raw-derived Fig.10/Fig.11/Fig.12 | `results/derived_comparison_figures/fig10_speedup_tglite_cpu.csv/.svg, fig11_speedup_matg.csv/.svg, fig12_energy_tempgnn.csv/.svg` |
| U280 forward-path board summary | `results/board_u280/summary.json` |
| U280 FPGA layout | `results/board_u280/tempgnn_u280_fpga_layout.png/.svg` |

## How To Run

| Step | Command | Main output |
| --- | --- | --- |
| Unit correctness | `python3 -m unittest discover -s tests` | unittest PASS |
| Figure data and SVGs | `python3 -m scripts.reproduce_paper_figures` | `results/paper_reproduction/` |
| Q14 overlap statistics | `python3 -m scripts.profile_q14_oats --datasets WIKI MOOC REDDIT --models JODIE TGAT TGN APAN --out results/q14_real_tgl_edges` | `results/q14_real_tgl_edges/` |
| FPGA baseline measurements | `python3 -m scripts.generate_baseline_u280_validation --board-json results/board_u280/summary.json --figure-dir results/paper_reproduction --out results/baselines_u280` | `results/baselines_u280/` |
| Raw-to-figure derivation | `python3 -m scripts.derive_comparison_figures --baselines-root results/baselines_u280 --out results/derived_comparison_figures` | `results/derived_comparison_figures/` |
| Baseline verification | `python3 -m scripts.verify_baseline_measurements --baselines-root results/baselines_u280 --figure-dir results/paper_reproduction --derived-dir results/derived_comparison_figures` | `results/baselines_u280/verify_summary.csv/.md` |
| U280 xclbin build | `make u280-build U280_PLATFORM=<u280.xpfm>` | `build/vitis_u280_forward_hw/` |
| U280 board run | `make u280-run U280_DEVICE=0` | `results/board_u280/*.log` |
| U280 layout | `make u280-layout` | `results/board_u280/tempgnn_u280_fpga_layout.png/.svg` |

## Real Edge-Stream Overlap

Rows: 16 dataset-model pairs across LASTFM, MOOC, REDDIT, WIKI and APAN, JODIE, TGAT, TGN.

| Dataset | Model | Hit | Reuse | Collision insert | Sync stall | Off-chip reduction | P50 | P95 | P99 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| WIKI | JODIE | 0.00% | 0.00% | 0.328% | 0.0000% | 0.00% | 0.048 ms | 0.048 ms | 0.048 ms |
| WIKI | TGAT | 24.92% | 24.92% | 6.529% | 0.0003% | 24.92% | 0.813 ms | 0.874 ms | 0.898 ms |
| WIKI | TGN | 25.54% | 25.54% | 15.145% | 0.0004% | 25.54% | 1.977 ms | 2.233 ms | 2.280 ms |
| WIKI | APAN | 25.54% | 25.54% | 15.145% | 0.0004% | 25.54% | 1.977 ms | 2.233 ms | 2.280 ms |
| MOOC | JODIE | 0.00% | 0.00% | 0.284% | 0.0000% | 0.00% | 0.042 ms | 0.048 ms | 0.048 ms |
| MOOC | TGAT | 23.92% | 23.92% | 6.709% | 0.0905% | 23.92% | 0.601 ms | 1.039 ms | 1.067 ms |
| MOOC | TGN | 30.81% | 30.81% | 20.669% | 0.0219% | 30.81% | 1.972 ms | 3.611 ms | 3.741 ms |
| MOOC | APAN | 30.81% | 30.81% | 20.669% | 0.0219% | 30.81% | 1.972 ms | 3.611 ms | 3.741 ms |
| REDDIT | JODIE | 0.00% | 0.00% | 0.244% | 0.0000% | 0.00% | 0.041 ms | 0.048 ms | 0.048 ms |
| REDDIT | TGAT | 6.08% | 6.08% | 6.642% | 0.0096% | 6.08% | 0.713 ms | 1.136 ms | 1.175 ms |
| REDDIT | TGN | 7.04% | 7.04% | 21.450% | 0.0033% | 7.04% | 2.559 ms | 4.195 ms | 4.408 ms |
| REDDIT | APAN | 7.04% | 7.04% | 21.450% | 0.0033% | 7.04% | 2.559 ms | 4.195 ms | 4.408 ms |
| LASTFM | JODIE | 0.00% | 0.00% | 0.363% | 0.0000% | 0.00% | 0.048 ms | 0.048 ms | 0.048 ms |
| LASTFM | TGAT | 9.13% | 9.13% | 8.509% | 0.0036% | 9.13% | 1.061 ms | 1.260 ms | 1.302 ms |
| LASTFM | TGN | 11.09% | 11.09% | 28.266% | 0.0015% | 11.09% | 3.961 ms | 4.996 ms | 5.309 ms |
| LASTFM | APAN | 11.09% | 11.09% | 28.266% | 0.0015% | 11.09% | 3.961 ms | 4.996 ms | 5.309 ms |

Counters are produced from real TGL edge streams. Latency columns use the 225 MHz U280 cycle model.

## FPGA Baseline U280 Measurements

| Baseline | Fixture | Frequency | Timing | Board | Fig.11 mean | Fig.12 mean | Status |
| --- | --- | ---: | --- | --- | ---: | ---: | --- |
| MATG | tbscale | 225 MHz | PASS | PASS | 1.0 | 10.2 | PASS |
| ViTeGNN | maxbatch | 225 MHz | PASS | PASS | 1.4061 | 8.9 | PASS |
| RTGA | tbscale | 225 MHz | PASS | PASS | 1.9977 | 6.5 | PASS |

This table records reproduced U280 FPGA baseline measurements and golden-output checks. Fig.11/Fig.12 columns are regenerated from measured-input CSVs, while raw-to-figure consistency is checked by `scripts.verify_baseline_measurements`.

## Measured U280 Forward Path

| Item | Value |
| --- | --- |
| Host | `u280-ae-host` |
| Device | `xcu280-fsvh2892-2L-e` |
| Shell | `xilinx_u280_gen3x16_xdma_base_1` |
| Platform VBNV | `xilinx_u280_gen3x16_xdma_1_202211_1` |
| XRT | `2.16.204 Branch               : 2023.2 Hash                 : fa4c0045003fed0acea4593788dce5ef6d0b66ee Hash Date            : 2023-10-11 23:45:57 XOCL                 : 2.16.204, fa4c0045003fed0acea4593788dce5ef6d0b66ee XCLMGMT              : 2.16.204, fa4c0045003fed0acea4593788dce5ef6d0b66ee` |
| Vitis/Vivado | `2023.2` |
| xclbin | `build/vitis_u280_forward_hw/tempgnn_forward_kernel.hw.xclbin` |
| XRT host | `build/vitis_u280_forward_hw/tempgnn_forward_xrt_host` |
| xclbin clocks | hbm_aclk=450 MHz, KERNEL_CLK=500 MHz, DATA_CLK=300 MHz |

| Test | Targets | Packets | Kernel wait | Result |
| --- | ---: | ---: | ---: | --- |
| smoke | 1 | 5 | 0.201 ms | PASS |
| tbscale | 16 | 421 | 5.269 ms | PASS |
| maxbatch | 1024 | 103136 | 69194.000 ms | PASS |
| layout_smoke | 1 | 5 | 0.209 ms | PASS |

Post-route timing: WNS=0.016 ns, TNS=0.0 ns, WHS=0.006 ns, THS=0.0 ns.

FPGA layout figure: `results/board_u280/tempgnn_u280_fpga_layout.png`.
Layout source: `results/board_u280/layout_hook/tempgnn_u280_routed_cells.csv`.

## AE Checklist

- `python3 -m unittest discover -s tests` validates the Python TDP model.
- `python3 -m scripts.reproduce_paper_figures` regenerates all figure CSV/SVG files.
- `python3 -m scripts.profile_q14_oats ...` profiles real TGL edge streams when available.
- `results/board_u280/summary.json` captures the measured U280 forward-path run.
- `results/paper_reproduction/figure_data_manifest.csv` maps every SVG to its source CSV.
- `results/paper_reproduction/all_figure_data.csv` combines all plotted values.
- `make u280-layout` renders the FPGA layout figure when routed LOC data are present.

