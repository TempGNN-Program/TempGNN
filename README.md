# TempGNN Reproduction

Artifact DOI:
[10.5281/zenodo.21417187](https://doi.org/10.5281/zenodo.21417187).

Frozen release: `sc26-ae-pap142-v1.0`.

This repository packages a TempGNN artifact for SC-style AE review. It contains:

1. A Python reference model for Target Dependency Packet (TDP) construction, DDTC scheduling, and OATS packet reuse.
2. Vitis-HLS hardware source plus an XRT host path for an Alveo U280 forward-path FPGA run.
3. Independent paper-based MATG, ViTeGNN, and RTGA forward-path reproductions,
   plus a common U280 measurement workflow for the core FPGA comparisons.
4. Scripts that read `results/result.csv` and regenerate the corresponding
   CSV/SVG figures.

The exact optional software-check and U280 environments are listed in
`ENVIRONMENT.md`. The authoritative measurement boundary is stated in
`AE_APPENDIX_DRAFT.md` and summarized in every generated manifest.

Reviewer-facing documents are available as
[AD PDF](release/appendices/pap142_TempGNN_AD_Appendix.pdf),
[AE PDF](release/appendices/pap142_TempGNN_AE_Appendix.pdf), and
[combined AD/AE PDF](release/appendices/pap142_TempGNN_AD_AE_Appendix.pdf),
with the matching LaTeX sources in `release/appendices/`.

## Reviewer One-Command Path

On the provided U280 host, the complete core path is:

```bash
bash scripts/run_all.sh u280-core
```

The wrapper loads the standard XRT setup when necessary and uses device 0 with
three repetitions. To override either value, source XRT and call
`make ae-core-u280` with `U280_CORE_DEVICE` or `U280_CORE_REPETITIONS`.

This command runs TempGNN, MATG, ViTeGNN, and RTGA on U280.

## U280 Latency

The expected arithmetic mean latency over 6 datasets and 4 models is:

| U280 implementation | Mean latency (ms) |
| --- | ---: |
| TempGNN | 1.296553 |
| MATG | 9.966618 |
| ViTeGNN | 2.869752 |
| RTGA | 4.192824 |

Run the command above to create fresh measurements under
`results/reviewer_u280_runs/<run-id>/`.

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

## Included, Regenerable Paper Figure Outputs

Generate the CSV/SVG artifacts from `results/result.csv`:

```bash
python -m scripts.reproduce_paper_figures
```

The package includes the outputs under `results/paper_reproduction/`; the
command deterministically regenerates them in place:

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

Every generated SVG has a matching generated CSV file. All 668 input rows are
stored in `results/result.csv`; `tempgenn/result.py` loads them as
`TempGNN_data`.

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

The three baselines are independent, paper-based forward-path reproductions, not
the authors' complete original stacks. This distinction is intentional and is
recorded in every fresh run's provenance.

## Metric Meaning

`DDTC` is dependency-driven TDP construction. `OATS` is overlap-aware TDP synchronization.

`packet_reuse_factor` measures how many per-target packet materializations collapse into unique PHLE packets. `memory_bytes` is packet state/metadata traffic. `cycles` is the kernel's cycle proxy used by C-sim and exported fixture stats. HLS reports provide C/RTL latency after synthesis/cosim.

## License

This artifact is licensed under the Apache License 2.0. See `LICENSE`.
