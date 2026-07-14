# Baseline Mechanism Map

These kernels are independent, bounded forward-path reproductions. This map
connects each published mechanism to the implementation that a reviewer can
inspect. It does not claim source or numerical equivalence to the authors'
complete designs.

## MATG

| Published mechanism | Implementation location | Packaged boundary |
| --- | --- | --- |
| Timestamp-only lightweight attention | `matg_time_score` in `src/matg_kernel.cpp` | Deterministic 128-entry Q10 ROM stands in for learned values |
| Temporal-neighbor pruning | `matg_insert_topk` and `matg_scan_recent` | At most 20 valid candidates and 2/4/6 retained neighbors |
| Memory/GNN update | `matg_model_update` | Eight-dimensional fixed-point adapters; no trained KD checkpoint |

## ViTeGNN

| Published mechanism | Implementation location | Packaged boundary |
| --- | --- | --- |
| Neighbor update and compacting | `vite_neighbor_update_unit` in `src/vitegnn_kernel.cpp` | Newest valid entries, duplicate-peer removal, four retained neighbors |
| Lightweight temporal attention | `vite_attention_aggregate` | Bounded integer attention over the retained neighbors |
| Versatile model computation | `vite_model_update` | One packaged CU with four model adapters |
| Inference modes | `inference_mode` selector | Measurements use the `bal`-inspired path; cached output is not the paper's separate `thpt` maintenance path |

## RTGA

| Published mechanism | Implementation location | Packaged boundary |
| --- | --- | --- |
| Temporal tree construction | `rtga_load_recent` and `rtga_temporal_tree_construction` in `src/rtga_kernel.cpp` | BRAM-buffered, bounded recent-history tree edges |
| Redundancy suppression | `visited_tag` and `rtga_contains_edge` | Direct-mapped 1,024-slot event tags plus local edge deduplication |
| Temporal-aware data cache | `rtga_temporal_aware_cache` | Sixteen cache lines with degree/timestamp priority |
| Parallel temporal arithmetic | `rtga_tau_groups` and `rtga_tau_lanes` | Eight unrolled TAU lanes |

## Common Measurement Boundary

All four U280 systems use the same 8,192-event real-data prefixes, target
batches, 8-dimensional Q10 tensors, deterministic weights, HBM port mapping,
225 MHz requested clock, XRT host timing, and gated `xbutil` total-board power
sampling. Each baseline has a separate top-level kernel and xclbin.

The package does not reproduce baseline training, knowledge distillation,
accuracy evaluation, original model checkpoints, full-stream preprocessing,
or the authors' complete host/runtime stacks. Fresh U280 rows therefore measure
these packaged mechanisms and remain diagnostic with respect to the paper
figures.

## Primary Sources

- MATG: H. Zhou et al., IPDPS 2022, DOI
  `10.1109/IPDPS53621.2022.00111`.
- ViTeGNN: H. Zhou et al., IEEE TPDS 36(3), 2025, DOI
  `10.1109/TPDS.2024.3521897`.
- RTGA: H. Yu et al., DAC 2024, DOI `10.1145/3649329.3656241`.
