# TempGNN AE Bridge Claim Map

See `AE_APPENDIX_DRAFT.md` for the measurement boundary.

| Bridge | Evidence | Verification |
| --- | --- | --- |
| Artifacts Available | Source, tests, fixtures, four hosts/xclbins, build provenance, board logs, and CSV/SVG records | Inspect `hardware/`, `hardware/baselines/`, `artifacts/u280/`, `scripts/`, and `results/` |
| Artifacts Evaluated Functional | Distinct-xclbin preflight, XRT checksum validation, repeat checks, gated board-power sampling, and post-route reports | Run `make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3` |
| Results Reproduced | Not currently asserted: the available bounded reproduction path differs from the paper's precision, model checkpoints, full-stream coverage, and power method | Current diagnostic tolerance status is **DIAGNOSTIC FAIL; NOT PAPER-EQUIVALENT** |

The Results Reproduced bridge is not asserted for the current bounded implementation, even if its diagnostic tolerance check passes.
