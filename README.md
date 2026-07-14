# TempGNN Reproduction

This repository packages a TempGNN artifact for SC-style AE review. It contains:

1. A Python reference model for Target Dependency Packet (TDP) construction, DDTC scheduling, and OATS packet reuse.
2. Vitis-HLS hardware source plus an XRT host path for an Alveo U280 forward-path FPGA run.
3. Independent paper-based MATG, ViTeGNN, and RTGA forward-path reproductions,
   plus a common U280 measurement workflow for the core FPGA comparisons.
4. Scripts that regenerate paper-reference CSV/SVG outputs from an anonymized,
   source-labeled numeric table.

The exact CPU-only and U280 hardware/software environments are listed in
`ENVIRONMENT.md`. The authoritative measurement boundary is stated in
`AE_APPENDIX_DRAFT.md` and summarized in the reference-data manifest.

## Current U280 Board Evidence

The package includes U280 forward-path evidence under `results/board_u280/`:

- Board/platform: Alveo U280, `xilinx_u280_gen3x16_xdma_1_202211_1`.
- Current reviewer-runnable xclbin:
  `artifacts/u280/TempGNN/bin/tempgnn_forward_kernel.hw.xclbin`.
- Board runs: `smoke`, `tbscale`, `maxbatch`, and `layout_smoke` all PASS golden fixed-point checks.
- Frequency/timing: target `225 MHz`, post-route WNS `+0.016 ns`, TNS `0.0 ns`.
- Layout evidence: `results/board_u280/tempgnn_u280_fpga_layout.png`.

This directory preserves the original TempGNN forward-path sanity logs and
layout evidence. Its older xclbin is omitted because its build metadata contains
an absolute home path; the current metadata-normalized, bitstream-verified
TempGNN xclbin is under `artifacts/u280/`. Fresh runs write new evidence under
`results/reviewer_u280_runs/`.

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

## Packaged Reference Figure Outputs

Regenerate the packaged reference CSV/SVG artifacts:

```bash
python -m scripts.reproduce_paper_figures
```

Outputs are written to `results/paper_reproduction/`:

- `all_figure_data.csv`
- `figure_data_manifest.csv`
- `fig2_execution_breakdown.csv/.svg`
- `fig4a_branch_parallelism_ratio.csv/.svg`
- `fig9b_gpu_overhead_breakdown.csv/.svg`
- `fig10_speedup_tglite_cpu.csv/.svg`
- `fig11_speedup_matg.csv/.svg`
- `fig12_energy_tempgnn.csv/.svg`
- `fig13_ablation_time.csv/.svg`
- `fig14a_batch_sensitivity.csv/.svg`
- `fig14b_tdp_entries.csv/.svg`
- `baseline_sources.md`

Every generated SVG has a matching CSV source file. The sole input is
`reference_inputs/paper_figure_values.csv`; each row records whether the value
is an exact author-workbook cell or an axis-calibrated recovery from an author
vector export. `reference_inputs/README.md` records source hashes, cell/geometry
locators, uncertainty, and the Fig.11 plot/prose discrepancy. No per-point value
is synthesized from a reported mean or range. This command checks deterministic
paper-reference reconstruction; it is not the fresh U280 measurement command.

## Fresh U280 Mechanism Comparison

The reviewer-facing U280 workflow contains four independent implementations:
TempGNN, MATG, ViTeGNN, and RTGA. Its checked configuration is
`configs/u280_core_reproduction.json`:

```bash
make u280-core-preflight
make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3
```

When the measurement directory is a staged copy without `.git`, bind it to the
published source snapshot before running:

```bash
export TEMPGNN_AE_SOURCE_COMMIT=<full-40-character-published-commit>
```

The orchestrator validates the value and records both it and its origin in
`provenance.json`. A normal Git checkout records `git rev-parse HEAD`
automatically.

The preflight records artifact hashes and rejects byte-identical xclbins. Each
runner must write fresh per-repetition measurements from public real-dataset
prefixes; the workflow then derives Fig.11/Fig.12-shaped diagnostic tables and
writes an automatic numerical comparison under
`results/reviewer_u280_runs/<run-id>/`. Synthetic fixtures are limited to C-sim
and are rejected by this workflow. Packaged reference CSV files are never
overwritten. The link request is read from each final xclbin, while the
implemented kernel clock and WNS/TNS are verified from the Vivado `ap_clk`
connection and post-route timing report. Comparison-figure generation is
rejected if the four timing-closed kernel clocks are not comparable. Because
this configuration is explicitly diagnostic, a completed
run remains successful even when `verification.md` records a tolerance FAIL;
use `--require-paper-match` only when auditing a paper-equivalent configuration.
The repository and frozen archive also retain the exact generated real-input
fixtures under `results/generated_u280_comparison_fixtures/` so the fixture
metadata and golden hashes named by packaged measurement rows remain directly
inspectable.

This is a bounded mechanism-level comparison, not a paper-equivalent rerun.
The packaged kernels use an 8-dimensional Q10 forward path and deterministic
stand-in weights over 8,192-event prefixes, with total-board power sampled by
`xbutil`. The paper's evaluation uses complete model configurations, default
32-bit floating point, full dataset streams, and post-route Vivado power
estimates. `configs/u280_core_reproduction.json` therefore records
`results_reproduced_eligible: false`.

The baseline source, paper-mechanism mapping, limitations, build commands,
measurement definition, artifact contract, and raw CSV schema are documented
in `hardware/baselines/README.md` and `artifacts/u280/README.md`. If any
independent implementation is absent, preflight fails rather than substituting
the TempGNN kernel.

## Baseline Status

- MATG: independently reproduced from the IPDPS 2022 paper and its partial
  public HLS headers; includes a distinct source, runner, and U280 xclbin.
- ViTeGNN: independently reproduced from the TPDS 2025 paper; includes a
  distinct source, runner, and U280 xclbin.
- RTGA: independently reproduced from the DAC 2024 paper; includes a distinct
  source, runner, and U280 xclbin.
- Cascade and TGLite-CPU: retained only as packaged paper comparison records in
  this repository; no fresh execution of those external stacks is claimed.
- TempGNN: includes HLS kernels, testbenches, Vitis build scripts, XRT host
  code, U280 forward-path board logs, and its own U280 xclbin.

The three baselines are clean-room, paper-based forward-path reproductions, not
the authors' complete original stacks. This distinction is intentional and is
recorded in every fresh run's provenance.

Run `make release-preflight` before creating the Zenodo archive. It currently
refuses a Results Reproduced release claim because the bounded implementation
is not paper-equivalent; it also requires a license, final citation metadata,
four distinct U280 artifacts, and a fresh numerical PASS. See
`ZENODO_RELEASE_CHECKLIST.md`.

## Metric Meaning

`DDTC` is dependency-driven TDP construction. `OATS` is overlap-aware TDP synchronization.

`packet_reuse_factor` measures how many per-target packet materializations collapse into unique PHLE packets. `memory_bytes` is packet state/metadata traffic. `cycles` is the kernel's cycle proxy used by C-sim and exported fixture stats. HLS reports provide C/RTL latency after synthesis/cosim.
