// Medical display names. Internal identifiers keep their source names (they key
// manifests, reports and checkpoints); everything the application shows goes
// through these maps. Original source names, authors and licences required for
// attribution appear only on the Data sources and licences page (/attribution).

const DATASET_NAMES: Record<string, string> = {
  // Audited dataset units (dataset_registry/tasks.json)
  "kvasir-v2": "GI endoscopy findings image set, 8 classes",
  "kvasir-v2-copy": "GI endoscopy findings image set, 8 classes (duplicate copy)",
  gastrovision: "GI endoscopy findings image set, 27 classes",
  arcade: "Coronary X-ray angiography image set",
  "tez-roi-aug-kidney-stone": "Renal calculus CT slice set",
  "brain-ct-hemorrhage-binary": "Brain CT, normal vs haemorrhage",
  "brain-stroke-ct": "Brain CT stroke set (normal, ischaemia, haemorrhage)",
  "brain-mri-tumor-4class-a": "Brain MRI tumour set, 4 classes (variant A)",
  "brain-mri-tumor-4class-b": "Brain MRI tumour set, 4 classes (variant B)",
  "mri-tumor-detection-small": "Brain MRI tumour detection set",
  "st000001-mr-study": "Single brain MR DICOM study (privacy review pending)",
  "lung-cancer-ct": "Lung cancer CT image set",
  "liver-ct-volumes": "Liver CT volumes with segmentation masks",
  "dataset-train-test-unlabelled": "Unlabelled image folders",
  "kidney-ct-normal-tumor": "Kidney CT, normal vs tumour",
  "kidney-ct-4class": "Kidney CT, normal, cyst, tumour and calculus",
  "2d-segmentation-pairs": "2-D image and mask pairs (organ not stated)",
  "liver-fibrosis-f0-f4": "Liver fibrosis ultrasound, stages F0–F4",
  "behsof-nafld": "Liver ultrasound, non-alcoholic fatty liver disease",
  "brain-mri-multicondition": "Brain MRI: tumours, Alzheimer stages, multiple sclerosis, normal",
  "brain-tumor-ct-mri": "Brain tumour vs healthy, CT and MRI",
  "cerebrovascular-lesions-ct": "Cerebrovascular lesion CT, 10 classes",
  "brain-stroke-ct-3class-external": "Brain CT haemorrhage, ischaemia and normal (external test)",
  "kvasir-seg": "Colorectal polyp endoscopy images with masks",
  "ptb-xl-1.0.1": "12-lead ECG diagnostic record set",
  "uci-heart-failure-clinical-records": "Heart-failure clinical records (survival)",
  "uci-cirrhosis-mayo-pbc": "Primary biliary cholangitis cohort (survival)",
  "acdc-cardiac-mri": "Cardiac cine-MRI with ventricular segmentations",
  "c-nmc-2019": "Leukaemia single-cell microscopy set (blast vs normal)",
  "bone-fracture-roboflow-v4": "Fracture radiograph detection set, 7 classes",
  "mura-v1.1": "Upper-extremity musculoskeletal radiographs (study level)",
  "echonet-dynamic": "Apical four-chamber echocardiography videos",
  "kits19-labels": "Kidney tumour CT segmentations (masks only)",
  "lidc-idri-xml": "Lung nodule CT annotations (annotations only)",
  "totalsegmentator-repository": "Multi-organ CT segmentation source code (no data)",
  "unknown-tfrecords": "Unidentified serialised record shards",
  "heart-csv": "Heart-disease clinical table",
  "stroke-csv": "Stroke risk-factor clinical table",
  "epileptic-seizure-csv": "Epileptic seizure EEG feature table",
  "indian-liver-patient-csv": "Liver patient clinical records",
  "hepatitis-c-csv": "Hepatitis C laboratory data",
  "kidney-disease-csv": "Chronic kidney disease records",
  "diabetes-prediction-csv": "Diabetes clinical table",
  "thyroid-csv": "Thyroid disease tables",
  "anemia-csv": "Anaemia laboratory table",
  "data-csv": "Unidentified clinical table",
  "pcos-tables": "Polycystic ovary syndrome tables",
  "fetal-health-csv": "Fetal cardiotocography features",
  "support2-csv": "Seriously ill hospitalised adults (prognosis table)",
  "voc-images-root": "Unidentified annotated image pairs",
  "roboflow-train-folder": "Unidentified annotated image export",
  "ultrasound-fetus": "Fetal ultrasound images",
  "lymphoma-cll-fl-mcl": "Lymphoma histology subtypes (CLL, FL, MCL)",
  "otoscopic-images": "Otoscopic images, 5 classes",
  mtsamples: "Medical transcription samples",
  "mtsamples-final": "Medical transcription derived table",
  "resized-images": "Unidentified resized image set",
  "nbme-patient-notes": "Clinical patient notes",
  medquad: "Medical question and answer pairs",
  "dataset-link": "Dataset link file only",
  "thermal-dataset-folder": "Thermal images",
  // Path-level discovery registry (dataset_registry/datasets.json)
  "2d-segmentation-dataset": "2-D image and mask pairs",
  behsof: "Liver ultrasound, non-alcoholic fatty liver disease",
  benchmarks: "Benchmark folders",
  "brain-stroke-ct-dataset": "Brain CT stroke set",
  "cerebrovascular-lesions": "Cerebrovascular lesion CT",
  data: "Shared imaging data folder",
  dataset: "Shared dataset folder",
  "dyed-lifted-polyps": "Dyed lifted polyps",
  "dyed-resection-margins": "Dyed resection margins",
  esophagitis: "Oesophagitis",
  "external-test": "External test images",
  "kvasir-dataset-v2": "GI endoscopy findings image set, 8 classes",
  lungcancerdataset: "Lung cancer CT image set",
  "mri-tumor-detection-dataset-training-and-testing": "Brain MRI tumour detection set",
  "normal-cecum": "Normal caecum",
  "normal-pylorus": "Normal pylorus",
  "normal-z-line": "Normal Z-line",
  polyps: "Polyps",
  segmentations: "Segmentation masks",
  "split-data": "Split image folders",
  st000001: "Single MR DICOM study (privacy review pending)",
  test: "Shared test folder",
  testing: "Testing folder",
  train: "Shared training folder",
  training: "Training folder",
  "ulcerative-colitis": "Ulcerative colitis",
  valid: "Shared validation folder",
};

const TASK_NAMES: Record<string, string> = {
  "kvasir-v2-8class": "GI endoscopy finding classification, 8 classes",
  "gastrovision-27class": "GI endoscopy finding classification, 27 classes",
  "arcade-stenosis-detection": "Coronary stenosis detection",
  "arcade-syntax-segmentation": "Coronary artery segment segmentation (SYNTAX segments)",
  "tez-kidney-stone-detection": "Renal calculus detection on CT slices",
  "brain-ct-hemorrhage-binary": "Brain CT haemorrhage classification",
  "brain-stroke-ct-3class": "Brain CT stroke classification, 3 classes",
  "brain-stroke-ct-lesion-segmentation": "Brain CT stroke lesion segmentation",
  "brain-mri-tumor-4class-a": "Brain MRI tumour classification, 4 classes (A)",
  "brain-mri-tumor-4class-b": "Brain MRI tumour classification, 4 classes (B)",
  "mri-tumor-detection-small": "Brain MRI tumour detection",
  "lung-cancer-ct-classification": "Lung cancer CT classification",
  "liver-ct-segmentation": "Liver CT segmentation",
  "kidney-ct-normal-tumor": "Kidney CT tumour classification",
  "kidney-ct-4class": "Kidney CT classification, 4 classes",
  "2d-segmentation-pairs": "2-D segmentation (organ not stated)",
  "liver-fibrosis-staging": "Liver fibrosis staging",
  "behsof-nafld-binary": "Non-alcoholic fatty liver disease classification",
  "brain-mri-multicondition": "Brain MRI multi-condition classification",
  "brain-tumor-ct-mri-binary": "Brain tumour classification, CT and MRI",
  "cerebrovascular-lesions-10class": "Cerebrovascular lesion classification, 10 classes",
  "brain-stroke-ct-3class-external": "Brain CT stroke classification with external test",
  "kvasir-seg-polyp-segmentation": "Colorectal polyp segmentation",
  "ptbxl-diagnostic-superclass": "12-lead ECG diagnostic superclass classification",
  "heart-failure-survival": "Heart-failure mortality (survival)",
  "pbc-survival": "Primary biliary cholangitis mortality (survival)",
  "acdc-cardiac-segmentation": "Cardiac MRI ventricular and myocardial segmentation",
  "cnmc-all-vs-normal": "Leukaemic blast vs normal cell classification",
  "bone-fracture-detection": "Fracture detection on radiographs",
  "mura-study-abnormality": "Musculoskeletal radiograph abnormality (study level)",
  "echonet-ef-regression": "Echocardiographic ejection fraction regression",
  "kits19-kidney-tumour-segmentation": "Kidney tumour CT segmentation",
};

const humanizeId = (value: string) => value.replace(/[-_]+/g, " ").replace(/\s+/g, " ").trim().replace(/^./, (first) => first.toUpperCase());

/** Medical name for a dataset unit or discovered path; never the source's own name. */
export function datasetName(id: string | null | undefined): string {
  if (!id) return "Unnamed dataset";
  return DATASET_NAMES[id] ?? humanizeId(id);
}

/** Medical name for an audited task. */
export function taskName(id: string | null | undefined, target?: string): string {
  if (!id) return "Unnamed task";
  return TASK_NAMES[id] ?? (target ? target.replace(/^./, (first) => first.toUpperCase()) : humanizeId(id));
}

type LicenseLike = { status?: string | null; name?: string | null; authorization_status?: string | null } | null | undefined;

/** Licence class without the source's name (the full text is on the attribution page). */
export function licenceLabel(license: LicenseLike): string {
  const name = license?.name ?? "";
  const open = /CC0 1\.0|CC BY(?:-NC)?(?:-SA)? \d\.\d/.exec(name);
  if (open) return open[0];
  if (/research and educational/i.test(name)) return "Publisher terms: research and educational use, citation required";
  if (license?.authorization_status === "VERIFIED") return "Publisher research release; citation required; owner-authorized local use";
  if (/research use agreement|PERMISSION_UNVERIFIED/i.test(`${name} ${license?.status ?? ""}`)) return "Individual research agreement required (not verified)";
  if (license?.status === "VERIFIED") return "Verified publisher terms";
  return "Licence not verified";
}

// Free text from generated reports and registry entries keeps its source names on
// disk (it is evidence); the app shows it with those names replaced.
const PUBLIC_TEXT: Array<[RegExp, string]> = [
  [/Strodthoff et al\.? 2020 \(IEEE JBHI\)/g, "A published 2020 benchmark"],
  [/\(PTB-XL, Physikalisch-Technische Bundesanstalt, recordings 1989-1996\)/g, "(single national ECG archive, recordings 1989-1996)"],
  [/PTB-XL superdiagnostic task/g, "ECG diagnostic-superclass task"],
  [/the PTB-XL lead order/g, "the source lead order"],
  [/Mayo Clinic primary biliary cirrhosis patients/g, "primary biliary cholangitis trial patients"],
  [/Kvasir\/Gastrovision data/g, "GI endoscopy data"],
  [/\bMURA\b/g, "Musculoskeletal radiograph"],
  [/\bACDC\b/g, "cardiac MRI"],
  [/\bKiTS\b/g, "kidney tumour CT"],
  [/\bMedCAT\b/g, "The concept-linking tool"],
  [/\bRadGraph\b/g, "radiology-relation"],
  [/\bMONAI\b/g, "the imaging deep-learning library"],
  [/spaCy's/g, "the NLP library's"],
  [/BC5CDR diseases\/chemicals/g, "diseases and chemicals"],
  [/MEDTWIN_SCISPACY=wsl/g, "the server's secondary-NER setting"],
  [/\bWSL\b/g, "an isolated Linux environment"],
];

export function publicText(text: string): string {
  return PUBLIC_TEXT.reduce((value, [pattern, replacement]) => value.replace(pattern, replacement), text);
}

const FRAMEWORK_LABELS: Record<string, string> = {
  "MONAI PyTorch 3-D U-Net": "3-D U-Net (volumetric convolutional network)",
  "MONAI UNet 2D": "2-D U-Net (convolutional segmentation network)",
  "torchvision resnet18": "ResNet-18 convolutional network",
  "torchvision efficientnet_b0": "EfficientNet-B0 convolutional network",
  "torchvision fasterrcnn_resnet50_fpn_v2": "Faster R-CNN detector (ResNet-50 feature pyramid)",
  pytorch: "1-D residual convolutional network",
  "numpy (ml_training/survival.py)": "Cox proportional-hazards model",
  pytorch_monai: "Deep-learning imaging runtime",
  monai: "Deep-learning imaging runtime",
  pytorch_transformers: "Transformer language model",
  spacy_scispacy: "Biomedical named-entity recognition pipeline",
  medcat: "Clinical concept-linking pipeline",
  python_rules: "Rule-based clinical text processing",
};

/** Architecture or method, without library names. */
export function frameworkLabel(value: string | null | undefined): string {
  return (value && FRAMEWORK_LABELS[value]) || "Not declared";
}

/** Runtime environment, without library names or versions. */
export function runtimeLabel(value: string | null | undefined): string {
  if (!value || value === "unresolved") return "Unresolved";
  if (value === ".venv") return "Local Python environment";
  if (value.startsWith("wsl:")) return "Isolated Linux NLP environment";
  if (value === "isolated-required") return "Isolated environment required";
  return "Declared environment";
}

/** Path-level licence status codes, without platform names. */
export function licenceStatusLabel(status: string | null | undefined): string {
  if (!status || status === "unknown") return "Unknown";
  if (/CC_BY_4_0/i.test(status)) return "CC BY 4.0 (declared for a scoped subset)";
  return humanizeId(status.toLowerCase());
}
