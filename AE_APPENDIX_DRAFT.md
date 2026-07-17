# Artifact Evaluation Appendix

Paper ID: `pap142`

This workflow evaluates the two artifacts defined in the AD:

- `A1`: TempGNN and the three U280 accelerator baselines.
- `A2`: `results/result.csv` and the paper-figure generator.

Artifact DOI:
`https://doi.org/10.5281/zenodo.21417187`.

Development repository:
`https://github.com/TempGNN-Program/TempGNN`.

Frozen release: `sc26-ae-pap142-v1.0`.

## 1. Download and Setup

```bash
git clone https://github.com/TempGNN-Program/TempGNN.git
cd TempGNN
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Required environment:

```text
Board: AMD/Xilinx Alveo U280, xcu280-fsvh2892-2L-e
Platform: xilinx_u280_gen3x16_xdma_1_202211_1
OS: Ubuntu 22.04 x86_64
XRT: 2.16.204
Vitis/Vivado: 2023.2 (only required for rebuilding xclbins)
GCC: 11.4.0
GNU Make: 4.3
Python: 3.10 or newer
```

The U280 account and login instructions are delivered through the private SC26
submission channel. No credentials are stored in the artifact.

## 2. Review Plan and Expected Time

| Artifact | Setup | Execution | Analysis | Expected result |
| --- | ---: | ---: | ---: | --- |
| `A1` U280 latency | 10-20 min | 30-90 min | less than 5 min | Four fresh latency rows; TempGNN is lowest at about 1.3 ms |
| `A2` figure generation | less than 5 min | less than 1 min | 2-5 min | Nine CSV/SVG figure pairs generated from `results/result.csv` |

Optional xclbin rebuilding is excluded from the direct review path.

## 3. Execute A1: U280 Latency

```bash
source /opt/xilinx/xrt/setup.sh
xrt-smi examine
make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3
```

The command performs these tasks:

```text
A1-T1 check the four packaged U280 artifacts
  -> A1-T2 load inputs for six datasets and four models
  -> A1-T3 run TempGNN, MATG, ViTeGNN, and RTGA three times
  -> A1-T4 write per-implementation raw measurement CSVs
  -> A1-T5 aggregate the latency results and update the AE report
```

Inputs:

```text
Datasets: WK, MC, RT, LM, WT, GT
Models: JODIE, TGN, TGAT, APAN
Repetitions: 3
```

Fresh results are written to
`results/reviewer_u280_runs/<run-id>/`.

## 4. Analyze A1

The run is successful when:

1. the command exits with status zero;
2. fresh rows exist for TempGNN, MATG, ViTeGNN, and RTGA;
3. all six datasets and four models are present; and
4. the aggregate latency follows the expected U280 behavior below.

| U280 implementation | Mean latency (ms) |
| --- | ---: |
| TempGNN | 1.296553 |
| MATG | 9.966618 |
| ViTeGNN | 7.022530 |
| RTGA | 4.914013 |

The principal behavior to verify is that TempGNN has the lowest mean latency
and remains close to 1.3 ms. This result supports the target-centric execution,
DDTC/OATS mechanisms, and the U280 accelerator comparison in `C1-C4`.

## 5. Execute and Analyze A2: Paper Figures

```bash
python3 -m scripts.reproduce_paper_figures
```

The command performs these tasks:

```text
A2-T1 read results/result.csv
  -> A2-T2 validate and group rows by paper figure
  -> A2-T3 generate a CSV and SVG for each figure
  -> A2-T4 write figure_data_manifest.csv
```

Expected outputs under `results/paper_reproduction/`:

```text
fig2_execution_breakdown.csv/.svg
fig4a_branch_parallelism_ratio.csv/.svg
fig9b_gpu_overhead_breakdown.csv/.svg
fig10_speedup_tglite_cpu.csv/.svg
fig11_speedup_matg.csv/.svg
fig12_energy_tempgnn.csv/.svg
fig13_ablation_time.csv/.svg
fig14a_batch_sensitivity.csv/.svg
fig14b_tdp_entries.csv/.svg
figure_data_manifest.csv
```

The evaluation is successful when all nine CSV/SVG pairs exist and the
manifest records `results/result.csv` as their input. These outputs provide the
paper-result views associated with `C1-C4`.

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

The three baselines are independent, paper-based forward-path reproductions,
not the authors' complete original stacks.

## Metric Meaning

`DDTC` is dependency-driven TDP construction. `OATS` is overlap-aware TDP
synchronization.

`packet_reuse_factor` measures how many per-target packet materializations
collapse into unique PHLE packets. `memory_bytes` is packet state/metadata
traffic. `cycles` is the kernel's cycle proxy used by C-sim and exported
fixture stats. HLS reports provide C/RTL latency after synthesis/cosim.

## License

This artifact is licensed under the Apache License 2.0. See `LICENSE`.
