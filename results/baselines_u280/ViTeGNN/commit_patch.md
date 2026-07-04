# ViTeGNN Commit/Patch Notes

- Repository revision: `workspace-snapshot`
- Baseline source: ViTeGNN: Towards Versatile Inference of Temporal Graph Neural Networks on FPGA
- Reproduction mapping: Reproduced according to the paper and measured on U280 with batched inference.
- Measurement scope: reproduced U280 baseline run with the packaged measurement harness and matching fixture settings.
- Output consistency: reproduced raw latency/energy rows are consumed by `scripts/derive_comparison_figures.py` and checked by `scripts/verify_baseline_measurements.py`.
