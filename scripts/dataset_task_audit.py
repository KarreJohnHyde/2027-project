"""Dataset governance and task-suitability audit for the imported source archives.

Inputs: docs/import/inventories/*.json and the per-archive entry manifests written
by scripts/archive_audit_and_extract.py (which map every archive entry to its
verified on-disk file, keeping archives separable where several were unpacked
into one folder).

Outputs:
  dataset_registry/tasks.json            dataset units, licence/privacy evidence, task readiness
  docs/data/DATA_READINESS_MATRIX.md     the same, for people
  _derived/datasets/<id>/samples.csv     sample manifests for training-eligible datasets (git-ignored)

A task is training-eligible only when its labels support the endpoint, its
licence was verified from an official source, and no privacy blocker applies.
Labels come from the dataset publisher's own structure (class folders, COCO or
YOLO files); archive file names never become labels.

Near-duplicates: 64-bit difference hashes, grouped by union-find at a Hamming
distance <= --dhash-threshold. Official splits are kept and checked for
cross-split near-duplicates; datasets without splits are split by group with a
fixed seed, so near-identical frames never straddle train and test.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORIES = ROOT / "docs" / "import" / "inventories"
MANIFESTS = ROOT / "_imports" / "archives" / "_manifests"
DERIVED = ROOT / "_derived" / "datasets"
SPLIT_SEED = 20261024
SPLIT_FRACTIONS = {"train": 0.70, "val": 0.15, "test": 0.15}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
VERIFIED_ON = "2026-10-24"

LICENSES = {
    "KVASIR": {"status": "VERIFIED", "name": "Kvasir terms of use: research and educational purposes only; commercial use requires written permission; cite the dataset paper",
               "source": "https://datasets.simula.no/kvasir/", "verified_on": VERIFIED_ON,
               "citation": "Pogorelov et al., Kvasir: A Multi-Class Image Dataset for Computer Aided Gastrointestinal Disease Detection, ACM MMSys 2017."},
    "GASTROVISION": {"status": "VERIFIED", "name": "CC BY 4.0", "source": "https://api.osf.io/v2/nodes/84e7f/ (OSF project 84e7f, license field)", "verified_on": VERIFIED_ON,
                     "citation": "Jha et al., GastroVision: A Multi-class Endoscopy Image Dataset for Computer Aided Gastrointestinal Disease Detection, ML4MHD @ ICML 2023."},
    "ARCADE": {"status": "VERIFIED", "name": "CC0 1.0", "source": "https://zenodo.org/records/10390295", "verified_on": VERIFIED_ON,
               "citation": "Popov et al., Dataset for Automatic Region-based Coronary Artery Disease Diagnostics Using X-Ray Angiography Images, Scientific Data 2024."},
    "TEZ_ROI_AUG": {"status": "VERIFIED", "name": "CC BY 4.0", "source": "in-archive README.dataset.txt and data.yaml (Roboflow Universe tez-nwkf5/tez_roi_aug v3)", "verified_on": VERIFIED_ON,
                    "citation": "Roboflow Universe project tez_roi_aug (workspace tez-nwkf5), version 3."},
    "UNVERIFIED": {"status": "UNVERIFIED", "name": "No licence file in the archive and no official source matched", "source": None, "verified_on": VERIFIED_ON},
    # Supplementary batch (archives 23-60), verified 2026-10-25.
    "KVASIR_SEG": {"status": "VERIFIED", "name": "Kvasir-SEG terms of use: research and educational purposes only; commercial use forbidden without prior written permission; cite the dataset paper",
                   "source": "https://datasets.simula.no/kvasir-seg/", "verified_on": "2026-10-25",
                   "citation": "Jha D, Smedsrud PH, Riegler MA, et al. Kvasir-SEG: A Segmented Polyp Dataset. MultiMedia Modeling (MMM) 2020."},
    "PTBXL": {"status": "VERIFIED", "name": "CC BY 4.0", "source": "LICENSE.txt in the archive; https://physionet.org/content/ptb-xl/1.0.1/", "verified_on": "2026-10-25",
              "citation": "Wagner P, Strodthoff N, Bousseljot R-D, et al. PTB-XL, a large publicly available electrocardiography dataset. Sci Data 7, 154 (2020)."},
    "UCI_HEART_FAILURE": {"status": "VERIFIED", "name": "CC BY 4.0", "source": "https://archive.ics.uci.edu/dataset/519/heart+failure+clinical+records", "verified_on": "2026-10-25",
                          "citation": "Chicco D, Jurman G. BMC Med Inform Decis Mak 20, 16 (2020); data of Ahmad T et al., PLoS ONE 12(7): e0181001 (2017)."},
    "UCI_CIRRHOSIS": {"status": "VERIFIED", "name": "CC BY 4.0", "source": "https://archive.ics.uci.edu/dataset/878/cirrhosis+patient+survival+prediction+dataset-1", "verified_on": "2026-10-25",
                      "citation": "Dickson ER, Grambsch PM, Fleming TR, Fisher LD, Langworthy A. Hepatology 10(1):1-7 (1989)."},
    "CNMC_TCIA": {"status": "VERIFIED", "name": "CC BY 3.0 (TCIA Data Usage Policy; citation required)", "source": "https://www.cancerimagingarchive.net/collection/c-nmc-2019/", "verified_on": "2026-10-25",
                  "citation": "Mourya S, Kant S, Kumar P, Gupta A, Gupta R. ALL Challenge dataset of ISBI 2019 (C-NMC 2019). TCIA (2019). doi:10.7937/tcia.2019.dc64i46r"},
    "BONE_FRACTURE_ROBOFLOW": {"status": "VERIFIED", "name": "CC BY 4.0", "source": "in-archive README.dataset.txt and data.yaml (Roboflow Universe veda/bone-fracture-detection-daoon v4)", "verified_on": "2026-10-25",
                               "citation": "Roboflow Universe project bone-fracture-detection-daoon (workspace veda), version 4."},
    # No licence text exists for ACDC, so availability alone never opened the training gate.
    # The repository owner then authorized local research training explicitly (2026-10-25).
    "ACDC": {"status": "SOURCE_AND_CITATION_VERIFIED_TERMS_NOT_FOUND", "authorization_status": "VERIFIED",
             "authorization_reason": ("Repository owner authorized local, non-commercial research training on 2026-10-25 after review of the official source: "
                                      "CREATIS states that the data and ground truth remain publicly available, the download collection is public, and the "
                                      "publisher requires the citation for any use. No licence text is published; the data are not committed or redistributed."),
             "authorized_by": "repository owner (recorded interactive decision)", "authorized_on": "2026-10-25",
             "authorization_scope": "local non-commercial research training and evaluation; no redistribution of images or masks",
             "name": "CREATIS ACDC public research release; mandatory citation; explicit licence terms not published",
             "source": "https://www.creatis.insa-lyon.fr/Challenge/acdc/databases.html (download: humanheart-project.creatis.insa-lyon.fr, public collection) and MANDATORY_CITATION.md in the archive",
             "verified_on": "2026-10-25",
             "citation": "Bernard O, Lalande A, Zotti C, et al. Deep Learning Techniques for Automatic MRI Cardiac Multi-structures Segmentation and Diagnosis: Is the Problem Solved? IEEE TMI 37(11):2514-2525 (2018)."},
    "KITS19": {"status": "VERIFIED", "name": "CC BY-NC-SA 4.0", "source": "LICENSE in the archive (KiTS19 challenge data repository)", "verified_on": "2026-10-25",
               "citation": "Heller N, et al. The KiTS19 Challenge Data: 300 Kidney Tumor Cases with Clinical Context, CT Semantic Segmentations, and Surgical Outcomes. arXiv:1904.00445."},
    # Stanford AIMI datasets: each user must register and accept the Research Use Agreement;
    # redistribution is prohibited. These copies arrived as Downloads/archive (N).zip, so the
    # user's own acceptance cannot be assumed.
    "STANFORD_RUA": {"status": "PERMISSION_UNVERIFIED", "name": "Stanford AIMI Research Use Agreement: personal, non-commercial research only; no redistribution; each user registers individually",
                     "source": "https://echonet.github.io/dynamic/ (agreement terms); https://aimi.stanford.edu/datasets/mura-msk-xrays", "verified_on": "2026-10-25",
                     "note": "Usable only after the user confirms their own Stanford AIMI registration and acceptance of the agreement for this dataset."},
}

# Curated from the archive inventories (class folders, metadata files) and official dataset pages.
DATASETS = [
    {"archive": "archive_16", "id": "kvasir-v2", "title": "Kvasir v2 (GI endoscopy)", "modality": "ENDOSCOPY", "system": "intestines",
     "identity": "8 publisher class folders x 1000 images, matching the official Kvasir v2 release", "license": "KVASIR",
     "labels": "CLASS_FOLDER", "label_root_depth": 2, "official_splits": False, "patient_ids": "NONE_AVAILABLE",
     "tasks": [{"id": "kvasir-v2-8class", "type": "CLASSIFICATION", "target": "8 Kvasir findings/landmarks per image"}]},
    {"archive": "archive_18", "id": "kvasir-v2-copy", "title": "Kvasir v2 (second copy, folders at project root)", "modality": "ENDOSCOPY", "system": "intestines",
     "identity": "same 8 classes x 1000 images as archive_16", "license": "KVASIR", "labels": "CLASS_FOLDER", "label_root_depth": 1,
     "official_splits": False, "patient_ids": "NONE_AVAILABLE", "duplicate_candidate_of": "archive_16", "tasks": []},
    {"archive": "archive_17", "id": "gastrovision", "title": "GastroVision (GI endoscopy, 27 classes)", "modality": "ENDOSCOPY", "system": "intestines",
     "identity": "27 publisher class folders, 8000 images, matching the OSF GastroVision description", "license": "GASTROVISION",
     "labels": "CLASS_FOLDER", "label_root_depth": 2, "official_splits": False, "patient_ids": "NONE_AVAILABLE",
     "tasks": [{"id": "gastrovision-27class", "type": "CLASSIFICATION", "target": "27 GastroVision classes per image", "min_per_class": 20}]},
    {"archive": "archive_06", "id": "arcade", "title": "ARCADE coronary X-ray angiography", "modality": "ANGIOGRAPHY", "system": "heart",
     "identity": "syntax/stenosis tasks with train/val/test 1000/200/300 and COCO annotations, matching Zenodo record 10390295", "license": "ARCADE",
     "labels": "COCO", "official_splits": True, "patient_ids": "NONE_AVAILABLE",
     "tasks": [{"id": "arcade-stenosis-detection", "type": "DETECTION", "target": "stenosis regions (COCO boxes, category 'stenosis')", "subset": "stenosis"},
               {"id": "arcade-syntax-segmentation", "type": "SEGMENTATION", "target": "25 SYNTAX coronary segments (COCO polygons)", "subset": "syntax"}]},
    {"archive": "archive_11", "id": "tez-roi-aug-kidney-stone", "title": "TEZ_ROI_AUG kidney stone detection (Roboflow)", "modality": "CT", "system": "kidneys",
     "identity": "Roboflow export with data.yaml (1 class 'Tas_Var', stone present) and YOLO labels", "license": "TEZ_ROI_AUG",
     "labels": "YOLO", "official_splits": True, "patient_ids": "NONE_AVAILABLE", "resplit_by": "FILENAME_TICKS_SESSION",
     "notes": ["Images are augmented ROI crops exported by Roboflow; augmented copies of one source image may exist.",
               "The publisher split is image-level: slices from one acquisition session (filename timestamps within 30 min) "
               "appear in train and test, so the task is re-split by session; the publisher split is kept as publisher_split."],
     "tasks": [{"id": "tez-kidney-stone-detection", "type": "DETECTION", "target": "kidney stone boxes (class Tas_Var)"}]},
    {"archive": "archive_00", "id": "brain-ct-hemorrhage-binary", "title": "Brain CT normal vs hemorrhagic (unidentified source)", "modality": "CT", "system": "brain",
     "identity": "Data/NORMAL (4105) and Data/Hemorrhagic (2690) JPEG slices", "license": "UNVERIFIED", "labels": "CLASS_FOLDER", "official_splits": False,
     "patient_ids": "NONE_AVAILABLE", "tasks": [{"id": "brain-ct-hemorrhage-binary", "type": "CLASSIFICATION", "target": "normal vs hemorrhagic slice"}]},
    {"archive": "archive_01", "id": "brain-stroke-ct", "title": "Brain stroke CT (Normal/Ischemia/Bleeding, DICOM+PNG, overlays, external test masks)", "modality": "CT", "system": "brain",
     "identity": "class counts 4427/1130/1093 match published descriptions of the Turkish Ministry of Health stroke data; distribution terms not verified",
     "license": "UNVERIFIED", "labels": "CLASS_FOLDER_AND_MASKS", "official_splits": True, "patient_ids": "UNKNOWN_DICOM_HEADERS_NOT_REVIEWED",
     "tasks": [{"id": "brain-stroke-ct-3class", "type": "CLASSIFICATION", "target": "normal / ischemia / bleeding"},
               {"id": "brain-stroke-ct-lesion-segmentation", "type": "SEGMENTATION", "target": "lesion masks (external test only)"}]},
    {"archive": "archive_02", "id": "brain-mri-tumor-4class-a", "title": "Brain MRI tumor 4-class (balanced variant)", "modality": "MRI", "system": "brain",
     "identity": "glioma/meningioma/notumor/pituitary, 1400/400 per class", "license": "UNVERIFIED", "labels": "CLASS_FOLDER", "official_splits": True,
     "patient_ids": "NONE_AVAILABLE", "tasks": [{"id": "brain-mri-tumor-4class-a", "type": "CLASSIFICATION", "target": "tumour type"}]},
    {"archive": "archive_03", "id": "brain-mri-tumor-4class-b", "title": "Brain MRI tumor 4-class (second variant)", "modality": "MRI", "system": "brain",
     "identity": "glioma/meningioma/notumor/pituitary, 5723 train / 1430 test", "license": "UNVERIFIED", "labels": "CLASS_FOLDER", "official_splits": True,
     "patient_ids": "NONE_AVAILABLE", "tasks": [{"id": "brain-mri-tumor-4class-b", "type": "CLASSIFICATION", "target": "tumour type"}]},
    {"archive": "archive_04", "id": "mri-tumor-detection-small", "title": "MRI tumor detection (113 images)", "modality": "MRI", "system": "brain",
     "identity": "Training/Testing folders without class labels", "license": "UNVERIFIED", "labels": "UNCLEAR", "official_splits": True,
     "patient_ids": "NONE_AVAILABLE", "tasks": [{"id": "mri-tumor-detection-small", "type": "CLASSIFICATION", "target": "unclear", "insufficient": True}]},
    {"archive": "archive_05", "id": "st000001-mr-study", "title": "Single brain MR DICOM study (10 series) with condition list and PDF", "modality": "MRI", "system": "brain",
     "identity": "one DICOM study; PatientName/Institution/Referrer are placeholders, PatientID pseudonymous, birth date present", "license": "UNVERIFIED",
     "labels": "NONE", "official_splits": False, "patient_ids": "PRESENT_BIRTH_DATE", "privacy": "PRIVACY_REVIEW_REQUIRED", "tasks": []},
    {"archive": "archive_07", "id": "lung-cancer-ct", "title": "Lung cancer CT (train/valid/test + test cases)", "modality": "CT", "system": "lungs",
     "identity": "Data/train (1460), valid (142), test (475) and 197 unlabelled test cases", "license": "UNVERIFIED", "labels": "CLASS_FOLDER", "official_splits": True,
     "patient_ids": "NONE_AVAILABLE", "tasks": [{"id": "lung-cancer-ct-classification", "type": "CLASSIFICATION", "target": "publisher classes (not reviewed)"}]},
    {"archive": "archive_08", "id": "liver-ct-volumes", "title": "Liver CT volumes with segmentation masks (LiTS-style)", "modality": "CT", "system": "liver",
     "identity": "131 segmentation volumes but only 51 image volumes present (volume_pt1-pt5)", "license": "UNVERIFIED", "labels": "MASK_VOLUME", "official_splits": False,
     "patient_ids": "NONE_AVAILABLE", "tasks": [{"id": "liver-ct-segmentation", "type": "SEGMENTATION", "target": "liver and lesion masks", "incomplete": True}]},
    {"archive": "archive_09", "id": "dataset-train-test-unlabelled", "title": "DATASET/train, DATASET/test (no class folders)", "modality": "UNKNOWN", "system": None,
     "identity": "999 + 412 images without labels; shares the DATASET folder with archives 10, 14 and 20", "license": "UNVERIFIED", "labels": "NONE",
     "official_splits": True, "patient_ids": "NONE_AVAILABLE", "tasks": []},
    {"archive": "archive_10", "id": "kidney-ct-normal-tumor", "title": "Kidney CT normal vs tumor (subset of the kidney CT set)", "modality": "CT", "system": "kidneys",
     "identity": "DATASET/train|val/Normal|Tumor; 6536 files are byte-identical to archive_12 (kidney CT Normal/Cyst/Tumor/Stone)", "license": "UNVERIFIED",
     "labels": "CLASS_FOLDER", "official_splits": True, "patient_ids": "NONE_AVAILABLE",
     "tasks": [{"id": "kidney-ct-normal-tumor", "type": "CLASSIFICATION", "target": "normal vs tumor"}]},
    {"archive": "archive_12", "id": "kidney-ct-4class", "title": "Kidney CT Normal/Cyst/Tumor/Stone", "modality": "CT", "system": "kidneys",
     "identity": "split_data train/val/test with Normal, Cyst, Tumor, Stone", "license": "UNVERIFIED", "labels": "CLASS_FOLDER", "official_splits": True,
     "patient_ids": "NONE_AVAILABLE", "tasks": [{"id": "kidney-ct-4class", "type": "CLASSIFICATION", "target": "normal / cyst / tumor / stone"}]},
    {"archive": "archive_13", "id": "2d-segmentation-pairs", "title": "2D segmentation image/mask pairs (organ not stated)", "modality": "UNKNOWN", "system": None,
     "identity": "2027 images and 2027 masks", "license": "UNVERIFIED", "labels": "MASK_PAIR", "official_splits": False, "patient_ids": "NONE_AVAILABLE",
     "tasks": [{"id": "2d-segmentation-pairs", "type": "SEGMENTATION", "target": "unknown structure", "needs_review": True}]},
    {"archive": "archive_14", "id": "liver-fibrosis-f0-f4", "title": "Liver fibrosis stage F0-F4 images", "modality": "ULTRASOUND", "system": "liver",
     "identity": "Dataset/Dataset/F0..F4 class folders", "license": "UNVERIFIED", "labels": "CLASS_FOLDER", "official_splits": False, "patient_ids": "NONE_AVAILABLE",
     "tasks": [{"id": "liver-fibrosis-staging", "type": "CLASSIFICATION", "target": "fibrosis stage F0-F4", "needs_review": True}]},
    {"archive": "archive_15", "id": "behsof-nafld", "title": "BEHSOF NAFLD vs non-NAFLD", "modality": "ULTRASOUND", "system": "liver",
     "identity": "BEHSOF/NAFLD (1517) and Non-NAFLD (152)", "license": "UNVERIFIED", "labels": "CLASS_FOLDER", "official_splits": False, "patient_ids": "NONE_AVAILABLE",
     "tasks": [{"id": "behsof-nafld-binary", "type": "CLASSIFICATION", "target": "NAFLD vs non-NAFLD"}]},
    {"archive": "archive_19", "id": "brain-mri-multicondition", "title": "Brain MRI: tumors, Alzheimer stages, MS, normal (merged sources)", "modality": "MRI", "system": "brain",
     "identity": "BT_*, AD_*, MS and Normal class folders combined from several sources", "license": "UNVERIFIED", "labels": "CLASS_FOLDER", "official_splits": True,
     "patient_ids": "NONE_AVAILABLE", "tasks": [{"id": "brain-mri-multicondition", "type": "CLASSIFICATION", "target": "mixed condition taxonomy", "needs_review": True}]},
    {"archive": "archive_20", "id": "brain-tumor-ct-mri", "title": "Brain tumor vs healthy, CT and MRI", "modality": "CT_AND_MRI", "system": "brain",
     "identity": "Brain Tumor MRI images and Brain Tumor CT scan Images, Healthy/Tumor", "license": "UNVERIFIED", "labels": "CLASS_FOLDER", "official_splits": False,
     "patient_ids": "NONE_AVAILABLE", "tasks": [{"id": "brain-tumor-ct-mri-binary", "type": "CLASSIFICATION", "target": "tumor vs healthy"}]},
    {"archive": "archive_21", "id": "cerebrovascular-lesions-ct", "title": "Cerebrovascular lesions (10 classes)", "modality": "CT", "system": "brain",
     "identity": "10 class folders, about 1000 images each", "license": "UNVERIFIED", "labels": "CLASS_FOLDER", "official_splits": False, "patient_ids": "NONE_AVAILABLE",
     "tasks": [{"id": "cerebrovascular-lesions-10class", "type": "CLASSIFICATION", "target": "10 cerebrovascular classes"}]},
    {"archive": "archive_22", "id": "brain-stroke-ct-3class-external", "title": "Brain CT hemorrhage/ischemia/normal with external test", "modality": "CT", "system": "brain",
     "identity": "Train 3x4000, Test 3x1000, External_test 639", "license": "UNVERIFIED", "labels": "CLASS_FOLDER", "official_splits": True, "patient_ids": "NONE_AVAILABLE",
     "tasks": [{"id": "brain-stroke-ct-3class-external", "type": "CLASSIFICATION", "target": "hemorrhage / ischemia / normal"}]},
    # ---- Supplementary batch: archives 23-60, extracted into the workspace root by the user on 2026-10-25.
    {"archive": "archive_25", "id": "kvasir-seg", "title": "Kvasir-SEG (GI polyp segmentation)", "modality": "ENDOSCOPY", "system": "intestines",
     "identity": "1000 polyp images with gastroenterologist-verified binary masks; official train.txt (880) / val.txt (120) lists", "license": "KVASIR_SEG",
     "labels": "MASK_FOLDERS", "official_splits": True, "patient_ids": "NONE_AVAILABLE",
     "notes": ["Images are taken from the Kvasir v2 polyps class; models trained on both may share images."],
     "tasks": [{"id": "kvasir-seg-polyp-segmentation", "type": "SEGMENTATION_MASK_FOLDERS", "target": "binary polyp masks", "class_name": "polyp",
                "images_dir": "Kvasir-SEG/Kvasir-SEG/images/", "masks_dir": "Kvasir-SEG/Kvasir-SEG/masks/", "train_list": "train.txt", "test_list": "val.txt"}]},
    {"archive": "archive_30", "id": "ptb-xl-1.0.1", "title": "PTB-XL 1.0.1 (12-lead ECG)", "modality": "ECG", "system": "heart",
     "identity": "21,837 10-second 12-lead ECGs (100 and 500 Hz WFDB) from 18,885 patients with SCP-ECG statements and 10 stratified folds", "license": "PTBXL",
     "labels": "WFDB_WITH_SCP_STATEMENTS", "official_splits": True, "patient_ids": "PSEUDONYMOUS_PATIENT_ID",
     "tasks": [{"id": "ptbxl-diagnostic-superclass", "type": "ECG_MULTILABEL", "target": "5 diagnostic superclasses (NORM, MI, STTC, CD, HYP)"}]},
    {"archive": "archive_28", "id": "uci-heart-failure-clinical-records", "title": "Heart failure clinical records (UCI)", "modality": "CLINICAL_TABULAR", "system": "heart",
     "identity": "299 patients, 12 clinical features, follow-up time and death event", "license": "UCI_HEART_FAILURE", "labels": "TABULAR_SURVIVAL",
     "official_splits": False, "patient_ids": "ONE_ROW_PER_PATIENT", "survival": {"file": "heart_failure_clinical_records_dataset.csv", "time": "time", "event": "DEATH_EVENT"},
     "tasks": [{"id": "heart-failure-survival", "type": "SURVIVAL", "target": "time to death during follow-up"}]},
    {"archive": "archive_35", "id": "uci-cirrhosis-mayo-pbc", "title": "Cirrhosis patient survival, Mayo Clinic PBC (UCI)", "modality": "CLINICAL_TABULAR", "system": "liver",
     "identity": "418 PBC patients (312 randomized trial + 106 non-randomized), follow-up days and status C/CL/D", "license": "UCI_CIRRHOSIS", "labels": "TABULAR_SURVIVAL",
     "official_splits": True, "patient_ids": "ONE_ROW_PER_PATIENT", "survival": {"file": "cirrhosis.csv", "time": "N_Days", "event": "Status", "event_value": "D"},
     "tasks": [{"id": "pbc-survival", "type": "SURVIVAL", "target": "time to death (transplant censored)"}]},
    {"archive": "archive_23", "id": "acdc-cardiac-mri", "title": "ACDC cardiac cine-MRI (CREATIS)", "modality": "MRI", "system": "heart",
     "identity": "150 patients (100 training, 50 testing), 4D cine volumes with ED/ES ground truth for LV, myocardium and RV", "license": "ACDC",
     "labels": "NIFTI_VOLUMES_WITH_MASKS", "official_splits": True, "patient_ids": "PSEUDONYMOUS_PATIENT_FOLDERS",
     "tasks": [{"id": "acdc-cardiac-segmentation", "type": "SEGMENTATION_VOLUMES", "target": "LV cavity, myocardium, RV cavity at ED and ES",
                "trainer": "python -m ml_training.volumetric train",
                "manifest_builder": "python -m ml_training.volumetric_manifest acdc",
                "dataset_root": "database",
                "pipeline_verification": {
                    "status": "IMPLEMENTED_AND_REAL_DATA_TRAINING_EXECUTED_INTERNAL_HELD_OUT_ONLY", "real_data_training_executed": True,
                    "acdc_manifest_validation": {
                        "dataset_version": "c0fa24d113128f2d33975747fa82c3d13eea27577c08de895346094544afebcd",
                        "discovered_cases": 300, "retained_cases": 298, "retained_patients": 149,
                        "patients_per_split": {"train": 84, "val": 15, "test": 50},
                        "cases_per_split": {"train": 168, "val": 30, "test": 100},
                        "patient_split_overlap": 0, "cross_split_identical_content": 0,
                        "leakage_exclusion": "patient055 (two phase images identical to frozen-test patient118; masks differ)",
                        "observed_label_ids": [0, 1, 2, 3], "geometry_and_affine_checks": "PASSED",
                    },
                    "license_gate": "OWNER_AUTHORIZATION_RECORDED_2026-10-25; explicit published licence terms remain unavailable",
                }}]},
    {"archive": "archive_47", "id": "c-nmc-2019", "title": "C-NMC 2019 leukaemia cell images (TCIA)", "modality": "MICROSCOPY", "system": None,
     "identity": "15,114 segmented cell images, ALL vs normal (hem), subject ID in each file name", "license": "CNMC_TCIA", "labels": "CLASS_FOLDER",
     "official_splits": True, "patient_ids": "SUBJECT_ID_IN_FILENAME",
     "tasks": [{"id": "cnmc-all-vs-normal", "type": "SUBJECT_CLASSIFICATION", "target": "ALL blast vs normal B-lymphoid precursor cell",
                "train_root": "C-NMC_Leukemia/training_data/", "test_dir": "C-NMC_Leukemia/validation_data/C-NMC_test_prelim_phase_data/",
                "test_labels": "C-NMC_Leukemia/validation_data/C-NMC_test_prelim_phase_data_labels.csv", "test_label_values": {"1": "all", "0": "hem"},
                "unlabelled_dir": "C-NMC_Leukemia/testing_data/", "subject_pattern": r"^UID_(H?\d+)_\d+_\d+_(all|hem)\.bmp$", "content_threshold": 10}]},
    {"archive": "archive_58", "id": "bone-fracture-roboflow-v4", "title": "Bone fracture detection v4 (Roboflow)", "modality": "XRAY", "system": "skeletal",
     "identity": "4148 X-ray images with YOLO boxes in 7 classes; the archive holds two identical copies", "license": "BONE_FRACTURE_ROBOFLOW", "labels": "YOLO",
     "official_splits": True, "patient_ids": "NONE_AVAILABLE",
     "tasks": [{"id": "bone-fracture-detection", "type": "DETECTION", "target": "fracture boxes",
                "needs_review": "class set mixes fracture labels with a non-fracture 'humerus' class; task definition needs clinical review"}]},
    {"archive": "archive_60", "id": "mura-v1.1", "title": "MURA v1.1 musculoskeletal radiographs (Stanford AIMI)", "modality": "XRAY", "system": "skeletal",
     "identity": "40,009 upper-extremity radiographs in 14,863 studies with study-level normal/abnormal labels; public valid split", "license": "STANFORD_RUA",
     "labels": "STUDY_LABEL_CSV", "official_splits": True, "patient_ids": "PSEUDONYMOUS_PATIENT_FOLDERS",
     "tasks": [{"id": "mura-study-abnormality", "type": "CLASSIFICATION", "target": "study-level normal vs abnormal"}]},
    {"archive": "archive_56", "id": "echonet-dynamic", "title": "EchoNet-Dynamic echocardiography videos (Stanford AIMI)", "modality": "ECHO", "system": "heart",
     "identity": "10,030 apical-4-chamber videos with EF, ESV/EDV and LV tracings", "license": "STANFORD_RUA", "labels": "VIDEO_WITH_EF", "official_splits": True,
     "patient_ids": "ONE_VIDEO_PER_PATIENT",
     "tasks": [{"id": "echonet-ef-regression", "type": "REGRESSION", "target": "left-ventricular ejection fraction"}]},
    {"archive": "archive_24", "id": "kits19-labels", "title": "KiTS19 kidney tumour segmentations and clinical data (no CT imaging)", "modality": "CT", "system": "kidneys",
     "identity": "210 case folders with segmentation.nii and kits.json clinical records; imaging.nii files are absent", "license": "KITS19", "labels": "MASKS_WITHOUT_IMAGES",
     "official_splits": False, "patient_ids": "PSEUDONYMOUS_CASE_IDS", "tasks": [{"id": "kits19-kidney-tumour-segmentation", "type": "SEGMENTATION_VOLUMES",
                                                                              "target": "kidney and tumour", "pending": "CT_IMAGING_NOT_PRESENT"}]},
    {"archive": "archive_59", "id": "lidc-idri-xml", "title": "LIDC-IDRI radiologist XML annotations (no CT imaging)", "modality": "CT", "system": "lungs",
     "identity": "1319 nodule annotation XML files and TCIA metadata; no CT volumes", "license": "UNVERIFIED", "labels": "ANNOTATIONS_WITHOUT_IMAGES",
     "official_splits": False, "patient_ids": "TCIA_SUBJECT_IDS", "tasks": []},
] + [
    # Catalogued only: no licence verified from an official source (Kaggle-style downloads without a
    # licence file) or no labelled task; never trained until provenance and terms are recorded.
    {"archive": f"archive_{number}", "id": slug, "title": title, "modality": modality, "system": system, "identity": identity, "license": "UNVERIFIED",
     "labels": labels, "official_splits": False, "patient_ids": "NONE_AVAILABLE", "tasks": []}
    for number, slug, title, modality, system, identity, labels in (
        (26, "totalsegmentator-repository", "TotalSegmentator source repository (code and test references)", "CT", None, "upstream tool source; not a dataset", "NONE"),
        (27, "unknown-tfrecords", "Four TFRecord shards (unidentified)", "UNKNOWN", None, "7.9 GB of TFRecords without a README", "UNCLEAR"),
        (29, "heart-csv", "heart.csv (heart-disease table, source not stated)", "CLINICAL_TABULAR", "heart", "single CSV without provenance", "UNCLEAR"),
        (31, "stroke-csv", "Healthcare stroke dataset (Kaggle-style CSV)", "CLINICAL_TABULAR", "brain", "single CSV without provenance", "UNCLEAR"),
        (32, "epileptic-seizure-csv", "Epileptic seizure recognition (EEG features CSV)", "CLINICAL_TABULAR", "brain", "single CSV without provenance", "UNCLEAR"),
        (33, "indian-liver-patient-csv", "Indian liver patient records (CSV)", "CLINICAL_TABULAR", "liver", "single CSV without provenance", "UNCLEAR"),
        (34, "hepatitis-c-csv", "Hepatitis C laboratory data (CSV)", "CLINICAL_TABULAR", "liver", "single CSV without provenance", "UNCLEAR"),
        (36, "kidney-disease-csv", "Chronic kidney disease records (CSV)", "CLINICAL_TABULAR", "kidneys", "single CSV without provenance", "UNCLEAR"),
        (37, "diabetes-prediction-csv", "Diabetes prediction dataset (CSV)", "CLINICAL_TABULAR", None, "single CSV without provenance", "UNCLEAR"),
        (38, "thyroid-csv", "Thyroid disease tables (CSV)", "CLINICAL_TABULAR", None, "two CSVs without provenance", "UNCLEAR"),
        (39, "anemia-csv", "Anaemia table (CSV)", "CLINICAL_TABULAR", None, "single CSV without provenance", "UNCLEAR"),
        (40, "data-csv", "data.csv (content not identified)", "CLINICAL_TABULAR", None, "single CSV without provenance", "UNCLEAR"),
        (41, "pcos-tables", "PCOS tables (CSV, XLSX)", "CLINICAL_TABULAR", None, "two tables without provenance", "UNCLEAR"),
        (42, "fetal-health-csv", "Fetal health (cardiotocography features, CSV)", "CLINICAL_TABULAR", None, "single CSV without provenance", "UNCLEAR"),
        (43, "support2-csv", "SUPPORT2 seriously ill hospitalised adults (CSV)", "CLINICAL_TABULAR", None, "survival table; UCI page defers licensing to the original source, which was not verified", "UNCLEAR"),
        (44, "voc-images-root", "870 JPEG/XML pairs extracted flat into the workspace root (unidentified)", "UNKNOWN", None, "Pascal-VOC-style XML without a README", "UNCLEAR"),
        (45, "roboflow-train-folder", "7052 files added to the shared train/ folder (unidentified Roboflow export)", "UNKNOWN", None, "no data.yaml or README in the archive", "UNCLEAR"),
        (46, "ultrasound-fetus", "Fetal ultrasound image bundle (class semantics unverified)", "ULTRASOUND", None, "fetal ultrasound PNGs and annotation-like PNGs plus a copied fetal-health CSV and an untrusted .pth file that is never loaded; provenance, class semantics and patient grouping are unverified", "MIXED_UNVERIFIED"),
        (48, "lymphoma-cll-fl-mcl", "Malignant lymphoma subtypes CLL/FL/MCL (TIFF)", "MICROSCOPY", None, "no licence file", "CLASS_FOLDER"),
        (49, "otoscopic-images", "Otoscopic images, 5 classes", "OTOSCOPY", None, "no licence file", "CLASS_FOLDER"),
        (50, "mtsamples", "MTSamples transcription samples (CSV)", "DOCUMENT", None, "unannotated clinical-note samples; terms not verified", "NONE"),
        (51, "mtsamples-final", "MTSamples derived table (CSV)", "DOCUMENT", None, "unannotated clinical-note samples; terms not verified", "NONE"),
        (52, "resized-images", "Resized images at 4 resolutions with cleaned_dataset.csv (unidentified)", "UNKNOWN", None, "no README", "UNCLEAR"),
        (53, "nbme-patient-notes", "NBME clinical patient notes (train CSV)", "DOCUMENT", None, "candidate annotated NLP corpus; competition terms not verified", "UNCLEAR"),
        (54, "medquad", "MedQuAD medical question-answer pairs (CSV)", "DOCUMENT", None, "question-answer corpus; terms not verified", "NONE"),
        (55, "dataset-link", "dataset_link.txt only", "UNKNOWN", None, "a link file, no data", "NONE"),
        (57, "thermal-dataset-folder", "16,520 thermal images added to the shared DATASET/ folder", "THERMOGRAPHY", None, "no licence file", "UNCLEAR"),
    )
]


def read_manifest(archive: str) -> list[dict]:
    path = MANIFESTS / f"{archive}.entries.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def overlap_matrix(units: list[dict]) -> dict[str, dict[str, int]]:
    """Exact duplicate files (same size and CRC-32) shared between archives."""
    keys = {unit["archive"]: {(row["size"], row["crc32"]) for row in read_manifest(unit["archive"]) if int(row["size"]) > 0} for unit in units}
    result: dict[str, dict[str, int]] = defaultdict(dict)
    names = sorted(keys)
    for index, first in enumerate(names):
        for second in names[index + 1:]:
            shared = len(keys[first] & keys[second])
            if shared:
                result[first][second] = shared
                result[second][first] = shared
    return {name: dict(values) for name, values in result.items()}


def dhash(path: Path) -> int:
    from PIL import Image

    import numpy as np

    with Image.open(path) as image:
        small = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = np.asarray(small, dtype=np.int16).reshape(-1).tolist()
    value = 0
    for row in range(8):
        for column in range(8):
            value = (value << 1) | (pixels[row * 9 + column] > pixels[row * 9 + column + 1])
    return value


class UnionFind:
    def __init__(self, size: int):
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, first: int, second: int) -> None:
        a, b = self.find(first), self.find(second)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


CONFIRM_CORRELATION = 0.95


ENDOSCOPY_CONTENT_THRESHOLD = 50


class ThumbnailCache:
    """Lazily computed 64x64 thumbnails used to confirm dHash candidates.

    With `dark_threshold` (endoscopy), pixels darker than it - the endoscope frame and
    the on-screen text panel - are zeroed after centring on the image's own content
    mean; otherwise two unrelated Kvasir frames correlate at 0.98 through identical
    borders. Pixels inside only one image's content area then lower the similarity."""

    def __init__(self, paths: list[Path], dark_threshold: int | None = None, excluded: str = "frame and text panel"):
        self.paths = paths
        self.dark_threshold = dark_threshold
        self.excluded = excluded  # what the dark pixels are, for the recorded group rule
        self.cache: dict[int, object] = {}

    def __call__(self, index: int):
        import numpy as np

        if index not in self.cache:
            raw = raw_thumbnail(self.paths[index]).reshape(-1)
            mask = raw >= self.dark_threshold if self.dark_threshold is not None else np.ones_like(raw, dtype=bool)
            if mask.mean() < 0.05:
                mask = np.ones_like(raw, dtype=bool)
            vector = np.where(mask, raw - raw[mask].mean(), 0).astype(np.float32)
            norm = float(np.linalg.norm(vector))
            self.cache[index] = vector / norm if norm else vector
        return self.cache[index]

    def similar(self, first: int, second: int) -> bool:
        return float(self(first) @ self(second)) >= CONFIRM_CORRELATION


def near_duplicate_groups(hashes: list[int], threshold: int, thumbs: ThumbnailCache | None = None, stats: dict | None = None) -> list[int]:
    """Near-duplicate group ids. dHash pairs within `threshold` bits (band index on four
    16-bit segments, pigeonhole) are chained by union-find into candidate pools. With
    `thumbs`, every pair inside a pool is compared by 64x64 normalised correlation and
    only confirmed pairs form groups: raw dHash chains link look-alike images (dark
    borders, overlay boxes) into large mixed-class components that are not duplicates."""
    import numpy as np

    pools = UnionFind(len(hashes))
    bands: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, value in enumerate(hashes):
        for band in range(4):
            bands[(band, (value >> (16 * band)) & 0xFFFF)].append(index)
    for members in bands.values():
        if len(members) < 2 or len(members) > 2000:
            continue
        for position, first in enumerate(members):
            for second in members[position + 1:]:
                if bin(hashes[first] ^ hashes[second]).count("1") <= threshold:
                    pools.union(first, second)
    pool_ids = [pools.find(index) for index in range(len(hashes))]
    if thumbs is None:
        return pool_ids
    members_of: dict[int, list[int]] = defaultdict(list)
    for index, pool in enumerate(pool_ids):
        members_of[pool].append(index)
    finder = UnionFind(len(hashes))
    confirmed_pairs = 0
    for members in members_of.values():
        if len(members) < 2:
            continue
        matrix = np.stack([thumbs(i) for i in members])
        similarity = matrix @ matrix.T
        for a, b in zip(*np.nonzero(np.triu(similarity >= CONFIRM_CORRELATION, k=1))):
            confirmed_pairs += 1
            finder.union(members[a], members[b])
    if stats is not None:
        pool_sizes = Counter(pool_ids)
        stats.update({"dhash_candidate_pools_with_more_than_one_image": sum(1 for size in pool_sizes.values() if size > 1),
                      "largest_dhash_candidate_pool": max(pool_sizes.values()), "pixel_confirmed_pairs": confirmed_pairs,
                      "group_rule": f"pairs within a dHash (<= {threshold} bits) candidate pool with 64x64 normalised correlation >= {CONFIRM_CORRELATION}"
                                    + (f" over content pixels (luminance >= {thumbs.dark_threshold}; {thumbs.excluded} excluded)" if thumbs.dark_threshold is not None else "")})
    return [finder.find(index) for index in range(len(hashes))]


def class_samples(unit: dict) -> list[dict]:
    """Image samples with publisher class-folder labels (and official split names when present)."""
    samples = []
    depth = unit.get("label_root_depth", 2)
    for row in read_manifest(unit["archive"]):
        parts = row["entry"].replace("\\", "/").strip("/").split("/")
        if Path(parts[-1]).suffix.lower() not in IMAGE_SUFFIXES or not row["location"]:
            continue
        label = parts[depth - 1] if len(parts) > depth else None
        if label is None:
            continue
        samples.append({"entry": row["entry"], "path": row["location"], "label": label, "size": row["size"], "crc32": row["crc32"]})
    return samples


def assign_group_splits(samples: list[dict], groups: list[int]) -> None:
    """Stratified (by majority label of each group) split of whole groups."""
    members: dict[int, list[int]] = defaultdict(list)
    for index, group in enumerate(groups):
        members[group].append(index)
    by_label: dict[str, list[int]] = defaultdict(list)
    for group, indices in members.items():
        majority = Counter(samples[i]["label"] for i in indices).most_common(1)[0][0]
        by_label[majority].append(group)
    rng = random.Random(SPLIT_SEED)
    for label in sorted(by_label):
        group_ids = sorted(by_label[label])
        rng.shuffle(group_ids)
        total = sum(len(members[g]) for g in group_ids)
        assigned = {"train": 0, "val": 0}
        for group in group_ids:
            size = len(members[group])
            if assigned["train"] + size <= SPLIT_FRACTIONS["train"] * total or assigned["train"] == 0:
                split = "train"
            elif assigned["val"] + size <= SPLIT_FRACTIONS["val"] * total or assigned["val"] == 0:
                split = "val"
            else:
                split = "test"
            if split in assigned:
                assigned[split] += size
            for index in members[group]:
                samples[index]["split"] = split


def manifest_version(rows: list[dict], fields: list[str]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: item["entry"]):
        digest.update(("\t".join(str(row.get(field, "")) for field in fields) + "\n").encode("utf-8"))
    return digest.hexdigest()


def write_samples(dataset_id: str, rows: list[dict], fields: list[str]) -> tuple[str, str]:
    target = DERIVED / dataset_id / "samples.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in sorted(rows, key=lambda item: item["entry"]):
            writer.writerow({field: row.get(field, "") for field in fields})
    return str(target), manifest_version(rows, fields)


def prepare_classification(unit: dict, task: dict, threshold: int) -> dict:
    samples = class_samples(unit)
    hashes = [dhash(Path(sample["path"])) for sample in samples]
    grouping: dict = {}
    dark = ENDOSCOPY_CONTENT_THRESHOLD if unit["modality"] == "ENDOSCOPY" else None
    groups = near_duplicate_groups(hashes, threshold, ThumbnailCache([Path(s["path"]) for s in samples], dark), grouping)
    for sample, group, value in zip(samples, groups, hashes):
        sample["group_id"] = group
        sample["dhash"] = f"{value:016x}"
    assign_group_splits(samples, groups)
    counts = Counter((sample["split"], sample["label"]) for sample in samples)
    labels = sorted({sample["label"] for sample in samples})
    small = [label for label in labels if sum(counts[(split, label)] for split in SPLIT_FRACTIONS) < task.get("min_per_class", 0)]
    group_sizes = Counter(groups)
    path, version = write_samples(task["id"], samples, ["entry", "path", "label", "split", "group_id", "dhash", "size", "crc32"])
    return {
        "samples": len(samples), "labels": labels, "per_split": {split: sum(counts[(split, label)] for label in labels) for split in SPLIT_FRACTIONS},
        "per_split_per_label": {split: {label: counts[(split, label)] for label in labels} for split in SPLIT_FRACTIONS},
        "near_duplicate_groups_with_more_than_one_image": sum(1 for size in group_sizes.values() if size > 1),
        "images_in_near_duplicate_groups": sum(size for size in group_sizes.values() if size > 1),
        "largest_near_duplicate_group": max(group_sizes.values()), **grouping,
        "near_duplicate_groups_with_conflicting_labels": sum(
            1 for group, size in group_sizes.items() if size > 1 and len({s["label"] for s in samples if s["group_id"] == group}) > 1),
        "split_method": f"group-aware stratified split, seed {SPLIT_SEED}, fractions {SPLIT_FRACTIONS}, dHash threshold {threshold}",
        "minimum_samples_per_class": task.get("min_per_class"),
        "classes_below_minimum": small, "sample_manifest": path, "dataset_version": version,
    }


def manifest_locations(unit: dict) -> dict[str, str]:
    return {row["entry"].replace("\\", "/"): row["location"] for row in read_manifest(unit["archive"])}


def prepare_subject_classification(unit: dict, task: dict, threshold: int) -> dict:
    """Class folders whose file names carry the subject id, plus a separately labelled held-out list
    (C-NMC: the training folds, and the preliminary-phase test images with their label CSV). Whole
    subjects are split into train/validation (stratified by class, seed); the labelled list is the
    frozen test set and must share no subject with them. Near-duplicates crossing splits are audited
    as for publisher splits; the group (bootstrap) unit is the subject."""
    location = manifest_locations(unit)
    pattern = re.compile(task["subject_pattern"], re.IGNORECASE)
    samples = []
    for entry, path in sorted(location.items()):
        if not path or not entry.startswith(task["train_root"]) or Path(entry).suffix.lower() not in IMAGE_SUFFIXES:
            continue
        folder, name = entry.split("/")[-2:]
        match = pattern.match(name)
        if match is None or match.group(2).lower() != folder.lower():
            raise ValueError(f"{entry}: the file name does not carry a subject id matching the class folder")
        samples.append({"entry": entry, "path": path, "label": folder.lower(), "subject_id": match.group(1).upper(), "publisher_split": "train"})
    unlabelled = sum(1 for entry, path in location.items() if path and entry.startswith(task["unlabelled_dir"]))
    with Path(location[task["test_labels"]]).open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            entry, label = task["test_dir"] + row["new_names"], task["test_label_values"][row["labels"]]
            match = pattern.match(row["Patient_ID"])
            if match is None or match.group(2).lower() != label or not location.get(entry):
                raise ValueError(f"{entry}: missing on disk, or the label CSV disagrees with the original file name")
            samples.append({"entry": entry, "path": location[entry], "label": label, "subject_id": match.group(1).upper(), "publisher_split": "test"})
    # Identical cell images occur under different subject ids, so the split unit is a subject
    # cluster: subjects joined by any pixel-confirmed near-duplicate. Single cells sit on a black
    # background, which is excluded from the confirming correlation (as the endoscope frame is);
    # otherwise any two centred cells of similar size correlate highly.
    content, excluded_pixels = task.get("content_threshold"), "black background"
    hashes = [dhash(Path(sample["path"])) for sample in samples]
    duplicates = near_duplicate_groups(hashes, threshold, ThumbnailCache([Path(s["path"]) for s in samples], content, excluded_pixels))
    subject_ids = sorted({sample["subject_id"] for sample in samples})
    position = {subject: index for index, subject in enumerate(subject_ids)}
    clusters = UnionFind(len(subject_ids))
    subjects_of_group: dict[int, set] = defaultdict(set)
    for sample, group in zip(samples, duplicates):
        subjects_of_group[group].add(sample["subject_id"])
    links = sorted({tuple(sorted(pair)) for subjects in subjects_of_group.values() if len(subjects) > 1
                    for pair in combinations(sorted(subjects), 2)})
    for first, second in links:
        clusters.union(position[first], position[second])
    cluster_of = {subject: f"C{clusters.find(position[subject]):03d}" for subject in subject_ids}
    test_clusters = {cluster_of[s["subject_id"]] for s in samples if s["publisher_split"] == "test"}
    # Training subjects that share images with the frozen test set are removed, not moved.
    removed = sorted({s["subject_id"] for s in samples if s["publisher_split"] == "train" and cluster_of[s["subject_id"]] in test_clusters})
    removed_images = sum(1 for s in samples if s["subject_id"] in removed and s["publisher_split"] == "train")
    samples = [s for s in samples if not (s["publisher_split"] == "train" and s["subject_id"] in removed)]
    images = Counter(cluster_of[s["subject_id"]] for s in samples if s["publisher_split"] == "train")
    classes_of: dict[str, set] = defaultdict(set)
    for sample in samples:
        if sample["publisher_split"] == "train":
            classes_of[cluster_of[sample["subject_id"]]].add(sample["label"])
    rng, validation = random.Random(SPLIT_SEED), set()
    for label in sorted({sample["label"] for sample in samples}):
        members = sorted(cluster for cluster, labels in classes_of.items() if labels == {label})
        rng.shuffle(members)
        total, assigned = sum(images[cluster] for cluster in members), 0
        for cluster in members:
            if assigned + images[cluster] <= 0.15 * total or assigned == 0:
                validation.add(cluster)
                assigned += images[cluster]
    for sample in samples:
        cluster = cluster_of[sample["subject_id"]]
        sample["subject_cluster"] = cluster
        sample["split"] = "test" if sample["publisher_split"] == "test" else ("val" if cluster in validation else "train")
    subjects_per_split = {split: sorted({s["subject_id"] for s in samples if s["split"] == split}) for split in ("train", "val", "test")}
    shared = {f"{a}-{b}": len(set(subjects_per_split[a]) & set(subjects_per_split[b])) for a, b in (("train", "val"), ("train", "test"), ("val", "test"))}
    leakage = split_leakage(samples, threshold, content, excluded_pixels)  # verification after the cluster split
    for sample in samples:
        sample["duplicate_group"], sample["group_id"] = sample["group_id"], sample["subject_cluster"]
    counts = Counter((sample["split"], sample["label"]) for sample in samples)
    labels = sorted({sample["label"] for sample in samples})
    fields = ["entry", "path", "label", "split", "publisher_split", "subject_id", "subject_cluster", "group_id", "duplicate_group", "dhash", "cross_split_duplicate"]
    path, version = write_samples(task["id"], samples, fields)
    return {
        "samples": len(samples), "labels": labels, "per_split": {split: sum(counts[(split, label)] for label in labels) for split in ("train", "val", "test")},
        "per_split_per_label": {split: {label: counts[(split, label)] for label in labels} for split in ("train", "val", "test")},
        "subjects_per_split": {split: len(subjects) for split, subjects in subjects_per_split.items()},
        "subject_overlap_between_splits": shared, "subject_clusters_with_both_classes": sum(1 for labels_ in classes_of.values() if len(labels_) > 1),
        "subject_pairs_sharing_near_identical_images": [f"{first}-{second}" for first, second in links],
        "training_subjects_removed_for_sharing_images_with_test": removed, "training_images_removed": removed_images,
        "unlabelled_images_excluded": unlabelled,
        "split_method": (f"subject clusters (subject id from the file name; subjects sharing a pixel-confirmed near-duplicate image joined) "
                         f"split train/validation 85/15 per class, seed {SPLIT_SEED}; the publisher's labelled preliminary-phase test images are the "
                         f"frozen test set, and training subjects sharing an image with it are removed; bootstrap unit = subject cluster"),
        **leakage, "group_unit": "subject cluster", "classes_below_minimum": [], "sample_manifest": path, "dataset_version": version,
    }


def prepare_volumes(unit: dict, task: dict, threshold: int) -> dict:
    """Patient-grouped NIfTI volume pairs through ml_training.volumetric_manifest (the builder the
    trainer validates against). Computed in memory: the training manifest is written by the builder's
    own CLI after this audit, so its recorded licence gate reflects the registry written here."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from ml_training import volumetric_manifest

    pairs, discovery = volumetric_manifest.discover_acdc_pairs(ROOT / task["dataset_root"])
    manifest = volumetric_manifest.build_manifest(dataset_id=unit["id"], dataset_root=ROOT / task["dataset_root"], pairs=pairs,
                                                  labels=volumetric_manifest.ACDC_LABELS, discovery=discovery)
    validation = manifest["validation"]
    exclusions = manifest["split_policy"].get("leakage_exclusions") or {}
    return {
        "samples": validation["case_count"], "patient_count": validation["patient_count"], "per_split": validation.get("cases_per_split"),
        "patients_per_split": validation["patients_per_split"], "leakage_exclusions": exclusions,
        "split_method": "publisher test patients frozen; development patients split by patient (seed 20261024); development patients whose "
                        "images duplicate a test patient are excluded",
        "classes_below_minimum": [], "dataset_version": manifest["dataset_version"],
        "sample_manifest": f"written by: {task['manifest_builder']} --dataset-root {task['dataset_root']}",
    }


def prepare_mask_folders(unit: dict, task: dict, threshold: int) -> dict:
    """Image/mask folder pairs with the publisher's two lists. The first list is split group-aware
    into train/validation (85/15); the second is the frozen test set. Near-duplicate groups
    (dHash pools confirmed by pixel correlation) are kept within one split where possible;
    groups that span the publisher lists are flagged on both sides."""
    location = manifest_locations(unit)
    images = {Path(entry).stem: (entry, path) for entry, path in location.items()
              if entry.startswith(task["images_dir"]) and Path(entry).suffix.lower() in IMAGE_SUFFIXES and path}
    masks = {Path(entry).stem: path for entry, path in location.items() if entry.startswith(task["masks_dir"]) and path}
    lists = {key: set(Path(location[task[key]]).read_text(encoding="utf-8").split()) for key in ("train_list", "test_list")}
    samples = []
    for stem in sorted(images):
        publisher = "train" if stem in lists["train_list"] else ("test" if stem in lists["test_list"] else None)
        if publisher is None or stem not in masks:
            continue
        entry, path = images[stem]
        samples.append({"entry": entry, "path": path, "mask_file": masks[stem], "image_id": stem, "publisher_split": publisher,
                        "label": task.get("class_name", "foreground")})
    dark = ENDOSCOPY_CONTENT_THRESHOLD if unit["modality"] == "ENDOSCOPY" else None
    hashes = [dhash(Path(sample["path"])) for sample in samples]
    grouping: dict = {}
    groups = near_duplicate_groups(hashes, threshold, ThumbnailCache([Path(sample["path"]) for sample in samples], dark), grouping)
    for sample, group, value in zip(samples, groups, hashes):
        sample["group_id"], sample["dhash"] = group, f"{value:016x}"
    sizes = Counter(sample["group_id"] for sample in samples if sample["publisher_split"] == "train")
    order = sorted(sizes)
    random.Random(SPLIT_SEED).shuffle(order)
    validation, assigned = set(), 0
    for group in order:
        if assigned + sizes[group] <= 0.15 * sum(sizes.values()):
            validation.add(group)
            assigned += sizes[group]
    for sample in samples:
        sample["split"] = "test" if sample["publisher_split"] == "test" else ("val" if sample["group_id"] in validation else "train")
    splits_of: dict[int, set] = defaultdict(set)
    for sample in samples:
        splits_of[sample["group_id"]].add(sample["split"])
    crossing = {group for group, splits in splits_of.items() if len(splits) > 1}
    for sample in samples:
        sample["cross_split_duplicate"] = int(sample["group_id"] in crossing)
    members: dict[int, list[dict]] = defaultdict(list)
    for sample in samples:
        if sample["group_id"] in crossing:
            members[sample["group_id"]].append(sample)
    pairs_across = sum(1 for group in members.values() for position, first in enumerate(group)
                       for second in group[position + 1:] if first["split"] != second["split"])
    fields = ["entry", "path", "mask_file", "image_id", "split", "publisher_split", "group_id", "dhash", "cross_split_duplicate"]
    path, version = write_samples(task["id"], samples, fields)
    return {
        "samples": len(samples), "per_split": dict(Counter(sample["split"] for sample in samples)),
        "split_method": f"publisher lists: {task['train_list']} split group-aware into train/validation (85/15, seed {SPLIT_SEED}); {task['test_list']} is the frozen test set",
        "near_duplicate_groups_crossing_splits": len(crossing), "images_in_crossing_groups": sum(sample["cross_split_duplicate"] for sample in samples),
        "test_images_with_cross_split_duplicate": sum(1 for sample in samples if sample["cross_split_duplicate"] and sample["split"] == "test"),
        "near_duplicate_candidate_pairs_across_splits": pairs_across, **grouping,
        "confirmation": f"dHash candidates confirmed by 64x64 normalised pixel correlation >= {CONFIRM_CORRELATION}",
        "sample_manifest": path, "dataset_version": version,
    }


def prepare_ptbxl(unit: dict, task: dict, threshold: int) -> dict:
    """Counts, patient disjointness and the dataset version shared with ml_training.ecg."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from ml_training import ptbxl  # numpy-only module; the same version definition as the trainer

    location = manifest_locations(unit)
    dataset_dir = Path(next(path for entry, path in location.items() if entry.endswith("/ptbxl_database.csv"))).parent
    records, statements, excluded = ptbxl.load_metadata(dataset_dir)
    sums = ptbxl.publisher_checksums(dataset_dir)
    missing = [name for name in ptbxl.used_files(records) if not (dataset_dir / name).exists()]
    return {
        "samples": len(records), "per_split": dict(Counter(record["split"] for record in records)),
        "split_method": "publisher strat_fold: 1-8 train, 9 validation, 10 test (patient-disjoint, asserted)",
        "patients": ptbxl.assert_patient_disjoint(records), "excluded": excluded, "diagnostic_statements": len(statements),
        "label_counts": dict(Counter(label for record in records for label in record["labels"])), "files_missing": len(missing),
        "dataset_version": ptbxl.dataset_version(records, sums), "trainer": "python -m ml_training.ecg",
    }


def prepare_survival(unit: dict, task: dict, threshold: int) -> dict:
    """Row and event counts; the split is defined by ml_training.survival (file hash = dataset version)."""
    spec = unit["survival"]
    location = manifest_locations(unit)
    path = Path(next(found for entry, found in location.items() if entry.split("/")[-1] == spec["file"]))
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
    events = sum(1 for row in rows if row[spec["event"]] == spec.get("event_value", "1"))
    return {"samples": len(rows), "per_split": {"all": len(rows)}, "events": events, "censored": len(rows) - events,
            "split_method": "defined in ml_training/survival.py (stratified 70/30, or the publisher's trial/non-trial cohorts for PBC)",
            "dataset_version": hashlib.sha256(path.read_bytes()).hexdigest(), "trainer": "python -m ml_training.survival"}


def coco_subset(unit: dict, subset: str) -> list[dict]:
    rows = read_manifest(unit["archive"])
    location = {row["entry"].replace("\\", "/"): row["location"] for row in rows}
    samples = []
    for split in ("train", "val", "test"):
        annotation_entry = next(entry for entry in location if entry.endswith(f"{subset}/{split}/annotations/{split}.json"))
        data = json.loads(Path(location[annotation_entry]).read_text(encoding="utf-8"))
        base = annotation_entry.rsplit("/annotations/", 1)[0] + "/images/"
        per_image = Counter(annotation["image_id"] for annotation in data["annotations"])
        for image in data["images"]:
            entry = base + image["file_name"]
            samples.append({"entry": entry, "path": location.get(entry, ""), "split": split, "annotation_file": location[annotation_entry],
                            "image_id": image["id"], "annotations": per_image.get(image["id"], 0), "width": image.get("width"), "height": image.get("height")})
    return samples


def yolo_samples(unit: dict) -> list[dict]:
    rows = read_manifest(unit["archive"])
    location = {row["entry"].replace("\\", "/"): row["location"] for row in rows}
    samples = []
    for entry, path in location.items():
        parts = entry.split("/")
        if len(parts) >= 3 and parts[-2] == "images" and Path(entry).suffix.lower() in IMAGE_SUFFIXES:
            label_entry = "/".join(parts[:-2]) + "/labels/" + Path(parts[-1]).stem + ".txt"
            label_path = location.get(label_entry, "")
            boxes = len([line for line in Path(label_path).read_text(encoding="utf-8").splitlines() if line.strip()]) if label_path else 0
            samples.append({"entry": entry, "path": path, "split": {"valid": "val"}.get(parts[-3], parts[-3]), "label_file": label_path, "boxes": boxes})
    return samples


def raw_thumbnail(path: Path):
    import numpy as np
    from PIL import Image

    with Image.open(path) as image:
        return np.asarray(image.convert("L").resize((64, 64), Image.Resampling.BILINEAR), dtype=np.float32)


def mark_crossing_components(samples: list[dict], confirmed_endpoints: set[int]) -> tuple[set[int], set[int]]:
    """Mark every member of a near-duplicate component that spans splits."""
    crossing_groups = {samples[index]["group_id"] for index in confirmed_endpoints}
    crossing_members = {
        index for index, sample in enumerate(samples)
        if sample["group_id"] in crossing_groups
    }
    for index, sample in enumerate(samples):
        sample["cross_split_duplicate"] = int(index in crossing_members)
    return crossing_groups, crossing_members


def split_leakage(samples: list[dict], threshold: int, dark_threshold: int | None = None, excluded: str = "frame and text panel") -> dict:
    """Checks publisher splits for near-duplicates that cross splits. dHash proposes
    candidates; a 64x64 normalised pixel correlation >= 0.95 confirms near-identity,
    which separates true duplicates from look-alike images (common in angiography)."""
    hashes = [dhash(Path(sample["path"])) for sample in samples]
    thumbs = ThumbnailCache([Path(s["path"]) for s in samples], dark_threshold, excluded)
    grouping: dict = {}
    groups = near_duplicate_groups(hashes, threshold, thumbs, grouping)
    for sample, group, value in zip(samples, groups, hashes):
        sample["group_id"], sample["dhash"] = group, f"{value:016x}"
    members: dict[int, list[int]] = defaultdict(list)
    for index, sample in enumerate(samples):
        members[sample["group_id"]].append(index)
    confirmed: set[int] = set()
    candidate_pairs = 0
    for indices in members.values():
        if len({samples[i]["split"] for i in indices}) < 2:
            continue
        for position, first in enumerate(indices):
            for second in indices[position + 1:]:
                if samples[first]["split"] == samples[second]["split"]:
                    continue
                candidate_pairs += 1
                if thumbs.similar(first, second):
                    confirmed.update((first, second))
    # Near-duplicate grouping is transitive.  Once any confirmed pair makes a
    # component span publisher splits, every image in that component is part of
    # the leakage sensitivity set, not only the direct cross-split pair endpoints.
    crossing_groups, crossing_members = mark_crossing_components(samples, confirmed)
    return {
        "near_duplicate_candidate_pairs_across_splits": candidate_pairs,
        "near_duplicate_groups_crossing_splits": len(crossing_groups),
        "images_in_crossing_groups": len(crossing_members),
        "test_images_with_cross_split_duplicate": sum(1 for i in crossing_members if samples[i]["split"] == "test"),
        "crossing_group_rule": "all members of any transitive near-duplicate component spanning publisher splits",
        "largest_near_duplicate_group": max(Counter(groups).values()), **grouping,
        "confirmation": f"dHash candidates confirmed by 64x64 normalised pixel correlation >= {CONFIRM_CORRELATION}",
    }


SESSION_WINDOW_MINUTES = 30


def filename_tick_sessions(samples: list[dict]) -> list[int]:
    """Acquisition sessions for Roboflow exports of DICOM-derived slices.

    The seventh dash-separated field of the source name begins with an 18-digit .NET
    tick timestamp (100 ns since 0001-01-01); slices acquired within the window of
    their neighbour belong to one session, the closest available proxy for one study."""
    ticks = []
    for sample in samples:
        field = sample["entry"].split("/")[-1].split("_png_jpg")[0].split("_jpg")[0].split("-")[6]
        ticks.append(int(field[:18]))
    order = sorted(range(len(samples)), key=lambda index: ticks[index])
    sessions = [0] * len(samples)
    session = 0
    for previous, current in zip(order, order[1:]):
        if ticks[current] - ticks[previous] > SESSION_WINDOW_MINUTES * 60 * 10**7:
            session += 1
        sessions[current] = session
    return sessions


def resplit_by_session(samples: list[dict], threshold: int, dark_threshold: int | None) -> dict:
    """Group-aware re-split that keeps every session and every pixel near-duplicate group in one split."""
    sessions = filename_tick_sessions(samples)
    publisher_crossing = {}
    for sample, session in zip(samples, sessions):
        publisher_crossing.setdefault(session, set()).add(sample["split"])
    test_affected = sum(1 for sample, session in zip(samples, sessions) if sample["split"] == "test" and len(publisher_crossing[session]) > 1)
    hashes = [dhash(Path(sample["path"])) for sample in samples]
    pixel_groups = near_duplicate_groups(hashes, threshold, ThumbnailCache([Path(s["path"]) for s in samples], dark_threshold))
    finder = UnionFind(len(samples))
    first_of: dict[tuple[str, int], int] = {}
    for index, key in enumerate(zip(["session"] * len(samples), sessions)):
        finder.union(first_of.setdefault(key, index), index)
    for index, key in enumerate(zip(["pixel"] * len(samples), pixel_groups)):
        finder.union(first_of.setdefault(key, index), index)
    combined = [finder.find(index) for index in range(len(samples))]
    for sample, session in zip(samples, sessions):
        sample["publisher_split"], sample["session_id"] = sample["split"], session
        sample["label"] = "stone" if int(sample.get("boxes") or 0) > 0 else "no_stone"
    assign_group_splits(samples, combined)
    return {"combined": combined, "audit": {
        "publisher_split_sessions": len(publisher_crossing),
        "publisher_split_sessions_spanning_splits": sum(1 for splits in publisher_crossing.values() if len(splits) > 1),
        "publisher_test_images_sharing_a_session_with_train_or_val": test_affected,
        "session_rule": f"filename .NET tick timestamps within {SESSION_WINDOW_MINUTES} min of the previous slice",
    }}


def prepare_official(unit: dict, task: dict, threshold: int) -> dict:
    dark = ENDOSCOPY_CONTENT_THRESHOLD if unit["modality"] == "ENDOSCOPY" else None
    if unit["labels"] == "COCO":
        samples = coco_subset(unit, task["subset"])
        fields = ["entry", "path", "split", "annotation_file", "image_id", "annotations", "width", "height", "group_id", "dhash", "cross_split_duplicate"]
    else:
        samples = yolo_samples(unit)
        fields = ["entry", "path", "split", "label_file", "boxes", "group_id", "dhash", "cross_split_duplicate"]
    resplit = resplit_by_session(samples, threshold, dark) if unit.get("resplit_by") == "FILENAME_TICKS_SESSION" else None
    leakage = split_leakage(samples, threshold, dark)
    split_method = "publisher splits kept"
    if resplit:
        # Bootstrap and grouping unit: session joined with pixel near-duplicate groups.
        for sample, group in zip(samples, resplit["combined"]):
            sample["group_id"] = group
        fields += ["publisher_split", "session_id"]
        split_method = (f"re-split by acquisition session joined with pixel near-duplicate groups; stratified by stone present, "
                        f"seed {SPLIT_SEED}, fractions {SPLIT_FRACTIONS} (publisher split kept as publisher_split)")
    path, version = write_samples(task["id"], samples, fields)
    counts = Counter(sample["split"] for sample in samples)
    return {"samples": len(samples), "per_split": dict(counts), "split_method": split_method, **leakage,
            **({"publisher_split_audit": resplit["audit"]} if resplit else {}), "sample_manifest": path, "dataset_version": version}


def task_flags(unit: dict, task: dict, overlaps: dict) -> list[str]:
    flags = []
    if unit.get("privacy") == "PRIVACY_REVIEW_REQUIRED":
        flags.append("PRIVACY_BLOCKED")
    license_info = LICENSES[unit["license"]]
    # Terms verified from the official source, or (where none are published) an explicit,
    # recorded authorization by the repository owner; availability alone never suffices.
    if license_info["status"] != "VERIFIED" and license_info.get("authorization_status") != "VERIFIED":
        flags.append("LICENSE_BLOCKED")
    if unit["labels"] in {"NONE"}:
        flags.append("MISSING_LABELS")
    if unit["labels"] in {"MASKS_WITHOUT_IMAGES", "ANNOTATIONS_WITHOUT_IMAGES"}:
        flags.append("MISSING_IMAGES")
    if task.get("needs_review") or unit["labels"] == "UNCLEAR":
        flags.append("NEEDS_REVIEW")
    if task.get("insufficient") or task.get("incomplete"):
        flags.append("INSUFFICIENT_SAMPLES")
    if unit["patient_ids"] in {"NONE_AVAILABLE", "UNKNOWN_DICOM_HEADERS_NOT_REVIEWED"}:
        flags.append("LEAKAGE_RISK")
    if task.get("pending"):
        flags.append(task["pending"])  # an engineering prerequisite that is not met yet
    if not any(flag in flags for flag in ("MISSING_LABELS", "MISSING_IMAGES", "NEEDS_REVIEW")):
        flags.insert(0, "TASK_SUPPORTED_BY_LABELS")
    return flags


def apply_task_readiness(entry: dict, preparation: dict | None = None) -> dict:
    """Apply the validation-readiness policy without blocking exploratory work.

    ``training_eligible`` means that the labels, licence, and privacy gate permit
    model development. It is deliberately distinct from ``validation_ready``:
    a class-count minimum is an evidence-adequacy gate, not a reason to hide the
    data from an explicitly exploratory experiment.
    """
    classes_below_minimum = list((preparation or {}).get("classes_below_minimum") or [])
    if classes_below_minimum and "INSUFFICIENT_SAMPLES" not in entry["flags"]:
        entry["flags"].append("INSUFFICIENT_SAMPLES")

    eligible = bool(entry["training_eligible"])
    insufficient = "INSUFFICIENT_SAMPLES" in entry["flags"]
    entry["validation_ready"] = eligible and not insufficient
    if not eligible:
        entry["readiness"] = "BLOCKED"
    elif insufficient:
        entry["readiness"] = "EXPLORATORY_TRAINING_ONLY"
    else:
        entry["readiness"] = "READY_FOR_TRAINING"
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dhash-threshold", type=int, default=4)
    parser.add_argument("--skip-hashing", action="store_true", help="Skip near-duplicate analysis and sample manifests.")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    imported = {record["archive_id"]: record for record in json.loads((ROOT / "dataset_registry" / "imported.json").read_text(encoding="utf-8"))["archives"]}
    overlaps = overlap_matrix(DATASETS)
    records = []
    for unit in DATASETS:
        archive = imported[unit["archive"]]
        license_info = LICENSES[unit["license"]]
        record = {key: unit[key] for key in ("id", "archive", "title", "modality", "system", "identity", "labels", "official_splits", "patient_ids")}
        record.update({
            "source_archive": archive["source_archive"], "source_sha256": archive["source_sha256"], "files": archive["files"],
            "location": archive["location"], "license": license_info, "privacy": unit.get("privacy", "NO_IDENTIFIERS_FOUND_IN_SAMPLED_METADATA"),
            "exact_duplicate_overlap": overlaps.get(unit["archive"], {}), "notes": unit.get("notes", []), "tasks": [],
        })
        for task in unit["tasks"]:
            flags = task_flags(unit, task, overlaps)
            eligible = (flags[0] == "TASK_SUPPORTED_BY_LABELS" and "LICENSE_BLOCKED" not in flags and "PRIVACY_BLOCKED" not in flags
                        and not task.get("pending"))
            entry = {"task_id": task["id"], "type": task["type"], "target": task["target"], "flags": flags,
                     "training_eligible": eligible}
            for key in ("class_name", "needs_review", "pending", "trainer", "manifest_builder", "blocked_reason"):
                if isinstance(task.get(key), str):
                    entry[key] = task[key]
            if isinstance(task.get("pipeline_verification"), dict):
                entry["pipeline_verification"] = task["pipeline_verification"]
            if task.get("min_per_class") is not None:
                entry["minimum_samples_per_class"] = task["min_per_class"]
            apply_task_readiness(entry)
            data_ok = flags[0] == "TASK_SUPPORTED_BY_LABELS" and "LICENSE_BLOCKED" not in flags and "PRIVACY_BLOCKED" not in flags
            if data_ok and str(task.get("pending", "")).endswith("_NOT_IMPLEMENTED"):
                entry["readiness"] = "NOT_STARTED"  # data and licence permit it; the pipeline does not exist yet
            if eligible and not args.skip_hashing:
                print(f"preparing {task['id']} ...", flush=True)
                prepare = {"CLASSIFICATION": prepare_classification, "SUBJECT_CLASSIFICATION": prepare_subject_classification,
                           "SEGMENTATION_MASK_FOLDERS": prepare_mask_folders, "SEGMENTATION_VOLUMES": prepare_volumes,
                           "ECG_MULTILABEL": prepare_ptbxl, "SURVIVAL": prepare_survival}.get(task["type"], prepare_official)
                entry["preparation"] = prepare(unit, task, args.dhash_threshold)
                apply_task_readiness(entry, entry["preparation"])
                if entry["preparation"].get("test_images_with_cross_split_duplicate"):
                    entry["flags"].append("LEAKAGE_RISK_CROSS_SPLIT_NEAR_DUPLICATES")
            record["tasks"].append(entry)
        records.append(record)
    output = {"generated_at": date.today().isoformat(), "tool": "scripts/dataset_task_audit.py", "split_seed": SPLIT_SEED,
              "dhash_threshold": args.dhash_threshold, "datasets": records}
    (ROOT / "dataset_registry" / "tasks.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    write_matrix(records)
    eligible = [task["task_id"] for record in records for task in record["tasks"] if task["training_eligible"]]
    print(f"datasets: {len(records)}; training-eligible tasks: {eligible}")
    return 0


def write_matrix(records: list[dict]) -> None:
    lines = ["# Data readiness matrix", "",
             "Generated by `scripts/dataset_task_audit.py` from the archive inventories and entry manifests. A task is training-eligible only when "
             "publisher labels support it, the licence was verified from an official source, and no privacy blocker applies. "
             "Patient-level grouping is enforced when stable subject identifiers are present. Several image archives lack such identifiers; near-duplicate grouping reduces, but does not remove, that residual leakage risk.", "",
             "| Dataset | Archive | Modality | Licence | Privacy | Task | Flags | Readiness |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for record in records:
        tasks = record["tasks"] or [{"task_id": "(none)", "flags": ["MISSING_LABELS"] if record["labels"] == "NONE" else [], "readiness": "NOT_APPLICABLE"}]
        for task in tasks:
            license_text = record["license"]["name"] if record["license"]["status"] == "VERIFIED" else record["license"]["status"]
            lines.append(f"| {record['title']} | {record['archive']} | {record['modality']} | {license_text} | {record['privacy']} | {task['task_id']} | {', '.join(task['flags'])} | {task['readiness']} |")
    lines += ["", "## Exact duplicate overlap between archives (same size and CRC-32)", ""]
    for record in records:
        if record["exact_duplicate_overlap"]:
            lines.append(f"- {record['archive']} ({record['id']}): " + ", ".join(f"{other} {count}" for other, count in sorted(record["exact_duplicate_overlap"].items())))
    lines += ["", "## Prepared training sets", ""]
    for record in records:
        for task in record["tasks"]:
            prep = task.get("preparation")
            if prep:
                if "near_duplicate_groups_crossing_splits" in prep:
                    detail = (f"; confirmed near-duplicates crossing splits: {prep['images_in_crossing_groups']} images in {prep['near_duplicate_groups_crossing_splits']} groups "
                              f"({prep['test_images_with_cross_split_duplicate']} in test; {prep.get('near_duplicate_candidate_pairs_across_splits', 0)} candidate pairs checked)")
                elif "near_duplicate_groups_with_more_than_one_image" in prep:
                    detail = f"; near-duplicate groups kept within one split: {prep['near_duplicate_groups_with_more_than_one_image']}"
                elif "patients" in prep:
                    detail = f"; patients per split {prep['patients']['patients_per_split']} (overlap {sum(prep['patients']['patient_overlap'].values())})"
                elif "events" in prep:
                    detail = f"; {prep['events']} events, {prep['censored']} censored"
                else:
                    detail = ""
                if "patient_count" in prep:
                    detail += (f"; {prep['patient_count']} patients, per split {prep['patients_per_split']}; development patients excluded for "
                               f"duplicating test images: {', '.join((prep['leakage_exclusions'] or {}).get('excluded_development_patients') or []) or 'none'}")
                if "subjects_per_split" in prep:
                    detail += (f"; subjects per split {prep['subjects_per_split']} (shared between splits {sum(prep['subject_overlap_between_splits'].values())}); "
                               f"{prep['unlabelled_images_excluded']} unlabelled images excluded")
                lines.append(f"- **{task['task_id']}**: {prep['samples']} samples, splits {prep['per_split']}; {prep['split_method']}; dataset version `{prep['dataset_version'][:16]}`" + detail)
    target = ROOT / "docs" / "data" / "DATA_READINESS_MATRIX.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
