# MEDTWIN 2.0 — UNIVERSAL MEDICAL AI RESEARCH, REAL 2D DETECTION, PATIENT-SPECIFIC 3D ANATOMY, MULTIMODAL EVIDENCE AND FORECASTING

## ONE AUTHORITATIVE EXECUTION DIRECTIVE FOR CLAUDE CODE + OPENAI CODEX

**Operating mode:** Execute real, verifiable local engineering tasks with maximum available reasoning; do not merely propose an architecture, create empty menus, or claim that every medical condition has a working model. Use Claude Code as the local implementation coordinator and the installed official `codex-plugin-cc` / Codex CLI for independent code and scientific reviews. The stop-time Codex review gate may already be enabled; verify rather than reinstalling the plugin.

**Working directory:** `D:\project`<br>
**Sanitized published reference:** `https://github.com/KarreJohnHyde/2027-project`<br>
**Find the real active browser URL at runtime:** recent instances have used `http://127.0.0.1:8550/`, `http://localhost:8443/`, and an isolated QA port. Do not assume a server is running.<br>
**Project identity:** MedTwin 2.0 — a **pure-software medical AI research system**, *not a clinical diagnostic device*. No Raspberry Pi, physical camera acquisition, hardware ECG sensors, MQTT, IoT or fabricated live telemetry. All inputs are digital uploads or existing authorized electronic records.

> **Primary user outcome:** For every supported medical specialty and input, MedTwin should recognize what it can process, select only scientifically suitable models, produce **real, source-aligned 2D bounding boxes, masks, labels, volumetric segmentations, tracks or image-level classifications**, enable clinician review and same-task model comparison, connect eligible evidence to the **correct Blender/Three.js anatomy** with the *actual level of spatial support*, and display genuinely evaluated historical changes or research forecasts only when eligible data and models exist.
>
> **“Every department” is a coverage roadmap, not permission to falsely promise universal disease diagnosis.** If a model, label, weight, license, benchmark, anatomy map, clinical population, or registration is absent, implement the ingestion/annotation/research infrastructure but mark that specific medical task blocked, unavailable or unvalidated. Never use fabricated outputs to make the product appear complete.

---

## 0. EXECUTION CONTRACT, PRECEDENCE AND SAFETY

1. **Start on the real local source tree.** Read local `AGENTS.md`, `CLAUDE.md`, relevant master directives, local README, `docs/`, `model_registry/`, `dataset_registry/`, lockfiles, `src/`, `backend/`, `ml_training/`, worker code and current model checkpoints. Find actual running processes, OS/Python/Node/CUDA versions, GPU free VRAM, disk capacity, network settings, working directory and app URL. Treat local executable state as operational truth; older GitHub status files are historical.
2. **Preserve and extend, do not rebuild.** Keep the existing React + TypeScript + Vite + Three.js anatomy UI, canonical FastAPI backend, worker queue, case DB, file security, research models, original anatomy GLBs, patient review state, checkpoints, scientific results and verified source citations. Do not introduce an unnecessary separate frontend or gateway solely to match an old diagram. If an architecture change is proposed, document its benefit, migration and rollback first.
3. **Make an auditable local baseline.** Before editing: capture `git status`, branch, tracked modifications and untracked paths, model hash inventory, dataset counts and license state, dependency state, current tests, API routes, runtime health and browser problems. Do not reset or overwrite uncommitted work. Preserve a reversible change plan; no destructive backups that duplicate identifiable records into unsafe locations.
4. **Scoped ordinary local changes are authorized for this development request:** code and tests, safe migrations with rollback, UI implementation, reproducible training configuration and eligible small benchmark experiments. **Get explicit approval before:** public GitHub push/PR, publishing data or artifacts, rewriting Git history, destructive record deletion, destructive production migration, bulk external transfer of datasets or patient files, cloud deployment or paid spend, training on identifiable patient uploads, or remote AI requests containing patient data.
5. **Privacy is a hard requirement.** Existing user-supplied X-ray photos, report PDFs, endoscopy reports and examples may contain names, patient IDs, hospitals and mixed-patient material. Do not add those images or their personal identifiers to GitHub, prompts to remote agents, open telemetry, issue bodies, CI fixtures, public model hubs or screenshots. In-source test assets must be synthetic with explicit TEST labeling or genuinely authorized/de-identified research material. Never assert an upload is de-identified based only on a checkbox.
6. **Separate software readiness from clinical validity.** Report distinct facts: code present; dependency installed; dataset licensed/complete; original weights present; SHA matched; model runnable; internal held-out evaluation; external validation; patient-population calibration; clinician review; and clinical authorization. None implies the next. No disease diagnosis, automated therapy recommendation, hallucinated tumor, invented risk score, fake lesion point or fake future CT/MRI. Use typed, user-readable abstention states.
7. **Every inference must be inspectable:** original source SHA-256, case, exam, acquisition date, modality, study/series/instance UID where safe, model ID/version, training scope, preprocessing version, immutable weight SHA, calibration/thresholds, input/outputs, source coordinates, quality/rejection codes, human review, evidence/annotation history and limitations.
8. **Do not let the prompt consume all execution time as planning.** After an initial bounded audit, implement the first genuinely runnable vertical slice, execute tests, fix failures, then repeat by milestone. Maintain a progress ledger at `docs/implementation/UNIVERSAL_MEDICAL_AI_PROGRESS.md` with `DONE / BLOCKED / IN_PROGRESS / NOT_STARTED`, exact test evidence and next small executable task.
9. **Claude + Codex coordination:** Claude owns the working tree and serializes writes. Use Codex for focused read-only adversarial reviews, independent test analysis, security/geometry review or separate file-scoped delegated tasks; never have two agents silently edit the same file. The Codex stop gate is not proof of clinical validity. Verify actual plugin commands and surface failures honestly. Review high-risk scientific paths after each milestone and incorporate only verified findings.
10. **Project corpus policy:** The older uploaded IEEE manuscript prompt is a scientific-writing reference, NOT an instruction to manufacture experiments or interrupt the engineering mission to draft a paper. If producing reports/manuscripts, distinguish executed results from proposed methods and avoid unsupported title claims.

### Mandatory initial read-only checks (adapt paths to actual repo; do not paste PHI into transcripts)

```powershell
Set-Location D:\project
Get-Location
git status --short --branch
Get-ChildItem -Name
Get-ChildItem model_registry,dataset_registry -ErrorAction SilentlyContinue
node --version
claude --version
codex --version
nvidia-smi
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalPort -in @(8443,8453,8550,8787,8790) } |
  Select-Object LocalAddress,LocalPort,OwningProcess
```

Do not assume GPU VRAM capacity based on the laptop marketing name: one recent UI report showed **6.88 GB free**. Plan for the *actually available* VRAM, Windows/WSL differences, virtual environments, disk limits and worker concurrency.

---

## 1. CURRENT REPOSITORY BASELINE: VERIFY, DO NOT BLINDLY RE-IMPLEMENT

The published GitHub `main` snapshot inspected on 2026-10-30 was commit `19301cce59a10688fb3eb0d110b3e98036a25b0e` from 2026-10-29. The registry had **22 entries**, including **11 internally evaluated research models**, a third-party chest-radiograph option and framework/placeholder entries. An October 29 report predating the added CXR registry entry counted 21; this is a **historical version difference, not proof of corruption**. The user’s local application may be ahead: reconcile actual current contents and routes.

### Preserve and independently verify these ELEVEN existing research models

| Registered ID | Task | What to verify in the current project |
|---|---|---|
| `gi_kvasir_v2_classifier` | 8-class GI endoscopy image classification | Checkpoint hash; classification route; no fabricated lesion boundary |
| `gi_gastrovision_27class_classifier` | Exploratory 27-class GI endoscopy classification | Rare-class reliability; scope; input applicability; no clinical claims |
| `angiography_stenosis_detector` | Coronary angiography stenosis object detection | Source boxes, thresholded mAP, weak recorded performance |
| `angiography_syntax_segmenter` | Coronary vessel/SYNTAX-segment segmentation | Actual mask alignment, segment labels, weak recorded performance; no automatic clinical SYNTAX score |
| `kidney_stone_detector` | CT-slice kidney stone detection | Source image boxes, patient-level generalization, false positives |
| `gi_kvasir_seg_polyp_segmenter` | Endoscopic polyp mask segmentation | Correct COCO-RLE/source pixel overlay; strongest first vertical slice |
| `hematology_cnmc_all_classifier` | Leukemia cell-image classification | Slide/image eligibility, hematology ground truth, **not** arbitrary smear diagnosis |
| `ptbxl_ecg_baseline` | Digital 12-lead ECG multilabel classes | Current validated research upload code, signal contract and known parity test; not printed ECG images |
| `acdc_cardiac_mri_3d_unet` | Constrained cardiac cine-MRI 3D segmentation | NIfTI and assembled DICOM research paths, affine and orientation caveats, source slice masks |
| `heart_failure_survival_cox` | Heart failure exploratory outcome model | Evaluation-only unless patient applicability/calibration gates proven |
| `pbc_mayo_survival_cox` | Liver disease survival model | Evaluation-only unless population/censoring/calibration gates proven |

Other registry rows may include `mura_study_baseline` (weights missing), `brain_imaging_adapter` (missing), `lung_imaging_adapter` (missing), legacy `gi_endoscopy_adapter` (missing despite working specific GI models), `medcat_adapter`, `radgraph_adapter` (dependencies/weights missing), `scispacy_adapter`, `clinical_rules_v1`, `monai_runtime`, unsupported DeepSA adapter, and `cxr_torchxrayvision_densenet121` (third-party pretrained research model, not independently evaluated by MedTwin). **A framework adapter is not a disease model.**

Previously executed held-out/implementation reports described 11 matching local checkpoint hashes, 9 research-upload pathways (7 2D image + PTB-XL + ACDC), 2 survival evaluation-only models and no external evaluation. Verify today's local files before repeating these counts. The optional chest radiograph research model can have 18 whole-image thoracic scores, 14 anatomy segment labels and Grad-CAM on a compatible CXR, but **Grad-CAM is not a lesion outline**; a photograph of a film may be out-of-domain. Never transfer the bounding box from an unrelated demonstration image onto an actual user image.

**Specific current files to trace:**

- `src/pages/MedicalImagingPage.tsx`, `src/components/ResearchModelPanel.tsx`, `src/pages/*Anatomy*`, relevant overlays, DICOM viewer and upload center.
- `backend/app/routers/research_models.py`, imaging/series routers and endpoints, API registration.
- `backend/app/services/model_inference.py`, `volume_inference.py`, `ecg_inference.py`, `imaging_readers.py`, `anatomy_evidence.py`, spatial registration and rendering logic.
- `model_registry/models.json`, `model_registry/validation_status.json`, `dataset_registry/tasks.json` and evaluation/model-card bundles.
- `docs/verification/COMPLETENESS_AUDIT_2026-10-29.md`, `docs/validation/UPLOAD_INFERENCE_PARITY.md`, and newer verified local test reports.

### Required first diagnostic report

Create `docs/implementation/REAL_IMAGE_FAILURE_MATRIX.md`: upload type/file signature → case/examination → route → model eligibility → license/weight/hash → quality gate → worker/job state → API error → 2D result → persisted provenance → frontend overlay → anatomical association → source evidence → root cause and patch/test. Include failures and successful examples. Avoid identifiable filenames in public/agent summaries.

---

## 2. END-TO-END MEDICAL INPUT ARCHITECTURE: UNIVERSAL INGESTION ≠ UNIVERSAL DIAGNOSIS

Implement a verified, extensible and secure ingest router for **all user-requested medical inputs** while refusing unrelated disease inference. Allow optional offline research analysis of compatible uploads; keep deterministic parsing separate from learned model inference.

### Inputs and quality metadata

| Family | Supported candidate digital formats and conditions | Main processing features |
|---|---|---|
| Radiography | DICOM DX/CR, original X-ray image; JPG/PNG/BMP research frames, film photographs separately marked | Photometric interpretation, laterality, AP/PA view, lung/bone windows, artifact/quality gates |
| CT/CTA/CCTA | DICOM series, NIfTI, NRRD, MHA/MHD | Group slices correctly, PixelSpacing/affine, HU calibration, window/level, 3D masks |
| MRI/MRA | DICOM, NIfTI, NRRD, MHA | T1/T2/FLAIR/DWI/ADC/SWI/perfusion, sequence and acquisition checks, volume geometry |
| Ultrasound | DICOM US, PNG/JPG, clips where permitted | B-mode vs Doppler/EUS/echocardiography, depth/scale/probe view, motion/quality metadata |
| PET/SPECT/PET-CT | DICOM NM/PT, volumes, paired CT/PET with true registration | Uptake quantification ONLY if required metadata correct, reference-aware focal activity detection |
| Angiography/fluoroscopy | DICOM XA, cine clips, frame image | Vessel/stenosis segmentation, temporal motion/contrast quality, source-frame coords |
| GI and non-GI endoscopy | PNG/JPG/BMP, DICOM video, authorized MP4/MKV/AVI clips | Scope family and organ check, frame extraction, candidate lesions, temporal tracks |
| Digital pathology | Whole-slide SVS/NDPI/MRXS/OME-TIFF/TIFF and microscopy frames | WSI pyramids and metadata, tiling, stain/quality control, coordinate-to-slide boxes/masks |
| Ophthalmology | Fundus JPEG, retinal OCT volumes, fluorescein angiography when supported | Vessel/disc/lesion segmentation; OCT layer-specific models distinct from fundus |
| Dermatology | Dermoscopy JPG/PNG and clinical photographs | Lesion segmentation and classification with skin-tone/device robustness audit |
| Dental/ENT | DICOM dental radiographs/CBCT, otoscopy/laryngoscopy digital frames | Dedicated dental/ear/airway models; not GI classifier reuse |
| ECG | WFDB .hea+.dat, validated time-column CSV and eligible standard formats | Digital signal quality, leads, unit/Hz constraints, arrhythmia research classification |
| EEG/other biosignals | EDF/EDF+/BDF and eligible signal metadata | Channel and physical-unit validation; seizure models only if trained and evaluated |
| Clinical documents | PDF, scanned pages, DOCX, image reports, CSV, XLSX, HL7 v2, FHIR R4 | Page boundaries, OCR/layout, lab metrics, entities, review, assertions, dates, provenance |

**Data integrity and security:** All input types must have file magic/MIME checks, size/quota limits, hostile parser protection, archives/zip-bomb and decompression limits, content-addressed storage, case identity/access verification, encryption as configured, reprocessing idempotency, immutable raw evidence, revocable share permissions and audit events. Prevent mixed-patient source documents from being silently assigned to one patient. Mask/burned-in text de-identification must be reviewed. Never send PHI to a third-party API by default.

**Ingestion pipeline (required in code):** `case authorization → upload/metadata validation → file-specific scanner & quality controls → modality / organ / acquisition recognition (with abstention) → eligibility and supported task mapping → verified model gate → asynchronous inference → normalized results with original coordinates → persistent evidence → imaging viewer → clinical review → anatomy association → report / scientific evaluation`. Each stage returns a typed, explainable refusal, not a blank panel.

**Mandatory typed failure and evidence states:** The backend and frontend must consistently expose `MODEL_UNAVAILABLE`, `WEIGHTS_MISSING`, `DEPENDENCY_MISSING`, `LICENSE_BLOCKED`, `DATASET_BLOCKED`, `INPUT_NOT_SUPPORTED`, `MODEL_INPUT_INCOMPATIBLE`, `OOD_INPUT`, `IMAGE_QUALITY_INSUFFICIENT`, `NO_GROUND_TRUTH`, `NOT_CALIBRATED`, `REGISTRATION_UNAVAILABLE`, `MAPPING_UNSUPPORTED`, `INSUFFICIENT_LONGITUDINAL_EVIDENCE`, `NO_VALIDATED_FORECAST`, `PENDING_CLINICIAN_REVIEW`, and `CLINICALLY_UNVALIDATED` where appropriate. Each state includes a user-readable reason and exact missing prerequisite; do not swallow a model error and show a blank viewer.

Do not silently convert a CT series to a random PNG and apply unrelated 2D weights. If an eligible 2D model is designed for slices, preserve slice selection and original affine; distinguish preview conversion from valid model inference.

---

## 3. UNIVERSAL SPECIALTY REGISTRY — DIRECT-VISUALIZATION AND ENDOSCOPIC PROCEDURES

For **each row** register actual target condition taxonomy, scoped anatomy, label provenance, permitted input formats, model family, training and inference contracts, true 2D/temporal output type, anatomical mapping level, metrics, clinical-review requirement and **explicit missing prerequisites**. Add code and tests for ingestion and annotation even when no eligible checkpoint can yet exist. A named condition without data and labels is **NOT_IMPLEMENTED**, not a functioning model.

| Department / procedure | Anatomy / candidate research targets (only if properly labeled) | Correct output |
|---|---|---|
| Upper GI gastroscopy / EGD | Esophagus, stomach, duodenum; polyps, esophagitis, erosion, ulcers, visible bleeding and suspicious lesions | Distinct image class, region boxes, masks, mucosal landmarks |
| Colonoscopy / flexible sigmoidoscopy | Rectum/colon; colorectal polyps, colitis, visible ulcers, bleeding, masses, anastomotic appearances | Polyp instance masks, visible lesion boxes, per-frame tracking if annotated |
| Capsule endoscopy / enteroscopy | Small bowel; polyps, bleeding, angioectasia, ulcers, mucosal inflammation | Framewise detections, clip timestamp, lesion review, temporal events |
| Bronchoscopy | Trachea, bronchi; obstruction, suspicious masses, inflammation, foreign body, bleeding | Airway segmentation, lesion boxes/masks, landmarks |
| Cystoscopy | Bladder/urethra; mucosal masses, bladder tumors *as suspected lesions*, inflammation, bleeding | Separate bladder-specific masks/boxes and reviewed labels |
| Ureteroscopy | Ureters, collecting system; calculi, strictures, lesions, obstruction | Calculus/lesion masks/boxes and reviewed urinary anatomy |
| Laparoscopy | Abdominal and pelvic organs; organ planes, adhesions where labeled, lesions, instruments | Organ segmentation, structure labels, time-based surgical tracks |
| Arthroscopy | Knee, shoulder, hip; cartilage defects, meniscus changes, ligament regions, synovitis | Anatomy labels, candidate defect masks, clip tracking |
| Hysteroscopy | Endometrial cavity, uterine cavity; polyps, submucosal fibroids, suspicious mucosal regions | Uterine landmarks, region boxes/masks |
| Otoscopy / otoendoscopy | Ear canal, tympanic membrane; perforation, inflammation, cerumen | Ear-specific segmentation, region labels, reviewed class outputs |
| Ophthalmoscopy / retinal fundus | Retina, optic disc/cup, retinal vessels; exudate, hemorrhage, microaneurysm where annotated | Fundus masks, optic structures, image scores |
| Retinal OCT / angiography | Retinal layers, fluid pockets, neovascular features where annotated | OCT volume masks, layer boundaries, projections |
| Laryngoscopy / nasopharyngoscopy | Larynx, vocal folds, pharynx; visible lesions, vocal-fold motion | Lesion masks, per-frame labels and timing where eligible |
| Endoscopic ultrasound (EUS) | GI wall, pancreas, adjacent organs; eligible US-visible lesions | EUS-specific masks; **not** RGB Kvasir inference |
| Colposcopy / cervicoscopy | Cervix; transformation zone, acetowhite regions, visible suspicious change | Dedicated cervix lesion masks, review and uncertainty |
| Thoracoscopy / pleuroscopy | Pleura, lung exterior; suspicious pleural regions and thoracic organs | Eligible video segmentation, annotated organ targets |
| Urologic/gynecologic surgical endoscopy | Relevant organ and instrument views | Specialty anatomy segmentation, injury evidence only with ground truth |

**Special endoscopy geometry rule:** Standard monocular RGB scopes do not provide unique metric 3D lesion coordinates or a map of the entire organ. If no calibrated stereo/depth, SLAM, endoscope position, CT-derived geometry or verified mapping exists, the 3D twin may indicate **organ-level or reviewed subregion association only**. Do not invent a colon segment, bronchi branch or bladder wall coordinate from a single unlocalized photograph. Pathology/histology is needed to confirm many cancers, etiologies and malignant subtypes; a visual suspicion label is not histologic diagnosis.

### Video implementation specifics

Add high-resolution digital clip upload with codec/container checks; record frame index, fps, timestamp and source byte hash; do deterministic extraction; implement clip-level QC (blur, saturation, specular highlights, smoke, tools, black frames), temporal sampling and optional reviewed tracking (ByteTrack/DeepSORT-style methods only if appropriate), and visually stable overlays. Preserve original frame coordinates and track IDs. Measure per-video false alarms, lesion-wise recall and temporal consistency on **video/session/patient-separated** datasets. Never apply frame-level random splits to contiguous clips.

---

## 4. ALL RADIOLOGY, PATHOLOGY AND HOSPITAL DEPARTMENTS — TASK MATRIX

**Register every specialty below even when the model is not yet available. Onboard only the datasets and models for which the label ontology, population, acquisition characteristics and license have actually been verified.**

| Department / organ | Medical images and research targets | Eligible model families / outputs |
|---|---|---|
| Neurology / neurosurgery | Brain MRI tumor/edema/necrosis, ischemic CT/MRI stroke, intracranial hemorrhage, white-matter lesions, vascular lesions | BraTS-type multi-sequence segmentation, CT hemorrhage box/mask, DWI/FLAIR models; **different labels, not generic tumor cancer recognition** |
| Cardiology / cardiothoracic | Coronary XA stenosis, vessel segments, cardiac MRI ventricles, echocardiography structures/LVEF, chest findings | Detector/segmenter, 3D cine segmentation, Echo video research, dedicated calc/quality gates |
| Pulmonology / respiratory | Chest X-ray findings, pneumothorax, CT lung nodules, lung anatomy, airway abnormalities and bronchoscopy | Multilabel CXR classification, lesion detector, pneumothorax mask, volumetric nodule segmentation |
| Hepatology / hepatic surgery | Liver CT/MRI, liver lesion masks, steatosis ultrasound, fibrosis clinical/lab research | Liver/tumor segmenter, liver US classifier, validated lab models |
| Pancreatology | Pancreas CT/MRI organ segmentation, pancreatic cyst/lesion only with labels, EUS | Pancreatic voxel masks, supervised lesion segmentation with imaging-specific ground truth |
| Nephrology / urology | Kidney CT stone, renal masses, KiTS19 tumor segmentation, urinary ultrasound, bladder endoscopy, CKD CSV | Renal/bowel organ segmentation, stone detector, dedicated tabular outcome model |
| Gastroenterology / colorectal | Upper and lower GI stills/videos, polyps, inflammatory bowel disease, ulcers, esophagitis, GI tissue pathology | Image classifier, separate polyp/lesion segmenter, video-localization model, report/NLP evidence |
| Orthopedics / rheumatology | MURA MSK radiographs, bone fractures, OA, MRI joint structures, arthroscopy | Study-level classifier, fracture detector, OA severity model, cartilage/meniscus segmenter |
| Hematology / pathology | Blood-cell microscopy, leukemia morphology, marrow histology, hematopathology | Cell detector/classifier, WSI/tile segmentation; separate diagnostic validation from morphology |
| Breast / gynecology | Mammography/US/MRI breast masses, BUSI masks, endometrium/cervix/hysteroscopy | Organ/lesion masks, calibrated classification, image-level labels where that is all the data supports |
| Obstetrics / fetal medicine | Fetal ultrasound anatomy, biometry when metadata & landmarks permit, CTG digital signals | Landmark/segmentation models, properly bounded biometry and signal classifiers |
| Endocrinology | Thyroid ultrasound nodules, diabetic retina/OCT, pancreas/gland imaging and lab trends | Nodule masks, retina lesions, validated tabular biochemical trends |
| Oncology | Distinct organ/tumor tasks across radiology, PET and histopathology | Separate target-specific masks, case-based comparison; no generic universal cancer diagnosis |
| Ophthalmology | Retina/fundus/OCT, retinal diseases, anterior segment | Retina segmentation, pathology-specific models, eye anatomy views |
| Dermatology | Dermoscopy and skin lesion photographic data | Lesion masks, scoped classifiers and bias evaluation |
| Dentistry / maxillofacial | Dental panoramic X-ray, bitewings, CBCT, TMJ | Tooth/missing-tooth/caries/radiolucency annotations where scientifically supported |
| ENT | Otoscopy, audiology records, laryngoscopy/nasopharyngoscopy and CT temporal bone | Tympanic membrane/airway models, bounded clinical document evidence |
| Infectious diseases | Scans/medical reports/lab and microbiology | Detect *visible patterns* or explicit lab evidence only; do not infer pathogen identity from an image without validated pathogen-specific ground truth |
| Emergency / critical care | CT hemorrhage, emergency chest abnormalities, trauma, ultrasound FAST | Dedicated urgent-finding models, flagged research output, immediate clinician review |
| Nuclear medicine | PET, SPECT, PET-CT/SPECT-CT | Correct DICOM quantitative correction; lesions/uptake only for appropriately validated tracers/scanners |
| General surgery / procedural | Laparoscopic, thoracoscopic, robotic surgical video and visible pathology | Video organ/tool segmentation, surgical anatomy and scope-specific labels |
| Whole-body anatomy | CT multi-organ masks, body systems, atlas ontology | nnU-Net/TotalSegmentator-appropriate organ masks, source geometry, 3D volume/surface, atlas association |
| Other departments | Add via config for vascular surgery, pediatrics, genetics, transplantation, rehabilitation and specialty niches | Explicit applicability/unsupported labels, never free-form diagnosis from mismatched model |

Provide a **reusable onboarding template** for every new medical task: task ID; clinical problem and exclusions; modality/organ; input shape/voxel units; exact target and annotated hierarchy; dataset publisher/link/license/ethics; normal/abnormal controls; split strategy; architecture; preprocessing; training run; checkpoint SHA; source geometry; calibration; evaluation; external tests; intended-use disclaimer; UI route; patient-specific mapping eligibility; review owner; and current blockers.

---

## 5. MODEL DEVELOPMENT, TRAINING AND ONBOARDING: ACTUAL RESEARCH, NOT PLACEHOLDERS

### Dataset audit and acquisition policy

1. Use existing `dataset_registry` plus local `D:\project` and archives first. Inventory content by SHA-256 and canonical source dataset ID, not ZIP filename. A source code ZIP is not a clinical dataset; annotations-only archives are not usable paired training examples. Avoid duplicate copies.
2. Create `docs/data/VERIFIED_DOWNLOAD_AND_TRAINING_GAPS.md` with **only actual missing material** (link, original publisher, Kaggle mirror if any, exact file type/size estimate, annotation schema, license/consent, duplicate source risks, model/task, priority, how to verify after download). Do not automatically download many GB without express permission, or misrepresent Kaggle community licenses as original-publisher authorization.
3. Known gaps to recheck, not assumptions: KiTS19 masks without matched CT volumes; LIDC-IDRI XML annotations without DICOM images; LUNA16 partial subsets; BraTS 2021, BTCV and pancreas CT labeled volumes not established; NIH Chest X-ray and pneumothorax masks not verified as complete. Existing Kvasir v2, Kvasir-SEG, GastroVision, ACDC, PTB-XL, ARCADE, C-NMC, renal stones, MURA, liver, ECG and CSV cohorts should be rechecked before download.
4. Dataset candidates by task (not pre-approved): BraTS, ACDC, KiTS19, LiTS, BTCV, TotalSegmentator CT, Pancreas-CT, LIDC-IDRI/LUNA16 (overlapping), NIH ChestX-ray14, CheXpert (license/conditions), RSNA Pneumonia, SIIM Pneumothorax, EchoNet-Dynamic (permissions), MURA, public fracture sets, Kvasir-SEG, GastroVision, GI video polyp datasets, gland/bladder/bronchoscopy/cystoscopy/arthroscopy/hysteroscopy/otoscopy datasets only after independent provenance verification, BUSI, HAM10000, retinal OCT, diabetic-retinopathy fundus, DDTI thyroid, PI-CAI, dental labeled sets, EEG seizure sets, NIH/C-NMC and histology studies. For text: MTSamples, IU Chest X-ray paired narratives, NBME, FUNSD, DocLayNet, PubLayNet, CORD, and a properly licensed **clinical lab-report source-linked ground-truth set**. General receipts/layout datasets do **not** validate clinical lab interpretations.
5. Do not treat LUNA16 as independent external validation for LIDC-IDRI; check shared patients/source. Do not train on unsupported disease claims from folder titles, classifier inference, synthetic descriptions or pathology absent from reference labels.
6. Patient/study/volume/slide/video-disjoint splits. Deduplicate identical, near-identical and augmented images before split. Segmentation masks must line up geometrically. Endoscopic video frames must stay in the same group. WSI tiles from the same patient/slide must not cross partitions. Lock test sets before hyperparameter selection.
7. For one new model at a time: verify license → schema and labels → dataloader smoke test → baseline training → validation → threshold/calibration → held-out evaluation → independent review → checkpoint hashing/model card → gated research inference → UI and performance regression tests.

### Architectures and algorithm choices — fit task, not buzzwords

- **2D classification:** torchvision ResNet/DenseNet/EfficientNet or suitable ViT; support multiple labels where appropriate; prevalence/threshold evaluation; no geometry from logits.
- **Object detection:** appropriately licensed YOLO-family or Faster R-CNN/RetinaNet; select based on verified boxes and task; mAP/AP50/lesion-wise recall and false-positive analysis.
- **2D segmentation:** MONAI 2D U-Net, nnU-Net where appropriate, DeepLab/SegFormer; correct transform inversion, source-aligned pixel masks and boundary performance.
- **3D segmentation:** MONAI 3D U-Net / DynUNet, nnU-Net v2, optional licensed pretrained TotalSegmentator for *supported organ labels*, SWIN-UNETR if resources permit; sliding-window and tiled prediction; NIfTI/DICOM geometry verification. TotalSegmentator is anatomical segmentation, not comprehensive tumor diagnosis.
- **Video:** per-frame classifier/detector with temporal aggregation or tracking; spatiotemporal architectures only if enough labeled sequences and compute. Do not claim lesion tracking from uncalibrated video registration.
- **WSI pathology:** slide pyramids, batched tile inference, slide-level MIL if slide annotations exist; spatial aggregation and slide/patient-disjoint evaluation.
- **ECG/EEG:** typed digital signal readers, 1D CNN/ResNet/CNN-LSTM/transformer baselines with patient-disjoint splits and frequency/unit gates; no photo ECG substitution.
- **Clinical tabular/survival:** logistic/regression, XGBoost, Cox and competing-risk models as justified; calibration, censoring, population and endpoint verification.
- **NLP:** rule baseline, medspaCy assertion and section processor, scispaCy/MedCAT terminology, BioBERT/ClinicalBERT encoder baselines where legally available, relation extraction when eligible; no generation of ungrounded medical findings.
- **Segmentation foundation models** (e.g. SAM or MedSAM if compatible/licensed): optional reviewer-assisted annotation or weak/zero-shot research baseline; cannot be silently declared medically validated or lesion-specific without evaluation.

### Mandatory training/evaluation run contract

For each new model implement: resolved dataset manifest and rights; exact labels and harmonization; train/val/test identity/group manifests; augmentation only on train; reproducible seeds; frozen hyperparameters; environment lock; device precision and OOM fallback; checkpoints and SHA-256; raw validation/test predictions; model card; per-class confusion/PR/ROC when applicable; calibration/threshold curves; failure cases/OOD checks; case-independent test and external cohort status; reproducible run command; registry entry only after evidence exists. Never fabricate or copy metrics from different model/dataset pairings. Mark failures and train-blocked tasks rather than inventing weights.

Optimize for available laptop GPU: mixed precision only when numerically supported, gradient accumulation, crop/patch training, small batches, activation checkpointing, CPU fallback and job queue, explicit disk budgets. Avoid concurrent training and live inference exhausting VRAM. Do not attempt to train all departments in one blind loop.

---

## 6. REPAIR THE ACTUAL 2D DETECTION / HIGHLIGHT FAILURE FIRST

**This is the first executable milestone. Do not proceed to dozens of new models before proof of one complete verified upload → prediction → saved source-aligned overlay.**

### First positive end-to-end research test: Kvasir-SEG

Using a permitted **de-identified Kvasir-SEG held-out sample** and an actual locally hashed research checkpoint:

1. Create or choose an authorized isolated synthetic research case; create exam; upload as IMAGE/eligible JPG or PNG, not REPORT/PDF.
2. Check magic bytes, source image dimensions, orientation and lossless byte hash; record input contract and model scope.
3. Verify `gi_kvasir_seg_polyp_segmenter` appears as compatible only for eligible GI endoscopy inputs, not chest X-ray/brain MRI.
4. Run server inference through the real job queue and model checkpoint; verify hash, genuine mask output, pixel grid and RLE decode.
5. Invert preprocessing exactly and overlay the mask on the same source pixels. Verify scaling, letterbox padding, EXIF orientation, crop, zoom, pan and full-screen alignment using pixel coordinate tests and visual QA.
6. Show mask color/opacity legend, model ID, evidence status, display threshold where meaningful, original image toggle, source filename redacted, review status and calibrated versus raw score semantics.
7. Persist inference run and mask; reload case/browser, prove overlay remains; allow clinician reviewer to accept/reject/correct an annotation without altering immutable raw prediction.
8. Link to the generic intestines/colon Blender anatomy as `SCHEMATIC_ORGAN_ONLY` unless independently reviewed colon segment evidence is available; **no exact colon-wall 3D marker** from standalone RGB still.
9. Include a compatible negative example, an inapplicable non-GI image, a missing-weights test, worker-error test, unauthorized-case test and no-annotation performance abstention test.
10. Run unit tests, integration test, Playwright browser visual alignment test and Codex independent review. Record exact results and failure causes.

### Second positive test: actual detection boxes

Using permitted samples that match the real detector distribution:
- `kidney_stone_detector`: source-aligned kidney-stone candidate boxes, score and limitations.
- `angiography_stenosis_detector`: source-aligned coronary stenosis candidate boxes; expose low internal mAP and threshold outcomes, even if 0 boxes are valid.
- `angiography_syntax_segmenter`: true source-aligned vessel labels; don't infer a complete clinical SYNTAX score without fully supported logic and reviewed segments.
- No fabricated positive boxes if model predicts no eligible objects.

### Third positive test: actual volumetric masks

- `acdc_cardiac_mri_3d_unet`: eligible NIfTI or research-assembled DICOM cine MRI within the registered input envelope. Verify frame and phase, voxel spacing and source native orientation; execute model inference, visualize axial source masks and reconstruct a true patient-derived cardiac volume/surface **if full appropriate geometry is available**.
- Check correct DICOM rescale/resampling, qform/sform, LPS/RAS and IJK→world transforms, not just a rendered montage. Existing parity on publisher test frames is not scanner-native external validation.
- Display correct cardiac structure masks/volumes and clear research-only limitations. Do not call normal chamber segmentation a cardiac lesion detector.

### Optional chest-X-ray example: distinguish classifier from detector

Your supplied examples include a **photographed printed chest X-ray** and an **unrelated demonstrative CXR with a red box**. Never transfer the demonstrative red box or declare a mass in the photograph simply because of it. In scope: compatible digital frontal chest radiographs may be processed by the optional TorchXRayVision model when its dependencies and publisher weights are verified. Display image-level class scores and coarse Grad-CAM as *attention/explainability*, with lung/heart anatomy outlines where supported, not precise tumor masks. For an actual lesion box, train/integrate and evaluate a box-labeled CXR nodule/opacity detector. Film photographs are explicitly domain-shifted and may be unsuitable.

---

## 7. UNIVERSAL ANNOTATION AND MEDICAL IMAGE VIEWER: 2D, VIDEO, VOLUME, WSI

Implement a modality-aware viewer with interoperable typed results rather than a single image canvas.

### 2D viewer

- Original pixels, calibrated image display where appropriate; window/level, inversion, zoom/pan, orientation, scale bars, slice selection, patient-side markings.
- Actual model boxes, boxes below threshold optionally dashed, instance/semantic masks, labels and class legend; adjustable opacity, toggles, multiple-model layers; source pixel-coordinate traceability and mask export.
- Distinguish `GROUND_TRUTH`, `MODEL_PREDICTION`, `REVIEWED_ANNOTATION`, and `EXPLANATION_HEATMAP`. Never blend them into an unlabeled one-color overlay.
- Manual edit tooling for verified reviewers: brush, eraser, polygon, box, landmarks, undo/redo, comment, confidence, approve/reject/version. Raw model result immutable; reviewed corrected annotation separate.
- On large images, tiled overlays with consistent transform, no clipping or stretching; 16-bit grayscale images should not be normalized in a way that changes clinical interpretation.

### DICOM/MRI/CT volumes

- Integrate appropriate existing reader or Cornerstone3D/OHIF when needed; keep original source datasets immutable. Support series grouping by FrameOfReferenceUID, SeriesInstanceUID, orientation, slice projection and frame timing, not filename order alone.
- MPR (axial/sagittal/coronal), proper voxels/spacing/units, volume controls, overlay masking per plane, interactive contours, spacing-aware measurements, segmentation review, 3D volume/mesh surface, visibility layers and click-through to original slices.
- DICOM SEG export only when geometry/references meet DICOM specification (use vetted pydicom/highdicom). NIfTI labelmaps and source-affine matrices are acceptable research alternatives.

### Endoscopy/arthroscopy/laparoscopy/etc. videos

- Frame/time scrubber, pause, overlay class/track, patient/endoscopy-session grouping, saved clips, time-aligned source, reviewer timeline and clip quality indicators.
- If only still-image model exists, clearly call inference `FRAMEWISE_RESEARCH_ONLY`; no unsupported video temporal diagnostic claim.

### Whole-slide imaging

- Multi-resolution pyramid reader with tile coordinates, WSI-specific slide_id, heatmap/region overlay, cell detection review; aggregate only with a trained slide-level method and report scope/validation.

### Rendering contracts

Provide typed JSON/API schemas, e.g.:

```json
{
  "kind": "instance_segmentation",
  "case_id": "<authorized-case>",
  "source_file_sha256": "<64-character-hash>",
  "frame_index": null,
  "model_id": "gi_kvasir_seg_polyp_segmenter",
  "model_checkpoint_sha256": "<real-checkpoint-hash>",
  "preprocessing_version": "<pinned-version>",
  "native_image_size_hw": [0, 0],
  "native_to_model_transform": "<serialized-transform>",
  "mask_source_coordinate_system": "pixel_xy",
  "annotation_uri": "<case-authorized-reference>",
  "research_only": true,
  "human_review_status": "PENDING",
  "anatomy_link_level": "SCHEMATIC_ORGAN_ONLY"
}
```

The JSON above is a **schema illustration**, not an actual model output; reject zero dimensions and invented hashes in real API validation. Use proper schema types rather than storing literal placeholder values.

---

## 8. THREE DISTINCT 3D ANATOMICAL EVIDENCE LEVELS — ABSOLUTELY NO FAKE COORDINATES

Preserve **10 existing anatomical systems**, **43 GLB variants** and their model license/attribution metadata. Keep whole-body skeletal, muscular, vascular, nervous and organ layers, transparency, cutaway/section planes and interactive naming. Do not assume all 3,898 named atlas structures are independent clean meshes or registration-ready.

### L1 — Generic Blender anatomy / schematic association

For a text report, 2D X-ray, endoscopy still or unregistered model finding: map supported **organ or broad anatomical region** to a generic GLB using a validated ontology/label mapping. Display organ highlight and source evidence, e.g. `SCHEMATIC_ORGAN_ONLY`, `NOT_PATIENT_SPECIFIC`. No exact lesion point, false depth or tumor 3D volume. Even a reviewed clinician-confirmed finding does not create new patient-specific geometry.

### L2 — Clinician-reviewed atlas-region association and verified registration

- If a report/document names a distinguishable supported atlas substructure, obtain human confirmation and mark `REGION_VERIFIED` without asserting 3D lesion location.
- Actual spatial mapping requires source DICOM/NIfTI 3D volume, correct study geometry and registration assumptions, matched patient anatomy, landmarks/segmentation and independently evaluated transforms. Store transform chain, coordinate spaces, physical units, inverse transform and review metrics.
- Registration options may include SimpleITK/ANTs-compatible rigid/affine/deformable pipelines but require task-specific checks and fold/Jacobian/landmark QC. Compare TRE in **mm**, surface Dice/HD95, organ contours, landmark agreement and robust failure cases, using independent validation landmarks not optimized by the same transform.
- Some 3D findings may instead be rendered directly in native patient volume space without registration to generic Blender reference; that is often the more honest and precise first 3D workflow.

### L3 — Patient-derived 3D geometry and source-linked lesion mesh

When **the patient's own** compatible CT/MRI scan has a real organ/lesion segmentation, create a patient-derived surface/volume using marching cubes or a trusted 3D segmentation mesh process; preserve metadata and orientation. Display lesion-specific geometry co-registered in **the same native image frame**. Only project onto generic Blender atlas when a validated source-to-atlas transform exists. Record source slice/frame, voxel ID, physical point, confidence/uncertainty, ROI mask, transformation, landmark validation and review status.

### Transform math / explicit coordinate responsibilities

- For voxel index vector `i = (i,j,k,1)^T`, compute patient physical coordinates via the header's real affine: `p_patient = A_native * i`. In DICOM use validated direction cosines, row/column spacing and slice geometry with the right conventions, LPS/RAS as required.
- If a separately validated patient→atlas transform `T` exists, `p_atlas = T * p_patient` for affine rigid mappings; deformation requires a proper field sampler, not a naive matrix multiply.
- The UI mesh frame may require another explicit `T_atlas_to_threejs`, with units and handedness validated. Do not use screenshot pixel x/y to invent a z coordinate.
- Persist invertible transforms where mathematically valid, uncertainty, coordinate conventions and flags for unsupported transformations. Test known synthetic geometric phantoms for sign, axis and unit reversal; synthetic phantoms are **geometry QA only**, never clinical findings.

### Important modality limits

- Single-view X-ray is a projection, generally no unique 3D lesion coordinate; can show region-level schematic or registered biplanar reconstruction only if genuinely validated.
- RGB endoscopy/retina/fundus/dermoscopy typically lacks patient-scale 3D coordinates; use schematic/region-level links unless calibrated mapping is independently justified.
- MRI/CT segmentation of a normal organ is **not** proof of tumor detection. A lesion-specific mask requires a lesion-trained model or independently reviewed annotation.
- A PDF narrative describing a lesion does not supply actual voxel coordinates.

### Required anatomical UI behavior

Click actual 2D mask/box → display source evidence and relevant organ/region in anatomy viewer (schematic unless registered). Click organ → see reviewable relevant images, report statements, original coordinates and model versions. L2/L3 displays should expose how registration was validated, and offer a toggle between generic reference and patient-derived segmentation. Always distinguish predicted versus human-edited geometry. Cache patient meshes only within authorized case access; do not leak between cases.

---

## 9. THE ACTUAL IMAGES IN THIS REQUEST — TREAT AS VISUAL TARGETS, NOT GROUND TRUTH

The user supplied illustrative examples of: (i) a phone photograph of a printed chest X-ray (with potentially identifying markings), (ii) a **different** X-ray already bearing a red detection box, (iii) a 3D brain with colored regions, (iv) a four-column colonoscopy image showing baseline/annotation/algorithmic/pathological layers, and (v) a multi-color brain tumor segmentation illustration.

**Required product experiences inspired by these examples** (without copying claims or converting illustration colors into medical labels):
- CXR: actual source photo shown with research applicability warning; if a suitable model returns valid coordinates, overlay its actual boxes; a picture of a red box does not make those coordinates true for another radiograph.
- Endoscopy: original image | human annotation | algorithmic mask | ground-truth/pathology reference only when truly provided. If histopathology does not match the exact case, do not call it confirmation. Keep visual columns synchronized.
- Brain: actual multi-class MRI segmentation labels shown with source-aligned colored masks on orthogonal planes and a native patient-derived 3D view when segmented volume permits; separate tumor, edema, enhancing tumor, necrosis only if the trained dataset and labels define them. Do not import sample screenshots as true patient scan results.
- Generic Blender brain / lung: schematic colored highlighting and labels on verified substructures. Actual patient-specific lesion mesh only where scan geometry supports it.

Neither these illustrations nor the user's scanned reports form a scientifically labeled ground-truth training/test dataset; do not run training on them by default. Check for personal identifiers before any export or external processing.

---

## 10. MEDICAL DOCUMENT INTELLIGENCE, BIO-MARKER NLP AND EVIDENCE CONCORDANCE

**Preserve the existing RapidOCR and transparent clinical-rule pipeline. Upgrade, measure and test rather than silently replacing it.** Required document types: PDFs with embedded text, scanned multi-page PDFs, DOC/DOCX, image-embedded scans, laboratory tables, narrative radiology reports, pathology and biopsy reports, physician notes, hospital requisitions, invoices/bills (administrative, not medical tests), structured CSV/XLSX, HL7 and FHIR observations.

### Layered extraction

- Embedded PDF text/pypdf and DOCX tables/paragraphs first where reliable; use original page images for scanned or low-confidence regions.
- RapidOCR as current baseline; PaddleOCR PP-StructureV3 for structure/table detection; optional Marker/Surya on difficult pages. Optional Tesseract/OCRmyPDF to add searchable layers. Optional experimental Unlimited-OCR must be separately benchmarked for hallucinations, numerical errors, VRAM and license; do not install all overlapping engines automatically.
- Layout reconstruction: page orientation, line/word polygon, headings, sections, tables/cells/rows/columns, header propagation, multi-page table continuation, original page coordinates, page/source-document grouping and uncertainty.
- Biomedical concept processing: medspaCy negation/context/sectioning, scispaCy/MedCAT terminology when installed and licensed, ClinicalBERT/BioBERT task-specific models (not vague transformer labels), RadGraph relation extraction if eligible weights exist, source-linked structured JSON and conservative abstention.
- Dates and source identity: collection time, observation time, procedure date, report date, encounter date, user-entered case date; do not collapse all into one visit. Detect multi-patient bundles and hold conflicting identities for authorized review.
- Clinical assertions: affirmative/negated/hypothetical/uncertain/historical/family history; e.g. `No pleural effusion or pneumothorax` must not become an affirmative diagnosis. Disease mentions in billing and requisitions are not confirmed diagnoses.
- Lab analyte correctness: full analyte identity (HDL ≠ total cholesterol; LDL ≠ HDL), value, unit, decimal/separators, reference interval, specimen (serum/plasma/EDTA whole blood), method, collection date, abnormality flag, original source cell and LOINC mapping only with sufficient evidence. Preserve raw versus normalized values, unit conversions, reviewer versions and duplicates.
- Correct and benchmark recurring failures: missing reference ranges, duplicate values across repeated pages, incorrect 2024/2025/2026 source dates, incorrect specimen identity, negation errors, unsupported eGFR/risk estimates and cross-patient false merges.
- Reviewer workspace: original scanned page beside extracted structured table, confidence/uncertainty and highlighting, editable fields and clinician approval/rejection, versioned audit. No silent replacement of original extraction or automatic application of unapproved corrections.

### Scientific benchmarks

A genuine gold-standard **de-identified** annotated lab/report dataset must provide ground-truth text spans or original image coordinates, test→value→unit→reference-range table-cell relations, negation, dates, specimen, patient linkage and reviewer adjudication. General FUNSD/DocLayNet/receipt datasets train layout/NER helpers, **not clinical extraction accuracy**. Report CER/WER, numeric exact match, field F1, table relationship correctness, source IoU, negation/context F1 and patient/exam matching; no synthetic test figures passed off as clinical results.

---

## 11. MODEL-TO-MODEL AND 2D-TO-3D COMPARISON WORKFLOWS

### Compare actual algorithms on the same eligible task

- At least two separately frozen, independently evaluated models of **the same task, label taxonomy and suitable modality** can be run on the same authorized image/study. Align their masks/boxes to original source coordinates and display side-by-side; show overlays, disagreement masks/uncertainty and model cards.
- **Never** rank a classifier against a detector by comparing raw accuracy to mAP, or compare a GI model to a chest-X-ray model. Shared-label and acquisition eligibility is mandatory.
- Aggregate held-out cohort performance: macro/micro F1, AUROC/AUPRC, Dice/IoU/HD95, mAP/FROC, calibration and CIs where appropriate; all have real denominators and true labels.
- For individual input without ground truth: show prediction differences and calibrated-score limitations; **do not show per-patient accuracy/Dice** as though the unknown truth were known. Reviewer annotations are separate until independently adjudicated.

### Compare actual 2D findings with 3D anatomy

- For a registered volumetric case, select a 3D lesion/organ mesh and jump to original CT/MRI slices in axial/sagittal/coronal views. Compare identical native-image-space mask geometry against mesh in mm, show intersection and optional geometric consistency checks.
- For a 2D surface/endoscopy or single radiograph without registration: show organ/verified-region **association**, not coordinates. Compare only evidence links and semantic label alignment.
- Show disagreement (`ANATOMICAL_MISMATCH` / `UNREGISTERED`), reviewed corrections and source-provenance links rather than “the model pinpointed it” without evidence.

### Longitudinal old-versus-current scans

- Require same patient, reliably dated exams, compatible organ and acquisitions, verified source orientation, frame-of-reference and quality; independent registration where needed. Never register unrelated patients or conflate timepoints.
- Compare lesion mask volumes, diameters, number of lesions and credible morphometric changes only when measurement definitions are consistent. Account for measurement error and slice thickness, not just raw percent change.
- Historical PDF and lab value deltas remain distinct from geometric scan comparison. No “healing/progression” causality without appropriate expert assessment.

---

## 12. FORECASTING, DISEASE RISK AND TREATMENT SCENARIOS — BUILD RESEARCH SCIENCE, NOT FICTITIOUS FUTURE IMAGES

The user wants future prediction for all organs. Implement the **infrastructure, research task registry and honest unavailable states universally**, while enabling each specific forecast only with appropriate longitudinal outcomes and external evaluation.

- For each organ/system, define prediction **target**, event and time horizon (e.g., adjudicated event by 1 year, lesion volume at specified follow-up, biomarker trend), patient population, required visits, censoring/competing events and clinically relevant input fields.
- Baselines: last-observation carried forward / linear regression / mixed-effects / ARIMA when mathematically appropriate, Cox/elastic-net/gradient-boosted survival, competing-risks methods, temporal deep-learning only where enough true longitudinal data exist. Use patient-disjoint temporal validation, calibration over horizons, missing-data methods, uncertainty bands and external cohort validation.
- For scan/image progression: register multi-timepoint images, define lesion-correspondence/volume measurement and compare **observed** data first. A neural net that can generate synthetic future anatomy is not a validated clinical forecast. Keep such research visualizations clearly hypothetical and separated from patient evidence, or disable them.
- For treatment A versus B: require a defined causal estimand, exposure assignment, confounders, positivity and target-trial or equivalent methodology, independent validation. Do **not** infer that a medication will shrink a lesion based on a Cox risk score or a menu choice.
- Display `OBSERVED`, `RESEARCH_ESTIMATE`, `FORECAST_ELIGIBLE`, `FORECAST_UNAVAILABLE`, `CAUSAL_EFFECT_UNAVAILABLE`, real horizon and uncertainty. Prognosis Studio should show exact missing inputs and the relevant scientific blockers when it cannot forecast.
- Do not generate treatment instructions or drug dosage for patients from unvalidated research models. Drugs/protocols may be sourced as reference material, with clinician review and appropriate scope.

---

## 13. MULTIMODAL FUSION, CONCORDANCE AND EXPLAINABILITY

- The three requested user modes must remain supported: document-only, scan-only, combined. Add digital ECG/EEG as typed evidence without forcing all cases to have all modes.
- Do not fuse modalities until they are truly **paired for the same patient and relevant examination/date**, labels/target definitions match and trained/validated fusion weights are available. Use modality masks for missing data, honest abstention and explicit concordance/disagreement review.
- Before a paired fusion model, implement **evidence-level concordance**, not learned inference: compare source radiology narrative against compatible image model findings with clinical assertion, site, date and acquisition caveats. Flag contradictions rather than averaging them into a fake unified probability.
- Model explanations: validated Grad-CAM for image-level *attention* (not exact lesion); Integrated Gradients and SHAP/feature attribution for eligible models with baseline and version recording; segmentation masks show the actual model output. Store explainability provenance and limitations.
- If no approved ground truth exists, explanations do not establish correctness. Flag `NO_PAIRED_MODEL`, `UNCOMPARABLE`, `UNVERIFIED_MODALITY`, `NOT_CALIBRATED` and case-review status appropriately.

---

## 14. SCIENTIFIC VALIDATION AND REQUIRED METRICS

Create two distinct workflows under Validation Center:

**A. Clinical Case Review:** case-authorized source images/reports, actual model boxes/masks, annotations, field corrections, review approvals/rejections, clinician notes, provenance and audit. This establishes human-review history, **not a statistically valid model test set** by itself.

**B. Scientific Model Evaluation:** explicitly versioned, licensed, train/test-separated cohort with frozen checkpoints and labels; independently adjudicated ground truth; numeric class-specific report; calibration, uncertainty, error analysis, fairness/site/vendor subgroup breakdown, patient/video/slide split integrity and reproducible scripts. Report external cohorts separately from held-out internal results.

| Task | Metrics and tests to compute from real truth |
|---|---|
| Binary/multiclass/multilabel classification | Accuracy/balanced accuracy, sensitivity, specificity, precision/recall, macro/micro F1, AUROC/AUPRC with valid class support, confusion matrix, calibration/ECE/Brier, CIs |
| Detection | COCO mAP@[0.50:0.95], AP50, false positives per image/study, FROC, lesion-wise recall, per-site error |
| 2D/3D segmentation | Per-class Dice, IoU, HD95, surface Dice, volume error and slice/case-wise uncertainty; test affine/orientation consistency |
| Endoscopy and surgical video | Lesion/event-level recall, false alarms per minute/procedure, tracking continuity, latency; patient/procedure separation |
| ECG/EEG | Per-class AUROC/AUPRC/F1, signal quality error, recording/patient split, threshold calibration |
| Tabular/survival and prognosis | Harrell C/time-dependent AUC, integrated Brier, horizon calibration, competing-risk checks and CIs |
| NLP and lab OCR | CER/WER, numeric exact match, table-cell relation accuracy, assertion/temporality and source span F1, patient/time/specimen linking |
| 3D mapping | Physical voxel-to-world error, independent landmark TRE mm, surface consistency/HD95, left-right inversion tests, transformation/inverse stability |
| Operational | API/job success, queue recovery, p50/p95 latency, VRAM peak, on-disk footprint, PHI leaks, role isolation |

Compute metrics only when appropriate truth exists and class support is adequate; record actual sample sizes and CIs with defined clustering/resampling. Do not use the same validation data to tune and claim final performance. Record calibration thresholds and provenance by model and dataset version.

---

## 15. MODEL REGISTRY, DATASET REGISTRY AND CASE UI: ONE SOURCE OF TRUTH

### Model Registry

Each registered model must show: specialty, organ system, modality/acquisition contract, task (classification/detection/2D mask/3D mask/video/signal/tabular), exact class taxonomy, ground-truth source, dataset version/license, checkpoint SHA/present status, preprocessing, output geometry, installed dependencies, GPU memory requirement, quality/OOD gate, applicable population and confidence calibration, internal and external test reports, inference endpoint and current case eligibility. Differentiate `REGISTERED`, `DEPENDENCY_MISSING`, `DATASET_BLOCKED`, `WEIGHTS_MISSING`, `TRAINED`, `RESEARCH_RUNNABLE`, `INTERNAL_EVALUATION`, `EXTERNAL_EVALUATION`, `CLINICAL_NOT_AUTHORIZED`, `FAILED`, `UNSUPPORTED_INPUT`.

### Dataset Registry

Separate **path-discovered** data (may be 33 roots and many overlapping media files), **dataset units** (may be 61), **task-specific manifests** (may be 32) and *actually eligible train/validation partitions*. A UI banner saying `0 of 33 training eligible` from path discovery does not negate 10 ready tasks in a separate task audit. Display which view each number belongs to; never merge them into a single misleading readiness percentage.

### Case and clinical workspaces

Maintain: Overview Dashboard, Case Workspace, Document Intelligence, Medical Imaging, Biomarker Analytics, Historical Comparison, Live Anatomy Studio, Prognosis Studio, Multimodal Intelligence, Risk & Explainability, Research Analytics, Model Registry, Dataset Registry, Validation Center, Reports, My Record and Settings. Add image-specific review queues and model-comparison UX without breaking existing routes.

Security: patient/caregiver/researcher/clinician/admin role gates, only verified professional reviewer sign-off, proper self-registration default, case consent/sharing, per-user evidence access, session management, safe evidence version/withdrawal, immutable audit and correct data retention. Evaluate missing CRUD (case/exam edits, upload replacement, review correction), but **do not assume older gaps persist**; check current local implementation and tested routes. Do not weaken permissions to make QA easier.

---

## 16. DEPENDENCY AND FRAMEWORK INTEGRATION — USE REAL RUNTIMES, NOT ZIP COLLECTIONS

**Inspect installed versions and existing source archives before installing anything.** Do not copy entire third-party `*-main` trees into the application import path or blindly overwrite requirements files. Pin compatible environments and check upstream licenses and pretrained weight terms separately.

| Framework | Actual intended use | Safe decision |
|---|---|---|
| PyTorch, MONAI | 2D/3D classification/segmentation/training | Reuse working CPU/CUDA locks and existing inference paths |
| nnU-Net v2 | Automated medical organ/lesion segmentation training | Integrate as separate research adapter only where data and hardware fit |
| TotalSegmentator | Pretrained supported multi-organ CT/MR anatomy masks | Verify current supported modalities, weights/license and memory; **not** universal lesion detector |
| OpenCV | Denoise, CLAHE, quality checks, morphology, contour overlays | Modality-appropriate reversible preprocessing; preserve medical units/metadata |
| SimpleITK, NiBabel | Image space, affine/registration, NIfTI/volume processing | Unit/coordinate conformance testing required |
| pydicom, highdicom | DICOM image metadata and segmentation objects | Verify references and DICOM SEG validity |
| Cornerstone3D or OHIF | Rich DICOM/MPR frontend | Prefer a single viewer strategy, not parallel full stacks |
| MONAI Label | Human-in-the-loop research annotation | Optional; integrate only if productive and compatible |
| RapidOCR, PaddleOCR PP-StructureV3 | Baseline and table-aware document OCR | Benchmark against same eligible de-identified reports |
| Marker, Surya, OCRmyPDF/Tesseract | Optional PDF layout/OCR alternatives | Avoid uncontrolled dependencies and VRAM conflicts |
| medspaCy, scispaCy, MedCAT, RadGraph | Assertion/NER/concept linking/relation extraction | Do not label active if weights/install missing; isolate WSL where needed |
| Transformers | Specialized clinical biomedical encoder/relation models | Install pinned; choose eligible checkpoint, do not download whole models blindly |
| TorchXRayVision | Optional 3rd-party chest classifier and anatomy masks | Research only; verify weights and domain shift; Grad-CAM is not lesion mask |
| Playwright and Codex plugin | Browser QA and independent source review | Verify commands and plugin login; no uncontrolled agent conflict |

Do not download additional Kaggle datasets or source ZIPs before generating the missing-files manifest. Prefer dataset publisher originals when Kaggle mirrors are partial or legally unclear. Use carefully scoped environment splits for incompatible Python/CUDA/Windows packages.

---

## 17. REPRODUCIBLE GPU/WORKER/TEST/DEPLOYMENT ENGINEERING

- Check Python virtual environments, CUDA/PyTorch device compatibility, JIT and ONNX/CUDA behavior, memory, CPU fallback and import errors; create isolated model environments as needed. Avoid globally changing system Python.
- Worker scheduling with bounded GPU jobs, queue leases, crash/timeout retry, cancellation and out-of-memory handling; preserve idempotency and avoid duplicate inference. Do not run clinical uploaded data through external services without authorization.
- Tests: Python unit/integration, dataset schema/geometry checks, ML checkpoint load/smoke, deterministic test phantoms, model output type validation, frontend TypeScript/build, Playwright interactions for upload/result/anatomy/persistence, role isolation and security; CI with cheap non-PHI fixtures. Full external validation is not a unit test.
- Inspect Dockerfiles and deployment configs; do not assert production/cloud readiness because compose YAML parses or a server returns 200. Maintain encrypted object storage, least-privilege DB access, backup/restore drills, audit integrity, secrets rotation, secure file handling and privacy reviews for production.
- Design for laptop first, optional server GPU later. No blanket guarantee of real-time high-resolution pathology, full-body 3D segmentation or all endoscopy video streams on 7 GB free VRAM.

---

## 18. MILESTONE-BASED IMPLEMENTATION PLAN — EXECUTE, TEST, REPORT AND CONTINUE

**Use this order. Begin the first phase immediately after read-only inspection. If blocked by missing data, keep building independent infrastructure and log blockers; do not mark blocked models operational.**

| Milestone | Deliverable proven with real test | Mandatory failure/negative case |
|---|---|---|
| M0. Baseline + safety | Diff of local vs GitHub, 11 checkpoints, actual services, privacy/role gates, failure matrix | Unauthorized patient/case or bad upload rejected |
| M1. Real 2D polyp mask | Authorized Kvasir-SEG → actual model mask → pixel-aligned overlay → persisted review → schematic colon | Mismatched CXR refused by GI model |
| M2. Real boxes | Kidney stone + coronary stenosis eligible sources → source boxes with genuine model quality disclosure | No fabricated positive if threshold gives zero |
| M3. Volumetric cardiac proof | Valid ACDC NIfTI/DICOM → actual slice masks → physical coordinates → patient-derived chamber surface where possible | Affine/spacing/view mismatch refused |
| M4. Whole-body anatomy and L1/L2/L3 | All GLB variants intact; source-linked organ clickthrough; patient mesh from eligible volume | X-ray/endoscopy cannot yield arbitrary lesion 3D coordinates |
| M5. First new missing specialty model | **One** selected from BraTS, lung, kidney, pancreas, liver, bone based on verified dataset → training + test + overlay | Insufficient labeled/allowed data blocks training |
| M6. Video and specialty onboarding | One authorized endoscopy/surgical clip through temporal viewer + reviewed framewise inference if eligible | Incompatible scope model refused |
| M7. Multimodel and longitudinal comparison | Same-task aligned model comparison and observed longitudinal evidence with gates | Unpaired scans/unknown truth must not receive invented metrics |
| M8. OCR/NLP and clinical report confidence | Lab/date/negation/specimen corrections and case-review UX benchmarked on allowed data | Cross-patient document contamination rejected |
| M9. Future research forecasting | Fully defined horizon model tested on eligible longitudinal cohort, or truthful unavailable block | No fictitious future scan/treatment effect |
| M10. Whole-application QA | Verified API, worker, UI, reports, privacy, dependencies, datasets and progress ledger | Regression tests and Codex adversarial review passed |

**Per-milestone definition of done:** actual code changes (when needed), executed local command/log, exact environment/runtime, dataset/version/checkpoint hash, inference artifact hash, numeric evaluation if labeled truth exists, screenshot or sanitized image hash, UI/browser acceptance, verified negative case, privacy permission check, reviewer/Codex review, and remaining known limitations. A model menu entry or loaded library is **not completion**.

### Explicit blocker protocol

When all specialty models cannot be developed with available resources, do not stop or falsely report success: list *which precise task* lacks weights, complete images, annotations, license, GPU, clinical ground truth, external validation or registration. Generate a human-readable acquisition/engineering checklist and leave the platform's interfaces able to onboard those models later. Implement highest-evidence tasks first and track others as blocked in UI.

---

## 19. CONCRETE DELIVERABLE PATHS AND EVIDENCE LOGS

Only create new files if the existing canonical equivalent cannot be safely updated; reconcile duplicates. Required persistent outputs:

1. `docs/implementation/UNIVERSAL_MEDICAL_AI_PROGRESS.md` — one table of requirements, status, code path, test evidence, blockers and next action.
2. `docs/implementation/REAL_IMAGE_FAILURE_MATRIX.md` — end-to-end root cause by upload/model/UI.
3. `docs/research/UNIVERSAL_SPECIALTY_CAPABILITY_MATRIX.md` — every department/scope, correct label taxonomy and honest model readiness.
4. `docs/research/EXISTING_MODEL_CHECKPOINT_VERIFICATION.md` — 11 original models + optional third-party CXR; hashes, routes, benchmark and gaps.
5. `docs/research/MISSING_DATASETS_AND_WEIGHTS.md` — verified incomplete source files, annotation licenses, prioritized download list; no blind redownload.
6. `docs/research/TRAINING_AND_EXTERNAL_VALIDATION_PLAN.md` — deterministic experiment settings, data split, metrics and external testing for each task.
7. `docs/imaging/IMAGE_GEOMETRY_AND_REGISTRATION_CONTRACT.md` — DICOM/NIfTI orientation, native pixels → physical world → atlas/Three.js, exact gates.
8. `docs/imaging/ACTUAL_2D_3D_OVERLAY_ACCEPTANCE.md` — case evidence, mask/box alignment, segment visualization and browser tests.
9. `docs/research/ENDOSCOPY_VIDEO_AND_SCOPE_MODEL_MATRIX.md` — all direct-scope procedures and video task requirements.
10. `docs/research/MODEL_COMPARISON_AND_FORECAST_ELIGIBILITY.md` — same-task comparison, actual longitudinal data and guarded prognosis.
11. `docs/clinical/DOCUMENT_AND_BIOMARKER_EXTRACTION_GOLD_STANDARD.md` — source-linked NLP/OCR evaluation specification and evidence.
12. `docs/qa/UNIVERSAL_MEDICAL_AI_EXECUTED_TESTS.md` — commands, environment, pass/fail/skipped, run dates, anonymized artifacts.
13. `docs/security/MEDICAL_DATA_HANDLING_AND_ROLE_GATE_AUDIT.md` — verified privacy and roles, outstanding risk.
14. `docs/research/RESEARCH_CAPABILITY_BLOCKERS.md` — transparent NOT_IMPLEMENTED/UNAVAILABLE/NOT_VALIDATED table.

Keep PHI out of these files. If clinical records are used in approved local verification, record only de-identified aggregate outcomes and salted or non-reversible reference IDs; do not include names or screenshots that display burned-in identifiers.

---

## 20. CLAUDE CODE + CODEX EXECUTION PROCEDURE

**Start a Claude Code session inside `D:\project`** (the Codex CLI/plugin is already reportedly signed in; verify setup, do not reinstall unnecessarily). Read this file completely. For each milestone:

1. Have Claude inspect source and establish a minimal patch/test plan.
2. Have Codex independently review the exact design for failure modes, patient privacy, scientific suitability and hidden assumptions—**read-only** review whenever possible.
3. Claude implements a coherent small patch; do not have both agents rewrite the same code simultaneously.
4. Run real unit/integration/GPU/UI tests; compare actual image overlays against source-coordinate checks and true authorized labels when available.
5. Request Codex independent adversarial review of changed files, numerical math, security checks and negative-case behavior; resolve verified findings.
6. Update the persistent progress ledger, report model/geometry status honestly, and begin the next feasible milestone.

Example optional plugin commands after checking local command availability: `/codex:setup`, `/codex:review`, `/codex:adversarial-review`, `/codex:status`, `/codex:result`, `/codex:rescue`. A stop-time review gate may be on; use it for substantive changes but do not confuse it with code correctness or clinical approval. **Do not block all engineering indefinitely on repeated no-op reviews.**

**Launch request to execute this document:**

> “Read `D:\project\MEDTWIN_CLAUDE_CODEX_UNIVERSAL_MEDICAL_AI_MASTER.md` completely. Start with an audited local worktree and the actual failed 2D model upload. Preserve working modules and existing 11 research checkpoints. Implement the first real Kvasir-SEG detection/mask/review/schematic-anatomy vertical slice, run unit and browser tests, have Codex independently review it, then expand in evidence-based phases across all imaging specialties, 2D/3D, model comparisons, biomedical documents and carefully gated longitudinal forecasting. Never invent predictions, source coordinates or future scans. Update the progress ledger and report actual verified outcomes.”

**Begin the actual audit and first executable 2D detection/overlay repair now. Do not conclude that “everything is implemented” until each specific task has a real model, valid data, independent execution and test evidence; preserve explicit BLOCKED/UNAVAILABLE status for every unmet clinical/scientific prerequisite.**
