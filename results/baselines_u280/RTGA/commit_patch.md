# RTGA Commit/Patch Notes

- Repository revision: `workspace-snapshot`
- Baseline source: RTGA: A Redundancy-free Accelerator for High-Performance Temporal Graph Neural Network Inference
- Reproduction mapping: Reproduced according to the paper and measured on U280 with redundancy-aware packet/cache behavior.
- Measurement scope: reproduced U280 baseline run with the packaged measurement harness and matching fixture settings.
- Output consistency: reproduced raw latency/energy rows are consumed by `scripts/derive_comparison_figures.py` and checked by `scripts/verify_baseline_measurements.py`.
