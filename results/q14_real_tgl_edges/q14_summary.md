# Q14 OATS Counter Profile

This table is generated from real TGL edge streams with the current TempGNN dependency/PHLE cycle model.
Model names are explicit dependency-scope profiles for the current HLS kernel, not trained checkpoints.
Memory reduction is versus a no-sharing/no-OATS baseline and is reported as an internal OATS counter profile.

| Dataset | Model | Coverage | Fanout | Depth | Batches | Packet hit | Packet reuse | Reuse factor | Collision inserts | Full-bucket fallback | Sync stall | Off-chip reduction | P50 ms | P95 ms | P99 ms |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| WIKI | JODIE | full | 0 | 0 | 157 | 0.00% | 0.00% | 1.000x | 0.33% | 0.00% | 0.00% | 0.00% | 0.0478 | 0.0478 | 0.0478 |
| WIKI | TGAT | full | 10 | 1 | 157 | 24.92% | 24.92% | 1.332x | 6.53% | 0.00% | 0.00% | 24.92% | 0.8126 | 0.8744 | 0.8977 |
| WIKI | TGN | full | 20 | 2 | 157 | 25.54% | 25.54% | 1.343x | 15.15% | 0.01% | 0.00% | 25.54% | 1.9766 | 2.2325 | 2.2802 |
| WIKI | APAN | full | 20 | 2 | 157 | 25.54% | 25.54% | 1.343x | 15.15% | 0.01% | 0.00% | 25.54% | 1.9766 | 2.2325 | 2.2802 |
| MOOC | JODIE | full | 0 | 0 | 411 | 0.00% | 0.00% | 1.000x | 0.28% | 0.00% | 0.00% | 0.00% | 0.0421 | 0.0478 | 0.0478 |
| MOOC | TGAT | full | 10 | 1 | 411 | 23.92% | 23.92% | 1.314x | 6.71% | 0.00% | 0.09% | 23.92% | 0.6011 | 1.0393 | 1.0670 |
| MOOC | TGN | full | 20 | 2 | 411 | 30.81% | 30.81% | 1.445x | 20.67% | 0.06% | 0.02% | 30.81% | 1.9724 | 3.6113 | 3.7414 |
| MOOC | APAN | full | 20 | 2 | 411 | 30.81% | 30.81% | 1.445x | 20.67% | 0.06% | 0.02% | 30.81% | 1.9724 | 3.6113 | 3.7414 |
| REDDIT | JODIE | stride=10 | 0 | 0 | 68 | 0.00% | 0.00% | 1.000x | 0.24% | 0.00% | 0.00% | 0.00% | 0.0407 | 0.0478 | 0.0478 |
| REDDIT | TGAT | stride=10 | 10 | 1 | 68 | 6.08% | 6.08% | 1.065x | 6.64% | 0.00% | 0.01% | 6.08% | 0.7128 | 1.1361 | 1.1754 |
| REDDIT | TGN | stride=10 | 20 | 2 | 68 | 7.04% | 7.04% | 1.076x | 21.45% | 0.06% | 0.00% | 7.04% | 2.5591 | 4.1954 | 4.4083 |
| REDDIT | APAN | stride=10 | 20 | 2 | 68 | 7.04% | 7.04% | 1.076x | 21.45% | 0.06% | 0.00% | 7.04% | 2.5591 | 4.1954 | 4.4083 |
| LASTFM | JODIE | stride=20 | 0 | 0 | 65 | 0.00% | 0.00% | 1.000x | 0.36% | 0.00% | 0.00% | 0.00% | 0.0478 | 0.0478 | 0.0478 |
| LASTFM | TGAT | stride=20 | 10 | 1 | 65 | 9.13% | 9.13% | 1.100x | 8.51% | 0.00% | 0.00% | 9.13% | 1.0614 | 1.2604 | 1.3023 |
| LASTFM | TGN | stride=20 | 20 | 2 | 65 | 11.09% | 11.09% | 1.125x | 28.27% | 0.16% | 0.00% | 11.09% | 3.9610 | 4.9965 | 5.3086 |
| LASTFM | APAN | stride=20 | 20 | 2 | 65 | 11.09% | 11.09% | 1.125x | 28.27% | 0.16% | 0.00% | 11.09% | 3.9610 | 4.9965 | 5.3086 |

Metric definitions:

- Packet hit = PHLE lookup hits / total packet references.
- Packet reuse = 1 - memory packet fetches / total packet references.
- Collision inserts = inserts whose hash bucket already held a nonmatching entry.
- Full-bucket fallback = nonmatching insert attempts into a full 4-way bucket, treated as non-shared.
- Sync stall = critical-path wait cycles not covered by parallel packet fetch cycles, divided by modeled forward cycles.
