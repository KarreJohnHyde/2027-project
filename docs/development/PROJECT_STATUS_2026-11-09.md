# MedTwin project audit and remaining work — 9 November 2026

> Historical snapshot: runtime repair, skin fusion, CT manifests, current tests and remaining work are updated in [Implementation progress, 9 November 2026](../development/IMPLEMENTATION_PROGRESS_2026-11-09.md). Earlier blockers and counts below must be read in their original dated context.

This audit answers the request to install useful free resources, expose organ/test/finding/model-version coverage, and identify unfinished implementation. The intended use is research/education and potentially commercial, not yet decided. Existing user changes were preserved. No deployment, clinical activation, model training, account creation or licence purchase was performed.

## Work completed in this pass

- Added **Model Registry → Organ / test coverage**: search by organ/system, test, target or model; each row shows a checkpoint version and preprocessing version. Exported CSVs include the complete checkpoint SHA-256, dataset licence, evaluation reference and limitations. An empty search explicitly has no registered target; segmentation rows are labelled anatomical/lesion masks rather than disease diagnoses.
- Exported [227 declared target rows](../data/CAPABILITY_COVERAGE.csv) from **28 registry entries**, of which **18 have checkpoints**. Recomputed gates: **16 pass the generic research artifact gate**, including two evaluation-only survival models; **zero pass the clinical activation gate**. Separate third-party adapters have their own input/source checks. These counts do not describe 227 validated diseases, and anatomical labels can include structures and landmarks.
- Refreshed `model_registry/validation_status.json` from the current gates. Its previous 21-entry snapshot was stale.
- Completed the **18-subset MedMNIST 28-pixel / 28-cubed collection**: added 11 NPZs / **261,220,620 bytes**, reused seven NPZs. All 18 match the official version-3.0 publisher MD5s and have additional local SHA-256s. The arrays contain **717,958 samples**. Publisher train/validation/test splits and all labels are preserved.
- Generated **18 `samples.csv` indexes**, label/preparation JSON, and **54 PNG previews**, under `D:/project/_derived/datasets/medmnist`. Complete image arrays remain in `C:/MedTwin_Datasets/MedMNIST/*.npz`; previews are not substituted for the complete datasets. A 3D preview is only its central slice. No unnecessary duplicate PNG expansion of 717,958 samples was made.
- Rechecked **all 1,669 artifacts** in the three previous pinned acquisition manifests: 217 public-data artifacts, 328 multimodal artifacts, and 1,124 DeepFluoro artifacts. All matched declared sizes/checksums. This is narrower than an integrity audit of every dataset already on the workstation.
- Confirmed the existing **292-package Python environment** has consistent dependencies with `uv pip check`. Required research libraries were already installed; no package versions were upgraded. The MedMNIST loader and new preparation/download code use these existing dependencies.
- Added a resumable recovery worker for the existing selected LIDC, CQ500 and MSD liver cohorts, with archive checks, local hashes, recorded errors and a 60-GiB C: storage reserve. It uses native `curl`; no security policy was changed. Its status records actual checked archives, not a previous process exit code. Large downloads are **not yet certified complete**.
- Corrected outdated application roadmap statements about cardiac MRI, brain MRI, MURA, Kvasir-SEG, KiTS19 and TotalSegmentator.

The [resource CSV](../data/RESOURCE_INSTALLATION_2026-11-09.csv) lists 25 grouped records across the manifests. The seven original MedMNIST NPZs occur in both the old and full-collection manifests; do not sum those rows as unique files or patients.

## Acquired resources and appropriate uses

| Resource | Installed/prepared evidence | Useful next work | Remaining restriction |
| --- | --- | --- | --- |
| MedMNIST, all 18 subsets | Full NPZs, indexed splits/labels and previews | Lightweight classification pipelines and software benchmarks | Not clinical data at diagnostic resolution; patient independence unavailable; overlaps parent datasets |
| KiTS19 | 210 CTs with matching existing masks; shapes/affines checked | Kidney/renal-tumour volumetric training | Finish training manifests, split audit, label quality, training and independent testing |
| PAD-UFES-20 | 2,298 images, metadata and patient-grouped manifests | Skin image + tabular research | Fit preprocessing only on training subjects; train and evaluate the actual model |
| VQA-RAD | 315 images and QA source; grouped QA manifest | Image/text retrieval and QA benchmarks | Teaching images; patient independence not established; no longitudinal outcome cohort |
| CBIS-DDSM JPEG conversion | 10,237 JPEGs, six source CSVs, patient-separated derived metadata | Mammography classification/fusion preparation | Full-image/crop/ROI coordinate and file correspondence still unvalidated |
| DeepFluoro | Six CT/mask pairs, 366 X-rays with poses, selected 1,124 files | Paired projection/volume registration research | Coordinate adapter, specimen-separated protocol and registration evaluation |
| BiomedCLIP | Pinned checkpoint, configuration, tokenizer; previous local encoder checks | Image/text feature extraction | Not an installed clinical diagnostic application or a trained MedTwin fusion model |
| LIDC-IDRI selected cohort | Recovery of selected 300-patient acquisition in progress | Lung nodule CT/reader annotation work | Complete downloads, verify XML/SeriesInstanceUID joins, reader agreement and splits |
| CQ500 | Reader CSV exists; 491 distinct source identifiers in the reader table; archive recovery queued | External head-CT evaluation | Verify source availability and usable cohort size, finish archive checks and serving-protocol evaluation; reserve as external evaluation data |
| MSD liver | Partial 28,925,891,584-byte source TAR recovery queued | Liver/tumour CT segmentation | Complete archive inventory, safe extraction, geometry/labels, manifests and training |

Source terms: [MedMNIST official release](https://zenodo.org/records/10519652), [KiTS19](https://github.com/neheller/kits19), [PAD-UFES-20](https://data.mendeley.com/datasets/zr7vgbcyr2/1), [VQA-RAD](https://osf.io/89kps/), [CBIS distribution](https://www.kaggle.com/datasets/awsaf49/cbis-ddsm-breast-cancer-image-dataset), [DeepFluoro remix](https://huggingface.co/datasets/eigenvivek/xvr-data/tree/main/deepfluoro), [BiomedCLIP](https://huggingface.co/microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224), [LIDC-IDRI](https://www.cancerimagingarchive.net/collection/lidc-idri/), [CQ500 publisher](https://www.qure.ai/us/blog/challenges-of-development-validation-of-deep-learning-for-radiology), [MSD](https://registry.opendata.aws/msd/).

## Immediate execution blocker

The installed Python 3.12 runtime's `_ssl` extension fails with **“An Application Control policy has blocked this file.”** This prevents Uvicorn/backend startup, Python HTTPS, the asynchronous API test client and the real-stack browser test from running on this workstation. Consistent package metadata does not establish a working runtime.

The appropriate next step is for the workstation administrator to approve or repair the sanctioned Python runtime, then re-run API and full-stack checks. This pass did not change application-control policy, swap blocked DLLs, disable certificate verification or claim those tests passed. Native `curl` is operational and the dataset downloader can continue independently.

## Prioritized implementation backlog

Statuses below concern the current inspected implementation; historical roadmap documents are not proof that work remains unfinished.

| Priority | Area | Current state | Work and acceptance evidence still needed |
| --- | --- | --- | --- |
| P0 | Python runtime / API availability | Blocked by workstation application control | Approved working runtime; successful SSL import, backend health/startup, API regressions and isolated browser workflow |
| P0 | Intended use and commercial rights | Both/undecided | Choose first use cases and markets; review source data, derived weights, code and redistribution rights separately |
| P0 | Clinical scope | No clinically activated model | Explicit organ + acquisition protocol/test + target + immutable model/preprocessing + supported population; unsupported requests must abstain |
| P0 | Independent clinical validation | Not established | Independent lawful data; subject/site-separated external tests, reference adjudication, calibration, sensitivity/specificity and subgroup error review; appropriate clinical/regulatory process before clinical use |
| P1 | Existing CT acquisition | In progress | All selected LIDC/CQ500/liver archives checked; failures and space pauses resolved; local hashes and source versions retained |
| P1 | Acquisition-to-task registration | Partial | Fold newly acquired roots and prepared manifests into the canonical task audit; regenerate readiness evidence without promoting benchmark presence to validation |
| P1 | KiTS19 and MSD CT tasks | Data/pipelines partly ready | Patient-level pairs, mask values/geometry, locked split manifests, bounded trainers, evaluated checkpoints and serving adapters |
| P1 | LIDC reader labels | Partial preparation code exists | Match exact XML series/SOP UIDs; explicitly handle reader disagreement and incomplete contours; never treat LUNA and LIDC as independent cohorts |
| P1 | CQ500 external evaluation | Cohort incomplete | Freeze cohort/protocol; evaluate head-CT serving consistently at scan level against reader-majority labels; keep it outside training/model selection |
| P1 | CBIS-DDSM localization | Patient split prepared | Verify full image/crop/ROI joins and coordinate transforms; no fabricated lesion boxes |
| P1 | Input quality and applicability | Existing gates have known limitations | Quality checks, protocol/sampling/sequence checks, stronger rejection of wrong anatomy/modality and explicit acceptance/false-refusal evaluation |
| P1 | OCR and laboratory extraction | Implemented, accuracy not clinically established | Independent de-identified gold pages/tables/cells; adjudicated values, units, dates, specimen, intervals, uncertainty and provenance; layout-aware row recovery |
| P1 | Clinical NLP / terminology | Several adapters exist | Independent assertion/temporality evaluation; qualified concept-linking vocabulary/model licence; persistent isolated NLP workers where needed |
| P1 | Modality/model parity | Existing internal checks only | Repeat upload/slice/volume/DICOM/ECG/video parity for every changed checkpoint and input adapter, after runtime repair |
| P1 | Security and recovery | Controls partly implemented | Key rotation and custody; encrypted backup/restore drill; durable object storage policy; malware scanning; tenant threat model; penetration testing and tamper-evident audit retention |
| P2 | ECG and echo expansion | ECG research paths exist; echo code/evidence present | Externally evaluate lead/unit/rate contracts; reconcile/register echo checkpoint and serving evidence; do not use digital ECG weights on photographs |
| P2 | Temporal endoscopy and other scopes | Still-image models; sampled-frame code exists | Procedure-separated temporal evaluation/tracking; separate labelled tasks for gastroscopy/capsule/bronchoscopy/cystoscopy/hysteroscopy/arthroscopy, rather than reusing a colonoscopy label set |
| P2 | Whole-slide pathology | Tile viewing exists | Licensed slide-level labels, colour/scanner QC, tiled inference, patient-separated training, target-specific adapters and external evidence |
| P2 | EEG | EDF/BDF reading/display only | Lawful subject-labelled recordings, channel/montage/rate contracts, event annotations, trained checkpoint and seizure/event evaluation |
| P2 | New specialties | No universal disease model | Separate breast, skin, retina/OCT, prostate, thyroid, dental, ENT, reproductive/fetal and nuclear-medicine tasks; benchmark datasets alone do not supply complete clinical coverage |
| P2 | Skeletal disease/localization | MURA study classifier exists | Fracture boxes, osteoarthritis and spine tasks each need their own labels, checkpoints and evaluations; MURA normal/abnormal is not fracture localization |
| P2 | Multimodal disease prediction | ECG+demographics exists; image/text/table resources prepared | Align actual subject/exam/time/outcome; exclude label leakage, fit on training split only, compare unimodal arms, validate missing-data behavior and external performance |
| P2 | New learning methods | Offline benchmark implementations exist | Task-specific validation of self-training/novelty/policy methods; no automatic retraining or treatment decisions from patient uploads |
| P2 | Registration / patient anatomy | Scan-frame surfaces and reference atlas exist | DeepFluoro coordinate adapter and specimen split; independent landmark TRE and transform validation; preserve distinction between reference atlas and patient geometry |
| P2 | Forecasting | Reviewed-data research baselines only | Outcome/horizon definition, longitudinal subject cohort, censoring/missingness handling, chronological validation, calibration and supported use limits |
| P2 | Treatment/procedure/operation guidance | Not validated | Separate causal/clinical evidence and human factors; surgical phase recognition is not an autonomous operation or complication detector |
| P2 | Reviewer workflow | Append-only corrections exist | Reader disagreement/adjudication and usability study; independently drawn ground truth; correction-derived masks are not independent evaluation truth |
| P2 | Interoperability | FHIR/HL7 imports exist | Deployment-specific interoperability/security testing, terminology mapping review and export/round-trip verification for intended integrations |
| P2 | Commercial/deployment boundaries | Local and deployment code exist | Data-protection review; approved cloud data flows/RLS; retention policy, monitoring, rollback, model version pinning and drift response |
| P3 | Accessibility and performance | Frontend builds; existing warnings | Automated accessibility audit and approved visual baselines; resolve React warnings and large Three.js chunks without breaking anatomy workflows |
| P3 | Evidence freshness | Multiple historical reports conflict | Use generated current manifests and gate snapshots; date/archive historical statements; make acquisition/training/research/clinical states visible separately |

This is a finite backlog of inspected project gaps. “Every disease, organ, test, scope and operation” is not a feasible completeness criterion or a capability established by installing more data.

## Commercial-use boundaries

- MedMNIST is CC BY 4.0 except DermaMNIST (CC BY-NC 4.0); the official benchmark is not intended for clinical use. Derived parent-cohort overlap must be checked before calling it external validation.
- KiTS19, CQ500, DeepFluoro, MURA, the existing RSNA research cohort, and Kvasir datasets have noncommercial/research or permission restrictions recorded in project manifests/model cards. Keep them out of a commercial release until the applicable permission is established.
- Attribution/share-alike datasets, pretrained-model licences, dependency licences and model-weight redistribution must be reviewed independently. A permissive code licence is not a blanket grant for its training data or medical use.
- MIMIC and other credentialed/approval-based resources are not acquired through unofficial copies. Missing independent report/lab/longitudinal labels remain prerequisites rather than invented data.

## Reproduction and live progress

```powershell
# Reuse and verify the installed lightweight collection; recreate CSV indexes.
.venv\Scripts\python.exe scripts\install_medmnist_collection.py --run

# Recompute organ/test/target/version coverage and the current registry snapshot.
.venv\Scripts\python.exe scripts\export_capability_coverage.py
.venv\Scripts\python.exe scripts\write_validation_status.py

# Cohort downloader is already running in a hidden background process.
# It has a single-worker lock; do not start redundant copies.
Get-Content artifacts\downloads\cohort_recovery_status.json
Get-Content artifacts\downloads\cohort-recovery-2026-11-09.log -Tail 10

# Resume after a recorded stop/reboot (keeps partial files and checks final archives).
.venv\Scripts\python.exe scripts\resume_dataset_cohorts.py
```

The recovery worker is a local process, not a restart-persistent scheduled service. On a reboot it must be resumed using the command above. `RUNNING` in a saved JSON file is not proof a process remains alive; check its recorded PID and log timestamp. Archives are not automatically extracted and datasets are not automatically used for training.

Offline loader example:

```python
import medmnist
from medmnist import INFO

name = "organmnist3d"
dataset = getattr(medmnist, INFO[name]["python_class"])(
    split="train", root="C:/MedTwin_Datasets/MedMNIST", download=False
)
image, label = dataset[0]
```

## Verification results

- `npm run check`: passed (type checking, lint with pre-existing warnings, check build with existing large-chunk warning).
- `uv pip check --python .venv/Scripts/python.exe`: all 292 installed distributions compatible.
- Acquisition/preparation and evidence-boundary tests: **20 passed**.
- Model/dataset backend subset: **8 passed, 11 setup errors** due the blocked asynchronous/SSL runtime; not an API pass.
- Real-stack browser check: **blocked at backend startup** by the same Windows application-control error.
- Component-only browser check: **1 passed**, covering target filtering, full-checkpoint CSV export, inactive clinical status and an unsupported-target empty state. Screenshot/run evidence is under `artifacts/verify/coverage-component-2026-11-09`. Explicit registry fixtures are used; this does not establish authentication/API behavior or medical accuracy.
- Existing pinned acquisition verification: **217/217 + 328/328 + 1,124/1,124** passed. Full MedMNIST installation: **18/18** passed official checksums, array/count/label checks and index preparation.
