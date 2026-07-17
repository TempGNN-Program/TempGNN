# Zenodo Release Checklist For SC26 Paper pap142

The DOI record must archive the complete runnable computational artifact, not
only the AD/AE PDF and LaTeX files.

## Before Reserving The DOI

1. Select and add the project license as `LICENSE`. License selection is an
   author/legal decision and is intentionally not guessed by this repository.
2. Place the four independent U280 implementations under `artifacts/u280/`.
3. Copy `configs/u280_core_reproduction.example.json` to
   `configs/u280_core_reproduction.json`, replace every placeholder, and record
   exact source revisions.
4. Run:

   ```bash
   make test
   make u280-core-preflight
   make ae-core-u280
   ```

5. Confirm that the fresh reviewer-style run contains `provenance.json`, raw
   per-repetition CSV files, derived CSV/SVG files, and `verification.md`.
6. Replace the creator placeholders in `release/zenodo_metadata.json.template`
   and `release/CITATION.cff.template` only when the conference anonymity rules
   permit publication of author metadata.

## Reserve And Publish

1. Create a Zenodo **Software** upload titled
   `TempGNN: Artifact for SC26 Paper pap142`.
2. Upload one complete compressed artifact generated from the frozen Git tag.
3. Use **Get a DOI now** while the record is still a draft.
4. Add the reserved DOI to the AD, AE, README, and final citation metadata.
5. Apply all AE feedback while the Zenodo record remains a draft.
6. Re-run the checks above, record the archive SHA-256, create the frozen Git
   tag `sc26-ae-pap142-v1.0`, and publish the Zenodo record by the SC26 artifact
   freeze deadline.

After publication, cite the version-specific DOI for the exact frozen artifact.
Changes to artifact files require a new Zenodo version.

## Required Artifact Location Block

```text
Persistent frozen artifact:
https://doi.org/10.5281/zenodo.REPLACE_ME

Development repository:
https://github.com/TempGNN-Program/TempGNN

Frozen release:
sc26-ae-pap142-v1.0

Archive SHA-256:
REPLACE_ME
```
