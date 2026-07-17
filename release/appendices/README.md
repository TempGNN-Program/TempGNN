# pap142 SC26 Artifact Appendices

This directory contains the reviewer-facing Artifact Description (AD),
Artifact Evaluation (AE), and combined AD/AE appendices as both PDF and LaTeX
source. The source uses the SC26 `sc26repro` style with the bundled
`IEEEtran.cls`.

Compile any appendix twice to settle cross-references, for example:

```bash
pdflatex -interaction=nonstopmode -halt-on-error pap142_TempGNN_AD_Appendix.tex
pdflatex -interaction=nonstopmode -halt-on-error pap142_TempGNN_AD_Appendix.tex
```

The authoritative editable content is in `AD_APPENDIX_DRAFT.md` and
`AE_APPENDIX_DRAFT.md` at the repository root. They cover code download,
environment setup, U280 latency runs, and figure generation from
`results/result.csv`.
