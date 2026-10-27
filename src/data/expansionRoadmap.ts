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
    currentCoverage: "Coronary stenosis, coronary segmentation, and an ECG research baseline",
    remainingGap: "Upload-ready cardiac MRI, echocardiography, and externally evaluated ECG",
    recommendation: "Keep ARCADE; verify ACDC and PTB-XL artifacts; add eligible echo data",
    action: "VERIFY_FIRST",
  },
  {
    system: "Brain",
    currentCoverage: "Reported stroke, haemorrhage, tumour, MS, and Alzheimer-related sources",
    remainingGap: "Volumetric tumour masks, white-matter lesions, and longitudinal progression",
    recommendation: "Keep current sources; add a provenance-cleared BraTS task",
    action: "ADD",
  },
  {
    system: "Lungs",
    currentCoverage: "Several CT cancer sources and locally present chest-radiology candidates",
    remainingGap: "Pneumonia, TB, pneumothorax, multilabel X-ray, and nodule localisation",
    recommendation: "Reconcile NIH, LIDC/LUNA, SIIM, and TB candidates before task activation",
    action: "VERIFY_FIRST",
  },
  {
    system: "Liver",
    currentCoverage: "LiTS candidate data plus fibrosis and fatty-liver ultrasound sources",
    remainingGap: "Clinical laboratory linkage, outcomes, and stronger ultrasound validation",
    recommendation: "Keep existing imaging; validate local clinical tables and label scope",
    action: "KEEP",
  },
  {
    system: "Pancreas",
    currentCoverage: "Generic anatomy asset; no dedicated validated pancreas model",
    remainingGap: "CT organ segmentation plus separately annotated tumour and cyst tasks",
    recommendation: "Add complete pancreas CT masks or a qualified BTCV task",
    action: "ADD",
  },
  {
    system: "Intestines",
    currentCoverage: "Kvasir v2 and GastroVision classification; Kvasir-SEG candidate",
    remainingGap: "Externally evaluated pixel masks and independent lesion localisation",
    recommendation: "Keep classifiers; verify Kvasir-SEG checkpoint, masks, and external testing",
    action: "VERIFY_FIRST",
  },
  {
    system: "Kidneys",
    currentCoverage: "Stone detection and reported cyst/tumour classification sources",
    remainingGap: "Renal tumour 3D segmentation and linked CKD measurements",
    recommendation: "Complete KiTS image-mask pairing and validate the CKD clinical table",
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
    currentCoverage: "MURA adapter without a verified checkpoint; fracture candidates present",
    remainingGap: "Fracture localisation, knee osteoarthritis, and spine abnormalities",
    recommendation: "High priority: verify MURA, fracture boxes, and OA labels as distinct tasks",
    action: "VERIFY_FIRST",
  },
  {
    system: "Hybrid full body",
    currentCoverage: "Generic anatomical GLB references",
    remainingGap: "Multiorgan segmentation, registration, and case-specific reconstruction",
    recommendation: "Add qualified multiorgan CT evidence; keep patient registration unavailable",
    action: "ADD",
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
    gate: "Require matched official CT volumes for the locally reported masks and clinical JSON",
  },
  {
    name: "Kvasir-SEG",
    system: "Intestines",
    capability: "Pixel-level colorectal polyp masks",
    priority: "CRITICAL",
    gate: "Verify the existing local image-mask pairs, split isolation, checkpoint, and evaluation",
  },
  {
    name: "TotalSegmentator CT",
    system: "Hybrid full body",
    capability: "Multiorgan anatomical segmentation",
    priority: "CRITICAL",
    gate: "Source code alone is insufficient; verify eligible weights, licence, and supported tasks",
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
