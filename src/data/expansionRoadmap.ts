export type RoadmapAction = "KEEP" | "ADD" | "VERIFY_FIRST";
export type RoadmapPriority = "CRITICAL" | "HIGH" | "OPTIONAL";

export interface SystemCoverageRow {
  system: string;
  currentCoverage: string;
  remainingGap: string;
  recommendation: string;
  action: RoadmapAction;
}

export interface DatasetCandidate {
  name: string;
  system: string;
  capability: string;
  priority: RoadmapPriority;
  gate: string;
}

export interface LabelBoundary {
  source: string;
  supportedClaim: string;
  unsupportedClaim: string;
}

/**
 * Programme-level roadmap supplied for MedTwin 2.0. These records are not
 * dataset-registry entries and must never be interpreted as downloaded,
 * licensed, training-eligible, or validated assets.
 */
export const SYSTEM_COVERAGE: SystemCoverageRow[] = [
  {
    system: "Heart",
    currentCoverage: "Coronary models, digital ECG, ECG with demographics, and cardiac MRI research inference",
    remainingGap: "Independent scanner-series, echo and ECG evaluation; clinical validation",
    recommendation: "Reuse ARCADE, ACDC, PTB-XL and existing EchoNet resources; evaluate before expanding",
    action: "VERIFY_FIRST",
  },
  {
    system: "Brain",
    currentCoverage: "RSNA haemorrhage classifier plus ISLES stroke and MSD glioma MRI segmentation",
    remainingGap: "External evaluation, EEG interpretation, white-matter lesions and progression",
    recommendation: "Finish CQ500 integrity review; preserve independent test data and MRI sequence contracts",
    action: "VERIFY_FIRST",
  },
  {
    system: "Lungs",
    currentCoverage: "Chest-radiograph classifier, lung anatomy masks and a prepared 299-patient LIDC consensus manifest",
    remainingGap: "Validated lesion localisation and disease-specific external evaluation",
    recommendation: "Train a bounded nodule task with suitable resolution and sampling, then evaluate independent patients",
    action: "VERIFY_FIRST",
  },
  {
    system: "Liver",
    currentCoverage: "Reference anatomy, evaluation-only PBC baseline and a verified 131-case MSD CT/mask manifest",
    remainingGap: "Registered liver lesion model, laboratory linkage, longitudinal outcomes and ultrasound validation",
    recommendation: "Complete commercial data-rights review before training a bounded liver/tumour model; independently validate it",
    action: "VERIFY_FIRST",
  },
  {
    system: "Pancreas",
    currentCoverage: "Generic anatomy, CT-organ adapter and an MSD pancreas preparation pipeline",
    remainingGap: "CT organ segmentation plus separately annotated tumour and cyst tasks",
    recommendation: "Audit existing MSD pancreas pairs before acquiring overlapping datasets or training",
    action: "VERIFY_FIRST",
  },
  {
    system: "Intestines",
    currentCoverage: "Kvasir v2 and GastroVision classifiers plus Kvasir-SEG polyp segmentation",
    remainingGap: "Externally evaluated pixel masks and independent lesion localisation",
    recommendation: "Retain current checkpoints; improve input applicability and procedure-separated external testing",
    action: "VERIFY_FIRST",
  },
  {
    system: "Kidneys",
    currentCoverage: "Kidney-stone detector; 210 paired KiTS19 cases; new combined model rejected after tumour Dice 0.000",
    remainingGap: "Renal tumour 3D segmentation and linked CKD measurements",
    recommendation: "Revise class sampling and loss on development data; reserve fresh independent evaluation and audit CKD tables",
    action: "VERIFY_FIRST",
  },
  {
    system: "Skin",
    currentCoverage: "PAD-UFES-20 image and image/attribute research classifiers; 304-image patient-separated internal test",
    remainingGap: "Independent external evaluation, rare-class evidence and clinical validation",
    recommendation: "Retain explicit attribute entry and refusal checks; validate population and acquisition differences before release",
    action: "VERIFY_FIRST",
  },
  {
    system: "Nervous system",
    currentCoverage: "Brain imaging and neurological-condition candidates",
    remainingGap: "EEG seizure detection, spinal cord, and peripheral nerve evidence",
    recommendation: "Validate the EEG source and patient split before developing a seizure task",
    action: "VERIFY_FIRST",
  },
  {
    system: "Skeletal system",
    currentCoverage: "MURA checkpoint with internal study-level evaluation; fracture box candidates present",
    remainingGap: "Fracture localisation, knee osteoarthritis, and spine abnormalities",
    recommendation: "Externally evaluate MURA; audit fracture boxes and OA labels as separate tasks",
    action: "VERIFY_FIRST",
  },
  {
    system: "Hybrid full body",
    currentCoverage: "Reference anatomy, TotalSegmentator CT adapter and scan-frame research surfaces",
    remainingGap: "Local evaluation beyond lungs, validated atlas registration and patient reconstruction",
    recommendation: "Use existing weights and DeepFluoro pairs; validate coordinates and specimen-separated transforms",
    action: "VERIFY_FIRST",
  },
];

export const DATASET_CANDIDATES: DatasetCandidate[] = [
  {
    name: "BraTS 2021 MRI",
    system: "Brain",
    capability: "3D glioma subregion segmentation",
    priority: "CRITICAL",
    gate: "Verify publisher source, access terms, multimodal volumes, masks, and patient split",
  },
  {
    name: "ACDC Cardiac MRI",
    system: "Heart",
    capability: "Cardiac chamber segmentation and function research",
    priority: "CRITICAL",
    gate: "Reconcile the existing registered evaluation bundle before acquiring another copy",
  },
  {
    name: "KiTS19",
    system: "Kidneys",
    capability: "Kidney and renal-tumour CT segmentation",
    priority: "CRITICAL",
    gate: "210 CT/mask pairs acquired and header-matched; subject-separated manifests and task training remain",
  },
  {
    name: "Kvasir-SEG",
    system: "Intestines",
    capability: "Pixel-level colorectal polyp masks",
    priority: "CRITICAL",
    gate: "Research checkpoint and internal evaluation exist; external evaluation and commercial permission remain",
  },
  {
    name: "TotalSegmentator CT",
    system: "Hybrid full body",
    capability: "Multiorgan anatomical segmentation",
    priority: "CRITICAL",
    gate: "Weights and dedicated research adapter exist; local evaluation covers lungs only, not all organs",
  },
  {
    name: "BTCV Abdomen 3D",
    system: "Abdomen",
    capability: "Multiorgan abdominal CT segmentation and registration research",
    priority: "CRITICAL",
    gate: "Require complete images, labels, provenance, and a patient-disjoint manifest",
  },
  {
    name: "Pancreas CT Segmentation",
    system: "Pancreas",
    capability: "Pancreatic anatomy segmentation",
    priority: "HIGH",
    gate: "Do not infer pancreatic cancer from organ masks",
  },
  {
    name: "LIDC-IDRI / LUNA16",
    system: "Lungs",
    capability: "Pulmonary-nodule annotation and detection research",
    priority: "HIGH",
    gate: "Match CT series to annotations and do not treat LUNA as independent LIDC validation",
  },
  {
    name: "NIH ChestXray14",
    system: "Lungs",
    capability: "Multilabel thoracic X-ray baseline",
    priority: "HIGH",
    gate: "Record weak-label limitations and patient-level split provenance",
  },
  {
    name: "SIIM Pneumothorax",
    system: "Lungs",
    capability: "Pneumothorax region segmentation",
    priority: "HIGH",
    gate: "Verify RLE-mask alignment and source-image completeness",
  },
  {
    name: "MURA v1.1",
    system: "Skeletal",
    capability: "Study-level musculoskeletal abnormality classification",
    priority: "HIGH",
    gate: "MURA does not support fracture localisation or fracture-type claims",
  },
  {
    name: "EchoNet-Dynamic",
    system: "Heart",
    capability: "Echocardiographic motion and cardiac-function research",
    priority: "HIGH",
    gate: "Verify official access terms, video metadata, patient grouping, and target definition",
  },
  {
    name: "Source-linked laboratory reports",
    system: "Clinical documents",
    capability: "Value, unit, date, specimen, interval, and page-location extraction",
    priority: "CRITICAL",
    gate: "Require lawful de-identification and independently annotated page/table/cell ground truth",
  },
  {
    name: "Retinal OCT / fundus",
    system: "Ophthalmology",
    capability: "Retinal disease classification",
    priority: "OPTIONAL",
    gate: "Expand only after core-system evidence and licence review are complete",
  },
  {
    name: "BUSI / HAM10000",
    system: "Oncology / dermatology",
    capability: "Breast-ultrasound and dermoscopic lesion research",
    priority: "OPTIONAL",
    gate: "Keep specialty tasks separate and validate labels, masks, and population scope",
  },
];

export const LABEL_BOUNDARIES: LabelBoundary[] = [
  {
    source: "LiTS",
    supportedClaim: "Liver and liver-tumour segmentation masks",
    unsupportedClaim: "Histologically confirmed hepatocellular carcinoma diagnosis",
  },
  {
    source: "Kidney four-class CT",
    supportedClaim: "The recorded kidney-image class label",
    unsupportedClaim: "Renal-cell-carcinoma subtype or pathology confirmation",
  },
  {
    source: "MURA",
    supportedClaim: "Study-level musculoskeletal abnormality classification",
    unsupportedClaim: "Fracture localisation, fracture type, or a normal study excluding every disease",
  },
  {
    source: "Kvasir v2",
    supportedClaim: "Eight endoscopic image categories, including landmarks and procedure findings",
    unsupportedClaim: "Eight distinct diseases or pixel-level polyp localisation",
  },
  {
    source: "PTB-XL",
    supportedClaim: "ECG statements and diagnostic group labels within the dataset definition",
    unsupportedClaim: "A confirmed acute cardiac event or calibrated patient risk",
  },
  {
    source: "ARCADE",
    supportedClaim: "Coronary anatomy segmentation or annotated stenosis detection for the selected task",
    unsupportedClaim: "A complete clinical SYNTAX score, ischaemic risk, or treatment recommendation",
  },
  {
    source: "ST000001",
    supportedClaim: "A study associated with its recorded source metadata",
    unsupportedClaim: "Ground-truth disease labelling without a qualified annotation source",
  },
];
