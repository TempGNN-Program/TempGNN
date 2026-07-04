# U280 AE Runbook

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
python3 -m scripts.profile_q14_oats \
  --datasets WIKI MOOC REDDIT \
  --models JODIE TGAT TGN APAN \
  --out results/q14_real_tgl_edges
```

Output:

- `results/q14_real_tgl_edges/q14_dataset_model_summary.csv`
- `results/q14_real_tgl_edges/q14_batches.csv`
- `results/q14_real_tgl_edges/q14_summary.md`

Counters are produced from real edge streams. Latency uses the 225 MHz U280 cycle model.

## Experiment 9: FPGA Baseline U280 Measurements

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
make u280-build \
  U280_PLATFORM=/opt/xilinx/platforms/xilinx_u280_gen3x16_xdma_1_202211_1/xilinx_u280_gen3x16_xdma_1_202211_1.xpfm
make u280-run U280_DEVICE=0
make u280-layout
```

The measured run writes `results/board_u280/*.log` and `results/board_u280/summary.json`. If routed LOC data are available, the layout image is written to `results/board_u280/tempgnn_u280_fpga_layout.png/.svg`.
