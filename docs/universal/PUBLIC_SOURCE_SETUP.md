# Running the published research source

Use the root README setup instructions to install the pinned Node/Python dependencies and start the canonical app. There is one FastAPI entrypoint, `backend/app/main.py`, under `/api/v1`. The source does not include patient records, trained weights or downloaded datasets. Missing optional resources produce unavailable/refusal states; they are not automatically downloaded or treated as disease-negative results.

Open `/universal` for the Twin Control Room and `/arena` for the research laboratory. Create/select an authorized pseudonymous case, upload an eligible source with the required attestations, then select an observation. Source-coordinate volume viewing requires a compatible real volume; a photograph of a printed scan has no missing voxel geometry to reconstruct. Actual segmentation requires a source-compatible saved run or properly recorded reviewer annotation.

Verification:

```powershell
python -m pytest backend/tests -q
npm run check
npm run build
```

Tests depending on optional local artifacts can skip explicitly. The committed aggregate evidence records the evaluated local configuration; a fresh checkout must report its own observed result.

The official ICD-10-CM index is optional. Reproduce the unchanged primary downloads and local SQLite index with the bounded resource tools:

```powershell
python scripts/fetch_external_resources.py --help
python scripts/build_official_terminology.py --help
```

Download receipts contain exact source URLs, versions, hashes and rights notices. Use the reviewed CDC resource identifiers, preserve attribution and build under ignored `data/external`. ICD-11 is a different terminology: configure its genuine native-reference credentials, approved release and accepted terms only after the required review; crosswalk permission is a separate prerequisite. No credentials are committed.

Trained-model operation additionally requires exact checkpoint/evaluation/manifest identities, compatible model and dataset rights, dependency/runtime checks and per-input contracts. The commercial usage profile must stay enabled for commercial-development work. No model is clinically activated by this source publication. The PTB operator sidecars used in the local demonstration are scoped evidence, not a blanket permission for another user or deployment.

Local operator reproduction uses the prior completion instructions plus:

```powershell
python scripts/qa_temporal_comparison.py
node tools/browser-qa/expansion-control-room.mjs
node tools/browser-qa/expansion-structures.mjs
node tools/browser-qa/matched-model-explorer.mjs
node tools/browser-qa/temporal-comparison.mjs
```

The browser scripts require the explicitly isolated QA stack and its generated local credential file. Consult the contracts for exact prerequisites and current script names. Detailed local artifacts, credentials and third-party source images are intentionally absent from the public repository.
