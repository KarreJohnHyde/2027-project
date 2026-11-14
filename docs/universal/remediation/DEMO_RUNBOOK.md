# Demonstration runbook (14 November 2026)

Start the app with the GPU hidden (PowerShell, in `D:\project`):

```powershell
npm run dev:stop
$env:CUDA_VISIBLE_DEVICES = '-1'
npm run dev:full
# open http://127.0.0.1:8443
```

| # | Scenario | Route and steps | Expected, verified result |
|---|---|---|---|
| 1 | Successful native-scan detection | Upload the slices of one head CT DICOM series (public control: `.\.venv\Scripts\python.exe scripts\prepare_e2e_ct_series.py`, files in `.cache\e2e-controls\cq500-head-ct-series`). Medical Imaging → DICOM series → Assemble series → haemorrhage model → confirm non-contrast axial head CT → Run model. | Per-label series maxima. On CQ500-CT-1: any haemorrhage 1.000 against threshold 0.442; IPH, IVH and SAH flagged (the readers marked ICH, IPH and SAH; IVH is a model false positive). The note cites the CQ500 external evaluation; the result is pending review. |
| 2 | Unsupported input refused | Upload a photographed CT film (e.g. the redacted CASE-D film crops) and run the haemorrhage model. | Refused (InferenceNotPermitted): a photographed film is not native digital CT. No score. |
| 3 | Document case | Upload a report PDF → Document Verification → review fields → Reports → export. | Source-linked fields, reviewer decisions, export and reload. |
| 4 | Model evidence | Model Registry → Model cards. | Held-out and external results per checkpoint, including 9 new tabular models and the CQ500 table. |
| 5 | Failure case | Model Registry → `ct_kidney_tumour_segresnet`. | FAILED (tumour Dice 0); blocked from upload inference. |
| 6 | Historical comparison | Historical Comparison with the fictional reviewed history case. | Observed values, baselines and explicit abstention. |

Automated checks:

```powershell
$env:CUDA_VISIBLE_DEVICES = '-1'
.\.venv\Scripts\python.exe -m pytest backend/tests -q
npm run check
cd tools\browser-qa; $env:MEDTWIN_E2E_CHANNEL='msedge'; $env:MEDTWIN_E2E_PYTHON='D:\project\.venv\Scripts\python.exe'; npx playwright test
```

Regenerate the remediation evidence:

```powershell
.\.venv\Scripts\python.exe scripts\remediation_dataset_integrity.py
.\.venv\Scripts\python.exe scripts\remediation_model_readiness.py
.\.venv\Scripts\python.exe scripts\remediation_requirements.py
```

Resume training after a shutdown: run `artifacts\training\resumable\cpu_queue1.cmd` to `cpu_queue4.cmd` again (finished steps are skipped). Resume downloads with `.\.venv\Scripts\python.exe scripts\acquire_approved_public_datasets.py`.

## New specialty demonstrations (14 November, evening)

| # | Scenario | Steps | Verified result |
|---|---|---|---|
| 7 | Malaria cell (blood) | Upload a thin-smear cell image → Medical Imaging → research image type **Microscopy** → malaria model | Classification with probabilities; "float32, as in the held-out evaluation"; finding pending review (browser test `new-specialty-models.spec.mjs`) |
| 8 | Fetal ultrasound plane (pregnancy) | Upload an obstetric ultrasound image → research image type **Obstetric ultrasound** → fetal-plane model | Six-class plane result; finding pending review (same browser test) |
| 9 | Typed values (kidney, thyroid, breast, heart, hepatitis, diabetes) | Model Registry → Model cards → **Enter values (research)** | Research probability inside the development envelope; out-of-range values and invalid codes refused with the reason |
