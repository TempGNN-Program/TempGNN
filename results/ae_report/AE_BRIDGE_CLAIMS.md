# TempGNN AE Bridge Claim Map

See `AE_APPENDIX_DRAFT.md` for the measurement boundary.

| Bridge | Evidence | Verification |
| --- | --- | --- |
| Artifacts Available | Source, tests, fixtures, four hosts/xclbins, build provenance, board logs, and CSV/SVG records | Inspect `hardware/`, `hardware/baselines/`, `artifacts/u280/`, `scripts/`, and `results/` |
| Artifacts Evaluated Functional | Python tests, three-baseline C-sim, distinct-xclbin preflight, XRT checksum validation, gated board-power sampling, and post-route reports | Run `make smoke`, `make baseline-csim`, and `make u280-core-preflight` |
| Results Reproduced | Not currently asserted: the available clean-room path differs from the paper's precision, model checkpoints, full-stream coverage, and power method | Current diagnostic tolerance status is **NOT RUN** |

The Results Reproduced bridge is not asserted for the current bounded implementation, even if its diagnostic tolerance check passes.
