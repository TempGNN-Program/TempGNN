# Full TempGNN Result Inventory

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
python3 -m scripts.make_ae_report --q14-summary results\q14_real_tgl_edges\q14_dataset_model_summary.csv --board-json results\board_u280\summary.json --out results\ae_report
python3 -m scripts.render_fpga_layout --summary results/board_u280/summary.json
```
