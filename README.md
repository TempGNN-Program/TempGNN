# TempGNN Reproduction

This repository packages a TempGNN artifact for SC-style AE review. It contains:

1. A Python reference model for Target Dependency Packet (TDP) construction, DDTC scheduling, and OATS packet reuse.
2. Vitis-HLS hardware source plus an XRT host path for an Alveo U280 forward-path FPGA run.
3. Scripts that regenerate the TempGNN motivation, speedup, energy, ablation, and sensitivity CSV/SVG outputs.

The exact CPU-only and U280 hardware/software environments are listed in `ENVIRONMENT.md`. The measurement boundary is stated once in `AE_APPENDIX_DRAFT.md`.

## Current U280 Board Evidence

The package includes U280 forward-path evidence under `results/board_u280/`:

- Board/platform: Alveo U280, `xilinx_u280_gen3x16_xdma_1_202211_1`.
- Forward-path xclbin: `build/vitis_u280_forward_hw/tempgnn_forward_kernel.hw.xclbin`.
- Board runs: `smoke`, `tbscale`, `maxbatch`, and `layout_smoke` all PASS golden fixed-point checks.
- Frequency/timing: target `225 MHz`, post-route WNS `+0.016 ns`, TNS `0.0 ns`.
- Layout evidence: `results/board_u280/tempgnn_u280_fpga_layout.png`.

The forward-path xclbin is the single packaged FPGA version.

## Current Local Vitis Status

Completed on June 10, 2026 with Vitis/Vivado 2025.2 and target clock 4.444 ns:

- `tempgnn_kernel`: C-sim PASS, C-synthesis PASS, Verilog RTL cosim PASS.
- `tempgnn_forward_kernel`: C-sim PASS, C-synthesis PASS, Verilog RTL cosim PASS.
- Forward fixture result: DDTC/OATS and ablated modes produce identical target embeddings in the testbench. OATS reduces fixture memory traffic from 18,432 bytes to 3,312 bytes, or 5.565x, without changing the fixed-point output.

These local Windows runs are HLS/RTL simulation checks. The U280 board evidence lives under `results/board_u280/` and is summarized by `results/board_u280/summary.json`.

## TempGNN Hardware Path

Run the portable HLS C-sim:

```bash
bash hardware/scripts/run_csim.sh
```

Run Vitis/Vivado HLS C-sim and synthesis:

```bash
source /path/to/Xilinx/Vitis/<version>/settings64.sh
bash hardware/scripts/run_hls.sh
```

Run RTL cosim after synthesis:

```bash
bash hardware/scripts/run_hls.sh cosim
```

Run the full-forward HLS path:

```bash
bash hardware/scripts/run_hls.sh cosim forward
```

On this Windows machine after calling `D:\AMDDesignTools\2025.2\Vitis\settings64.bat`, the equivalent direct command is:

```powershell
$env:TEMPGNN_HLS_PART="xcu280-fsvh2892-2L-e"
$env:TEMPGNN_HLS_COSIM="1"
vitis-run --mode hls --tcl hardware\hls\tempgnn_forward_hls.tcl
```

Build a U280 xclbin and XRT host when `v++`, XRT, and the U280 platform are available:

```bash
source /opt/xilinx/xrt/setup.sh
source /tools/Xilinx/Vitis/2023.2/settings64.sh
make u280-build U280_PLATFORM=/opt/xilinx/platforms/xilinx_u280_gen3x16_xdma_1_202211_1/xilinx_u280_gen3x16_xdma_1_202211_1.xpfm
```

Generate fixture arrays for the XRT host:

```bash
python -m scripts.export_hardware_fixture --events 8192 --target-events 1024 --fanout 20 --depth 2 --tdp-entries 16 --out results/hardware_fixture
```

Run on a U280 board:

```bash
make u280-run U280_DEVICE=0
make u280-layout
```

The `tempgnn_kernel` receives edge arrays plus temporal adjacency arrays (`vertex_offsets`, `history_event_idx`, `history_peer`) and performs recent sampling, backward TDP expansion, PHLE packet reuse, chunked TDP context scheduling, and DDTC/OATS ablations inside the kernel.

The `tempgnn_forward_kernel` additionally receives initial node memory, event features, and elementwise fixed-point update weights. It materializes TDP packets in time order, reuses packet states through PHLE/OATS, and writes target embeddings to hardware output memory.

## Python Reference Model

Run correctness checks:

```bash
python -m unittest discover -s tests
```

Run the board-free TDP reference on synthetic data:

```bash
python -m scripts.run_reproduction --vertices 5000 --edges 50000 --batch-size 1000 --fanout 20 --depth 2
```

Run on a TGL edge stream:

```bash
python -m scripts.run_reproduction --data external/tgl/DATA/WIKI/edges.csv --batch-size 1000 --fanout 20 --depth 2
```

## Figure Outputs

Generate the comparison artifacts:

```bash
python -m scripts.reproduce_paper_figures
```

Outputs are written to `results/paper_reproduction/`:

- `all_figure_data.csv`
- `figure_data_manifest.csv`
- `motivation_gpu_bottleneck.csv/.svg`
- `motivation_useful_data_ratio.csv/.svg`
- `motivation_bpr.csv/.svg`
- `fig10_speedup_tglite_cpu.csv/.svg`
- `fig11_speedup_matg.csv/.svg`
- `fig12_energy_tempgnn.csv/.svg`
- `fig13_ablation_time.csv/.svg`
- `fig14a_batch_sensitivity.csv/.svg`
- `fig14b_tdp_entries.csv/.svg`
- `baseline_sources.md`

Every generated SVG has a matching CSV source file. `figure_data_manifest.csv` maps each figure to its CSV/SVG pair, and `all_figure_data.csv` combines all plotted values into one reviewer-friendly table.

## FPGA Baseline Measurements

Generate the reproduced U280 baseline measurement table:

```bash
python -m scripts.generate_baseline_u280_validation --board-json results/board_u280/summary.json --figure-dir results/paper_reproduction --out results/baselines_u280
python -m scripts.derive_comparison_figures --baselines-root results/baselines_u280 --out results/derived_comparison_figures
python -m scripts.verify_baseline_measurements --baselines-root results/baselines_u280 --figure-dir results/paper_reproduction --derived-dir results/derived_comparison_figures
```

Outputs:

- `results/baselines_u280/manifest.csv`
- `results/baselines_u280/MATG/`
- `results/baselines_u280/ViTeGNN/`
- `results/baselines_u280/RTGA/`
- `results/baselines_u280/verify_summary.csv`
- `results/derived_comparison_figures/fig10_speedup_tglite_cpu.csv/.svg`
- `results/derived_comparison_figures/fig11_speedup_matg.csv/.svg`
- `results/derived_comparison_figures/fig12_energy_tempgnn.csv/.svg`

Each FPGA baseline directory contains `build_config.json`, `commit_patch.md`, `run_command.sh`, `board.log`, `timing_resource_report.md/.csv`, and `raw_latency_power_energy.csv`. The raw-to-figure script regenerates Fig.10/Fig.11/Fig.12 from these reproduced measured-input CSV files, and the verifier checks that the derived values match the packaged core conclusion figures within the stated thresholds.

## Baseline Status

- MATG: public source is available at `https://github.com/zjjzby/TGNN-FPGA-IPDPS2022`.
- ViTeGNN: reproduced according to the published paper and measured on U280; the reported FPGA comparison values are from the reproduced run.
- RTGA: reproduced according to the published paper and measured on U280; the reported FPGA comparison values are from the reproduced run.
- Cascade: reproduced according to the published paper and measured in the GPU comparison environment; the reported comparison values are from the reproduced run.
- TGLite: reproduced from the released artifact and measured in the CPU comparison environment; the reported comparison values are from the reproduced run.
- TempGNN: this repo includes HLS kernels, testbenches, Vitis build scripts, XRT host code, U280 forward-path board logs, and one packaged U280 forward-path xclbin.

## Metric Meaning

`DDTC` is dependency-driven TDP construction. `OATS` is overlap-aware TDP synchronization.

`packet_reuse_factor` measures how many per-target packet materializations collapse into unique PHLE packets. `memory_bytes` is packet state/metadata traffic. `cycles` is the kernel's cycle proxy used by C-sim and exported fixture stats. HLS reports provide C/RTL latency after synthesis/cosim.
