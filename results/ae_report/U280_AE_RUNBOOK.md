# U280 AE Runbook

## Environment

```bash
source /tools/Xilinx/Vitis/2023.2/settings64.sh  # rebuild only
source /opt/xilinx/xrt/setup.sh
```

## Fast Checks

```bash
python3 -m unittest discover -s tests
python3 -m scripts.reproduce_paper_figures
make baseline-csim
```

The figure command regenerates the source-labeled paper-reference inputs. `baseline-csim` executes every paper-based kernel twice and requires bit-identical outputs and stats.

## Fresh Mechanism-Level Comparison

```bash
make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3
```

Preflight requires four distinct xclbin hashes. The measurement harness fetches deterministic prefixes from the six public real datasets, records source/sample hashes, cross-checks each xclbin link request against the Vivado-connected kernel clock and post-route WNS/TNS, calibrates a repeated-kernel window, validates repeat checksums, samples total U280 board power with `xbutil`, writes raw rows, derives measured Fig.11/Fig.12 comparison data, and compares it with code-embedded paper references. Each implementation must keep one timing-closed clock across its rows; clocks are recorded and latency is not frequency-rescaled. Synthetic fixtures are accepted only by C-sim and rejected by this workflow. The default target preserves a tolerance failure in `verification.md`; `make ae-core-u280-strict` additionally makes numerical mismatch fail the command.

This is not a paper-equivalent rerun because the reduced Q10 kernels, deterministic stand-in weights, bounded prefixes, and power method differ from the paper methodology.

Current recorded tolerance status: **DIAGNOSTIC FAIL; NOT PAPER-EQUIVALENT**.

## Optional Rebuild

```bash
make u280-build U280_PLATFORM=/opt/xilinx/platforms/xilinx_u280_gen3x16_xdma_1_202211_1/xilinx_u280_gen3x16_xdma_1_202211_1.xpfm
make u280-baseline-build
```

Rebuilding can take multiple hours. Packaged xclbins allow board evaluation without Vivado/Vitis.
