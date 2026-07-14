# U280 Mechanism Comparison Artifact Contract

This directory contains four independently built implementations used by the
reviewer-facing U280 core workflow:

```text
artifacts/u280/TempGNN/
artifacts/u280/MATG/
artifacts/u280/ViTeGNN/
artifacts/u280/RTGA/
```

Each implementation directory contains:

- a runner that executes all requested dataset/model/repetition combinations;
- the host binary used by that runner;
- the implementation-specific U280 xclbin;
- build provenance and SHA256 records. The corresponding source is under
  `hardware/` and `hardware/baselines/`.

Each provenance record separates the complete workflow-source snapshot from
the kernel/header/HLS/link files that are direct xclbin build inputs.

The four xclbins must be independently built. The preflight check records their
SHA-256 hashes and rejects byte-identical xclbins so that one implementation
cannot be silently reused as another baseline.

## Runner Output Contract

The runner receives the arguments shown in
`configs/u280_core_reproduction.json` and writes one CSV row per
repetition. The comparison columns are:

```text
dataset,model,solution,repetition,batch_size,latency_ms,power_w,energy_mj,frequency_mhz,requested_frequency_mhz,xclbin_link_requested_frequency_mhz,post_route_kernel_frequency_mhz,post_route_wns_ns,post_route_tns_ns,timing_met,fixture_input_kind,fixture_input_sha256,fixture_source_url
```

Every row also carries the evidence fields checked by the orchestrator:

```text
power_samples,power_min_w,power_max_w,kernel_iterations,kernel_checksum,embedding_checksum,warmup_kernel_checksum,warmup_embedding_checksum,expected_kernel_checksum,expected_embedding_checksum,golden_validation,repeat_consistency,golden_embedding_sha256,golden_stats_sha256,xclbin_sha256,host_sha256,fixture_metadata_sha256,measurement_utc
```

For every row, `power_w` is total U280 board power sampled with
`xbutil examine --report electrical` only during the gated repeated-kernel
window. `energy_mj` must be consistent with `latency_ms * power_w`. The
orchestrator validates completeness, units, and real-input provenance,
aggregates repetitions, derives diagnostic Fig.11/Fig.12-shaped tables, and
writes a numerical tolerance report under
`results/reviewer_u280_runs/<run-id>/`.

`frequency_mhz` is an aggregation alias for the timing-closed post-route kernel
clock. `xclbin_link_requested_frequency_mhz` comes from the final xclbin build
metadata; `post_route_kernel_frequency_mhz` comes from the Vivado `ap_clk`
connection and is accepted only with nonnegative post-route WNS/TNS. The
orchestrator rejects comparison-figure generation when the four implemented
clocks differ by more than the configured tolerance.

The current contract is explicitly mechanism-level and not paper-equivalent;
see `hardware/baselines/README.md` and the configuration's
`results_reproduced_eligible` field.

The packaged paper CSV files are reference outputs only. A reviewer run must
write a new run directory and must never overwrite the packaged references.
