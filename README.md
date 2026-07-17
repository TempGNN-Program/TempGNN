# TempGNN Reproduction

This repository packages a TempGNN artifact for SC-style AE review. It contains:

1. A Python reference model for Target Dependency Packet (TDP) construction, DDTC scheduling, and OATS packet reuse.
2. Vitis-HLS hardware source plus an XRT host path for an Alveo U280 forward-path FPGA run.
3. Independent paper-based MATG, ViTeGNN, and RTGA forward-path reproductions,
   plus a common U280 measurement workflow for the core FPGA comparisons.
4. Scripts that regenerate paper-reference CSV/SVG outputs from anonymized,
   source-labeled constants in `tempgenn/paper_reference_data.py`.

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

This command generates the paper-reference CSV/SVG files from code, runs the
four packaged U280 implementations, validates timing/provenance/goldens and
repeat consistency, derives the measured Fig.11/Fig.12 comparison, and writes
the reviewer report. It does not execute a CPU or GPU performance baseline.

## Current U280 Board Evidence

The package includes U280 forward-path evidence under `results/board_u280/`:

- Board/platform: Alveo U280, `xilinx_u280_gen3x16_xdma_1_202211_1`.
- Current reviewer-runnable xclbin:
  `artifacts/u280/TempGNN/bin/tempgnn_forward_kernel.hw.xclbin`.
- Reviewer artifact: 21 compute units at `168 MHz`; post-route WNS
  `+0.002 ns`, TNS `0.0 ns`, WHS `+0.006 ns`, and THS `0.0 ns`.
- Delivered-xclbin 100-iteration WK/TGN check: mean `1.412534 ms`, P50
  `1.424431 ms`, P95 `1.438663 ms`; golden, repeat, and validation PASS.
- Four-input, same-xclbin cache-switch check: WK/TGN, WK/APAN, MC/JODIE,
  and RT/TGAT all PASS with distinct input cache keys.
- Historical board runs: `smoke`, `tbscale`, `maxbatch`, and `layout_smoke`
  all PASS golden fixed-point checks at `225 MHz` with WNS `+0.016 ns`.
- Layout evidence: `results/board_u280/tempgnn_u280_fpga_layout.png`.

`results/board_u280/` preserves the original TempGNN forward-path sanity logs
and layout evidence. Its older xclbin is omitted because its build metadata contains
an absolute home path; the current metadata-normalized, bitstream-verified
TempGNN xclbin is under `artifacts/u280/`. Fresh runs write new evidence under
`results/reviewer_u280_runs/`.

The current packaged audited run is `20260717T024537Z`. It contains 72 fresh
rows per implementation, 288 rows total, with zero golden, repeat, or timing
failures. The arithmetic mean latency over the 24 aggregate workload rows
(6 datasets x 4 models, with 3 repetitions per aggregate row) is:

| U280 implementation | Mean latency (ms) |
| --- | ---: |
| TempGNN | 1.296553 |
| MATG | 9.966618 |
| ViTeGNN | 2.869752 |
| RTGA | 4.192824 |

These values are read from the fixed CSV snapshot under
`results/reviewer_u280_runs/20260717T024537Z/baselines_u280/`; they are not
parsed from terminal output or hardcoded into the plotting workflow. Thus the
short all-workload summary for TempGNN is approximately `1.30 ms`, while an
individual workload may be near `1.5 ms`. The same CSVs produce the fresh
`7.8889x` TempGNN/MATG average speedup. The paper-figure tolerance diagnostic
remains FAIL and is preserved because this bounded Q10/total-board-power path
is not paper-equivalent.

## Current Validation Status

Completed on July 17, 2026 with Vitis/Vivado 2023.2:

- Cache-key invalidation C-sim PASS, including changed-weight reload and restore.
- Exact 21-worker C-sim PASS for all 24 dataset/model fixtures.
- HLS synthesis PASS; final 21-CU implementation and route PASS.
- U280 100-iteration performance check and sequential input-switch check PASS.
- Four-xclbin reviewer workflow PASS for all 288 functional rows.

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

## Included, Regenerable Paper Figure Outputs

Generate the paper-reference CSV/SVG artifacts:

```bash
python -m scripts.reproduce_paper_figures
```

The package includes the outputs under `results/paper_reproduction/`; the
command deterministically regenerates them in place:

- `paper_figure_values.csv` (runtime reconstruction of all 668 source records)
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

Every generated SVG has a matching generated CSV file. The 668 source records
live as structured constants in `tempgenn/paper_reference_data.py`; each record
states whether the value is an exact author-workbook cell or an axis-calibrated
recovery from an author vector export. `reference_inputs/README.md` records the
source classes, hashes, uncertainty, and Fig.11 plot/prose discrepancy. The
included files provide direct reviewer access, while the code-embedded records
remain authoritative and reproducible. These are paper-reference
reconstructions, not fresh hardware measurements.

## Fresh U280 Mechanism Comparison

The reviewer-facing U280 workflow contains four independent implementations:
TempGNN, MATG, ViTeGNN, and RTGA. Its checked configuration is
`configs/u280_core_reproduction.json`:

```bash
make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3
```

`make ae-core-u280` also generates the paper-reference figures and final AE
report, so this is the only required reviewer command after XRT setup.

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
prefixes; the workflow then derives measured Fig.11/Fig.12 comparison tables and
writes an automatic numerical comparison under
`results/reviewer_u280_runs/<run-id>/`. Synthetic fixtures are limited to C-sim
and are rejected by this workflow. Code-embedded paper-reference records are
never overwritten. The link request is read from each final xclbin, while the
implemented kernel clock and WNS/TNS are verified from the Vivado `ap_clk`
connection and post-route timing report. Each implementation must use one
stable timing-closed clock across all rows; the comparison uses measured
latency directly and performs no frequency rescaling. The
default reviewer target preserves a tolerance FAIL in `verification.md` while
still completing a functionally valid hardware run. Use
`make ae-core-u280-strict` to make numerical paper-figure mismatch fail the
command; reference values are never substituted in either mode.
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

The three baselines are independent, paper-based forward-path reproductions, not
the authors' complete original stacks. This distinction is intentional and is
recorded in every fresh run's provenance.

Run `make release-preflight` before creating the Zenodo archive. It currently
refuses a Results Reproduced release claim because the bounded implementation
is not paper-equivalent; Apache-2.0 is included, while final citation metadata,
four distinct U280 artifacts, and fresh-run completeness are checked. The
separate `make release-preflight-results` target additionally requires a
paper-equivalent configuration and numerical tolerance PASS. See
`ZENODO_RELEASE_CHECKLIST.md`.

## Metric Meaning

`DDTC` is dependency-driven TDP construction. `OATS` is overlap-aware TDP synchronization.

`packet_reuse_factor` measures how many per-target packet materializations collapse into unique PHLE packets. `memory_bytes` is packet state/metadata traffic. `cycles` is the kernel's cycle proxy used by C-sim and exported fixture stats. HLS reports provide C/RTL latency after synthesis/cosim.

## License

This artifact is licensed under the Apache License 2.0. See `LICENSE`.
