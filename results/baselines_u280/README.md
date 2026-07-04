# U280 FPGA Baseline Evidence

This directory contains reproduced U280 FPGA baseline measurement evidence for MATG, ViTeGNN, RTGA.

Important files:

- `manifest.csv` and `manifest.md`: baseline source, reproduction mapping, toolchain, platform, parameters, output paths, and measurement date.
- `validation_summary.csv`: compact PASS/FAIL summary and Fig.11/Fig.12 mean values.
- `raw_tempgnn_u280.csv`: TempGNN raw latency/power/energy rows used as the comparison reference.
- `raw_fig10_system.csv`: TGLite-CPU/Cascade/TempGNN-G/TempGNN raw rows used for Fig.10 derivation.
- `<baseline>/raw_latency_power_energy.csv`: reproduced measured input rows for each FPGA baseline.

Use `python3 -m scripts.derive_comparison_figures` to regenerate Fig.10/Fig.11/Fig.12 from the raw CSVs, then `python3 -m scripts.verify_baseline_measurements` for PASS/FAIL checks.
