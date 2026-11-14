"""Research classifiers on public clinical tables from the UCI Machine Learning Repository (CC BY 4.0).

Each cohort is downloaded by scripts/acquire_approved_public_datasets.py (owner approval 2026-11-14; a receipt with the
SHA-256 and the licence page is kept next to each archive), registered in dataset_registry/tasks.json with that
evidence, and passes the shared training-rights gate (ml_training.volumetric_manifest.enforce_training_license) before
any row is read for training.

Method, identical for every cohort:
- split 70/15/15 into development, validation and test, stratified by outcome; rows of one person (a subject or
  patient number, where the source has one) never cross splits (sklearn StratifiedGroupKFold, seed 20261024);
- preprocessing (median/most-frequent imputation, scaling, one-hot encoding) is fitted on the development part only;
- candidates: L2 logistic regression and histogram gradient boosting, a small fixed grid each; the model with the best
  validation AUROC is kept (logistic regression on ties);
- Platt calibration and the operating threshold (Youden's J) are fitted on the validation part only;
- the test part is scored once: AUROC and AUPRC with group-bootstrap 95% intervals, sensitivity and specificity at the
  validation threshold, Brier score against the prevalence-only baseline, and expected calibration error (10 bins).

These are research models of the published cohorts; they are not validated for any other population or clinical use.

  python -m ml_training.tabular --cohort heart-disease        (or --all)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ml_training.common import MODEL_CARDS, REPORTS, ROOT, Run, bootstrap_ci, checkpoint_ref, register_model, relative, sha256_file
from ml_training.volumetric_manifest import enforce_training_license

SEED = 20261024
UCI = Path("C:/MedTwin_Datasets/UCI_Tables")
LICENCE = "CC BY 4.0"
CITATION_NOTE = "UCI Machine Learning Repository dataset; cite the dataset's UCI page and original authors."


def _archive(name: str) -> Path:
    path = UCI / name
    if not path.exists() or not path.with_name(path.name + ".receipt.json").exists():
        raise SystemExit(f"{path} or its download receipt is missing; run scripts/acquire_approved_public_datasets.py first")
    return path


def _member(archive: Path, member: str) -> str:
    with zipfile.ZipFile(archive) as handle:
        return handle.read(member).decode("latin-1")


def _frame(text: str, columns: list[str], sep: str = ",") -> pd.DataFrame:
    return pd.read_csv(io.StringIO(text), header=None, names=columns, sep=sep, na_values=["?", ""], skipinitialspace=True)


def load_heart() -> tuple[pd.DataFrame, pd.Series, pd.Series, str]:
    columns = ["age", "sex", "cp", "trestbps", "chol", "fbs", "restecg", "thalach", "exang", "oldpeak", "slope", "ca", "thal", "num"]
    archive = _archive("uci-45-heart.zip")
    frames = []
    for site in ("cleveland", "hungarian", "switzerland", "va"):
        frame = _frame(_member(archive, f"processed.{site}.data"), columns)
        frame["site"] = site
        frames.append(frame)
    data = pd.concat(frames, ignore_index=True)
    y = (data.pop("num") > 0).astype(int)
    data.pop("site")  # sites differ in case mix; the site is never a predictor
    return data, y, pd.Series(np.arange(len(data)), name="row"), "angiographic coronary disease (>50% narrowing; 'num' > 0)"


def load_ckd() -> tuple[pd.DataFrame, pd.Series, pd.Series, str]:
    archive = _archive("uci-336-chronic.zip")
    target = UCI / "extracted" / "ckd"
    arff = next(target.rglob("chronic_kidney_disease_full.arff"), None) if target.exists() else None
    if arff is None:
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as handle:
            handle.extract("Chronic_Kidney_Disease.rar", target)
        # Windows' bsdtar (libarchive) reads RAR archives.
        subprocess.run(["tar", "-xf", str(target / "Chronic_Kidney_Disease.rar"), "-C", str(target)], check=True)
        arff = next(target.rglob("chronic_kidney_disease_full.arff"))
    names, rows, data_started = [], [], False
    for line in arff.read_text(encoding="latin-1").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("%"):
            continue
        if stripped.lower().startswith("@attribute"):
            names.append(stripped.split()[1].strip("'"))
        elif stripped.lower() == "@data":
            data_started = True
        elif data_started:
            values = [value.strip().strip("\t") for value in stripped.rstrip(",").split(",")]
            values = [value for value in values if value != ""] if len(values) > len(names) else values
            if len(values) == len(names):
                rows.append(values)
    data = pd.DataFrame(rows, columns=names).replace("?", np.nan)
    for column in ("age", "bp", "sg", "al", "su", "bgr", "bu", "sc", "sod", "pot", "hemo", "pcv", "wbcc", "rbcc"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    y = (data.pop("class").str.strip() == "ckd").astype(int)
    return data, y, pd.Series(np.arange(len(data)), name="row"), "chronic kidney disease (the source's 'ckd' class)"


def load_diabetes() -> tuple[pd.DataFrame, pd.Series, pd.Series, str]:
    data = pd.read_csv(io.StringIO(_member(_archive("uci-296-diabetes.zip"), "diabetic_data.csv")), na_values=["?"])
    # Encounters ending in death or hospice cannot be readmitted; they are excluded, as in the original study.
    data = data[~data["discharge_disposition_id"].isin([11, 13, 14, 19, 20, 21])].reset_index(drop=True)
    groups = data["patient_nbr"].astype(str)
    y = (data["readmitted"] == "<30").astype(int)
    keep = ["race", "gender", "age", "admission_type_id", "discharge_disposition_id", "admission_source_id", "time_in_hospital",
            "num_lab_procedures", "num_procedures", "num_medications", "number_outpatient", "number_emergency", "number_inpatient",
            "number_diagnoses", "max_glu_serum", "A1Cresult", "insulin", "metformin", "change", "diabetesMed"]
    features = data[keep].copy()
    for column in ("admission_type_id", "discharge_disposition_id", "admission_source_id"):
        features[column] = features[column].astype(str)
    return features, y, groups, "readmission within 30 days of discharge (diabetic inpatient encounters, 130 US hospitals)"


def load_breast() -> tuple[pd.DataFrame, pd.Series, pd.Series, str]:
    measures = ["radius", "texture", "perimeter", "area", "smoothness", "compactness", "concavity", "concave_points", "symmetry", "fractal_dimension"]
    columns = ["id", "diagnosis"] + [f"{stat}_{measure}" for stat in ("mean", "se", "worst") for measure in measures]
    data = _frame(_member(_archive("uci-17-breast.zip"), "wdbc.data"), columns)
    groups = data.pop("id").astype(str)
    y = (data.pop("diagnosis") == "M").astype(int)
    return data, y, groups, "malignant (vs benign) breast mass from fine-needle aspirate image features"


def load_thyroid() -> tuple[pd.DataFrame, pd.Series, pd.Series, str]:
    columns = ["class", "age", "sex", "on_thyroxine", "query_on_thyroxine", "on_antithyroid_medication", "thyroid_surgery", "query_hypothyroid",
               "query_hyperthyroid", "pregnant", "sick", "tumor", "lithium", "goitre", "TSH_measured", "TSH", "T3_measured", "T3",
               "TT4_measured", "TT4", "T4U_measured", "T4U", "FTI_measured", "FTI", "TBG_measured", "TBG"]
    data = _frame(_member(_archive("uci-102-thyroid.zip"), "hypothyroid.data"), columns)
    y = (data.pop("class").str.strip() == "hypothyroid").astype(int)
    for column in ("TSH", "T3", "TT4", "T4U", "FTI", "TBG", "age"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.drop(columns=[column for column in data.columns if column.endswith("_measured")])  # recoverable from missingness
    return data, y, pd.Series(np.arange(len(data)), name="row"), "hypothyroidism (Garvan Institute referrals; the source's 'hypothyroid' class)"


def load_liver() -> tuple[pd.DataFrame, pd.Series, pd.Series, str]:
    columns = ["age", "gender", "total_bilirubin", "direct_bilirubin", "alkaline_phosphatase", "alt", "ast", "total_protein", "albumin", "ag_ratio", "selector"]
    data = _frame(_member(_archive("uci-225-ilpd.zip"), "Indian Liver Patient Dataset (ILPD).csv"), columns)
    y = (data.pop("selector") == 1).astype(int)
    return data, y, pd.Series(np.arange(len(data)), name="row"), "liver patient (the source's selector = 1) from liver function tests"


def load_hepatitis() -> tuple[pd.DataFrame, pd.Series, pd.Series, str]:
    columns = ["class", "age", "sex", "steroid", "antivirals", "fatigue", "malaise", "anorexia", "liver_big", "liver_firm", "spleen_palpable",
               "spiders", "ascites", "varices", "bilirubin", "alk_phosphate", "sgot", "albumin", "protime", "histology"]
    data = _frame(_member(_archive("uci-46-hepatitis.zip"), "hepatitis.data"), columns)
    y = (data.pop("class") == 1).astype(int)
    return data, y, pd.Series(np.arange(len(data)), name="row"), "death (vs survival) of patients with hepatitis"


def load_parkinsons() -> tuple[pd.DataFrame, pd.Series, pd.Series, str]:
    data = pd.read_csv(io.StringIO(_member(_archive("uci-174-parkinsons.zip"), "parkinsons.data")))
    groups = data.pop("name").str.extract(r"_(S\d+)_")[0]  # several recordings per subject: never across splits
    y = data.pop("status").astype(int)
    return data, y, groups, "Parkinson's disease (vs healthy) from sustained-vowel voice measurements"


def load_cervical() -> tuple[pd.DataFrame, pd.Series, pd.Series, str]:
    data = pd.read_csv(io.StringIO(_member(_archive("uci-383-cervical.zip"), "risk_factors_cervical_cancer.csv")), na_values=["?"])
    y = data.pop("Biopsy").astype(int)
    # Other examination results and diagnosis-history columns are excluded as possible proxies of the label.
    data = data.drop(columns=["Hinselmann", "Schiller", "Citology"] + [column for column in data.columns if column.startswith("Dx")])
    return data, y, pd.Series(np.arange(len(data)), name="row"), "positive cervical biopsy from questionnaire risk factors"


COHORTS = {
    "heart-disease": {"load": load_heart, "uci": 45, "dataset_id": "uci-heart-disease", "model_id": "tabular_heart_disease_uci", "anatomy": "heart",
                      "display_name": "Coronary disease from clinical tests (UCI Heart Disease, 4 sites, research)",
                      "population": "Patients referred for coronary angiography at Cleveland, Budapest, Zurich/Basel and Long Beach VA (1980s)."},
    "chronic-kidney-disease": {"load": load_ckd, "uci": 336, "dataset_id": "uci-chronic-kidney-disease", "model_id": "tabular_ckd_uci", "anatomy": "kidneys",
                               "display_name": "Chronic kidney disease from routine tests (UCI CKD, research)",
                               "population": "400 hospital patients in India (2015), small and with a high disease share."},
    "diabetes-readmission": {"load": load_diabetes, "uci": 296, "dataset_id": "uci-diabetes-130-hospitals", "model_id": "tabular_diabetes_readmission_uci",
                             "anatomy": "endocrine", "display_name": "30-day readmission of diabetic inpatients (UCI Diabetes 130-US hospitals, research)",
                             "population": "Diabetic inpatient encounters in 130 US hospitals, 1999-2008."},
    "breast-cancer": {"load": load_breast, "uci": 17, "dataset_id": "uci-breast-cancer-wisconsin-diagnostic", "model_id": "tabular_breast_fna_uci",
                      "anatomy": "breast", "display_name": "Malignant breast mass from aspirate image features (UCI Wisconsin Diagnostic, research)",
                      "population": "569 breast masses sampled by fine-needle aspiration at the University of Wisconsin (1990s)."},
    "hypothyroidism": {"load": load_thyroid, "uci": 102, "dataset_id": "uci-thyroid-hypothyroid", "model_id": "tabular_hypothyroid_uci", "anatomy": "endocrine",
                       "display_name": "Hypothyroidism from thyroid tests (UCI Thyroid, research)",
                       "population": "Thyroid referrals to the Garvan Institute, Sydney (1980s).",
                       "extra_limitations": ["Near-definitional task: the source label was assigned from these thyroid tests (FTI alone reaches development "
                                             "AUROC 0.984), so the high score reflects re-learning that rule, not independent diagnostic discovery."]},
    "liver-patient": {"load": load_liver, "uci": 225, "dataset_id": "uci-indian-liver-patient", "model_id": "tabular_liver_patient_uci", "anatomy": "liver",
                      "display_name": "Liver patient from liver function tests (UCI ILPD, research)",
                      "population": "583 patients from north-east Andhra Pradesh, India."},
    "hepatitis-mortality": {"load": load_hepatitis, "uci": 46, "dataset_id": "uci-hepatitis", "model_id": "tabular_hepatitis_mortality_uci", "anatomy": "liver",
                            "display_name": "Death among hepatitis patients (UCI Hepatitis, research)",
                            "population": "155 hepatitis patients (1980s); very small, so estimates are uncertain."},
    "parkinsons-voice": {"load": load_parkinsons, "uci": 174, "dataset_id": "uci-parkinsons", "model_id": "tabular_parkinsons_voice_uci", "anatomy": "brain",
                         "display_name": "Parkinson's disease from voice measurements (UCI Parkinsons, research)",
                         "population": "31 people (23 with Parkinson's disease), several recordings each; very few people in the test part."},
    "cervical-biopsy": {"load": load_cervical, "uci": 383, "dataset_id": "uci-cervical-cancer-risk-factors", "model_id": "tabular_cervical_biopsy_uci",
                        "anatomy": "reproductive", "display_name": "Positive cervical biopsy from risk factors (UCI Cervical Cancer, research)",
                        "population": "858 patients at Hospital Universitario de Caracas, Venezuela; few positive biopsies."},
}


# Cohorts whose first evaluation (2026-11-14) showed no Brier skill; they stay EXPLORATORY_ONLY until an independent test.
EXPLORATORY_ON_FIRST_EVALUATION = {"liver-patient", "cervical-biopsy", "parkinsons-voice"}


def register_dataset(name: str, spec: dict) -> None:
    """Upsert the cohort's dataset record with its download receipt as licence evidence (owner authorization 2026-11-14)."""
    archive = next(UCI.glob(f"uci-{spec['uci']}-*.zip"))
    receipt = json.loads(archive.with_name(archive.name + ".receipt.json").read_text(encoding="utf-8"))
    evidence = receipt["licence_evidence"]
    if not evidence.get("marker_found"):
        raise SystemExit(f"{name}: the licence page did not show {LICENCE}; not registering")
    record = {
        "id": spec["dataset_id"], "archive": archive.name, "title": f"UCI {spec['display_name'].split('(UCI ')[-1].rstrip(', research)')}",
        "modality": "CLINICAL_TABULAR", "system": spec["anatomy"], "identity": spec["population"], "labels": "SOURCE_TABLE",
        "official_splits": False, "patient_ids": "SOURCE_GROUPING_WHERE_PRESENT", "source_archive": receipt["source_url"],
        "source_sha256": receipt["sha256"], "files": 1, "location": str(archive).replace("\\", "/"),
        "license": {"status": "VERIFIED", "name": LICENCE, "source": evidence["page"], "verified_on": evidence["retrieved_at"][:10],
                    "evidence": {"page_sha256": evidence["page_sha256"], "marker": evidence["marker"]}, "citation": CITATION_NOTE,
                    "authorization_status": "VERIFIED", "authorization_scope": "NON_COMMERCIAL_RESEARCH_UNDER_RECORDED_TERMS",
                    "authorized_by": "project owner (chat instruction)", "authorized_on": "2026-11-14",
                    "authorization_reason": "Owner approved the download and research training on 2026-11-14; CC BY 4.0 shown on the UCI dataset page."},
        "privacy": "PUBLISHER_DE_IDENTIFIED", "exact_duplicate_overlap": {}, "notes": [],
        "tasks": [{"task_id": name, "type": "TABULAR_CLASSIFICATION", "target": spec["display_name"], "flags": ["TASK_SUPPORTED_BY_LABELS"],
                   "training_eligible": True, "validation_ready": True, "readiness": "READY_FOR_TRAINING"}],
    }
    path = ROOT / "dataset_registry" / "tasks.json"
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw[:4096] else "\n"
    registry = json.loads(raw.decode("utf-8"))
    registry["datasets"] = [item for item in registry["datasets"] if item["id"] != spec["dataset_id"]] + [record]
    path.write_bytes((json.dumps(registry, indent=2, ensure_ascii=False) + "\n").replace("\n", newline).encode("utf-8"))


def merge_duplicate_records(features: pd.DataFrame, y: pd.Series, groups: pd.Series) -> pd.Series:
    """Identical records (every feature and the label) join one group with the person they belong to, so an exact
    duplicate can never sit in two parts of a split (union-find over person groups and record hashes)."""
    keys = pd.util.hash_pandas_object(pd.concat([features, y.rename("__label")], axis=1), index=False).astype(str).to_numpy()
    parent: dict[str, str] = {}

    def find(item: str) -> str:
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for group, key in zip(groups.astype(str).to_numpy(), keys):
        a, b = find("g:" + group), find("k:" + key)
        if a != b:
            parent[b] = a
    return pd.Series([find("g:" + group) for group in groups.astype(str).to_numpy()], index=groups.index, name="group")


def split(y: pd.Series, groups: pd.Series, features: pd.DataFrame | None = None) -> np.ndarray:
    """70/15/15 by outcome, keeping each group (person, and with ``features`` every exact duplicate record) in one part."""
    if features is not None:
        groups = merge_duplicate_records(features, y, groups)
    labels = np.empty(len(y), dtype=object)
    outer = StratifiedGroupKFold(n_splits=7, shuffle=True, random_state=SEED)
    develop, test = next(outer.split(np.zeros(len(y)), y, groups))
    labels[test] = "test"
    inner = StratifiedGroupKFold(n_splits=6, shuffle=True, random_state=SEED)
    train, val = next(inner.split(np.zeros(len(develop)), y.iloc[develop], groups.iloc[develop]))
    labels[develop[train]], labels[develop[val]] = "train", "val"
    return labels


def preprocessor(features: pd.DataFrame) -> ColumnTransformer:
    numeric = [column for column in features.columns if pd.api.types.is_numeric_dtype(features[column])]
    categorical = [column for column in features.columns if column not in numeric]
    return ColumnTransformer([
        ("numeric", Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True)), ("scale", StandardScaler())]), numeric),
        ("categorical", Pipeline([("impute", SimpleImputer(strategy="most_frequent")), ("encode", OneHotEncoder(handle_unknown="ignore", min_frequency=5, sparse_output=False))]), categorical),
    ])


def candidates(features: pd.DataFrame) -> dict[str, Pipeline]:
    models = {f"logistic_C{c}": LogisticRegression(C=c, max_iter=5000) for c in (0.01, 0.1, 1.0, 10.0)}
    models.update({f"gradient_boosting_depth{d}_lr{lr}": HistGradientBoostingClassifier(max_depth=d, learning_rate=lr, max_iter=300, random_state=SEED)
                   for d in (3, None) for lr in (0.05, 0.1)})
    return {name: Pipeline([("prepare", preprocessor(features)), ("model", model)]) for name, model in models.items()}


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    index = np.clip(np.digitize(p, edges[1:-1], right=True), 0, bins - 1)  # p = 0 falls in the first bin, p = 1 in the last
    total = 0.0
    for b in range(bins):
        mask = index == b
        if mask.any():
            total += mask.mean() * abs(p[mask].mean() - y[mask].mean())
    return float(total)


def train_cohort(name: str) -> dict:
    spec = COHORTS[name]
    register_dataset(name, spec)
    gate = enforce_training_license({"dataset_id": spec["dataset_id"]})
    features, y, groups, target = spec["load"]()
    person_grouped = groups.astype(str).nunique() < len(groups)
    duplicates = int(pd.util.hash_pandas_object(pd.concat([features, y], axis=1), index=False).duplicated().sum())
    groups = merge_duplicate_records(features, y, groups.astype(str))
    parts = split(y, groups)
    masks = {part: parts == part for part in ("train", "val", "test")}
    run = Run(spec["model_id"], name, {"cohort": name, "seed": SEED})
    validation = {}
    fitted = {}
    for candidate, pipeline in candidates(features).items():
        pipeline.fit(features[masks["train"]], y[masks["train"]])
        score = roc_auc_score(y[masks["val"]], pipeline.predict_proba(features[masks["val"]])[:, 1])
        validation[candidate], fitted[candidate] = float(score), pipeline
    best = max(validation, key=lambda key: (round(validation[key], 6), key.startswith("logistic")))
    model = fitted[best]
    raw_val = model.predict_proba(features[masks["val"]])[:, 1]
    platt = LogisticRegression(C=1e6, max_iter=5000).fit(_logit(raw_val).reshape(-1, 1), y[masks["val"]])
    calibrate = lambda raw: platt.predict_proba(_logit(raw).reshape(-1, 1))[:, 1]
    val_p = calibrate(raw_val)
    candidates_t = np.unique(val_p)
    youden = [(np.mean(val_p[y[masks["val"]] == 1] >= t) + np.mean(val_p[y[masks["val"]] == 0] < t) - 1, t) for t in candidates_t]
    threshold = float(max(youden)[1])
    y_test = y[masks["test"]].to_numpy()
    p_test = calibrate(model.predict_proba(features[masks["test"]])[:, 1])
    g_test = groups[masks["test"]].to_numpy()
    prevalence = float(y[masks["train"]].mean())
    guess = p_test >= threshold
    metrics = {
        "auroc": float(roc_auc_score(y_test, p_test)), "auprc": float(average_precision_score(y_test, p_test)),
        "sensitivity": float(guess[y_test == 1].mean()), "specificity": float((~guess)[y_test == 0].mean()),
        "brier": float(brier_score_loss(y_test, p_test)), "brier_prevalence_baseline": float(brier_score_loss(y_test, np.full(len(y_test), prevalence))),
        "ece_10_bins": ece(y_test, p_test), "threshold": threshold, "test_positive_share": float(y_test.mean()),
    }
    metrics["brier_skill"] = 1 - metrics["brier"] / metrics["brier_prevalence_baseline"] if metrics["brier_prevalence_baseline"] else None
    unit = "person or duplicate-record group" if person_grouped or duplicates else "row"
    group_array = g_test if unit != "row" else None
    safe = lambda f: (lambda idx: f(y_test[idx], p_test[idx]) if len(set(y_test[idx])) == 2 else None)
    intervals = {"auroc": bootstrap_ci(safe(roc_auc_score), len(y_test), group_array, unit=unit),
                 "auprc": bootstrap_ci(safe(average_precision_score), len(y_test), group_array, unit=unit)}
    checkpoint = run.directory / "model.joblib"
    joblib.dump({"kind": "tabular_binary_classifier", "pipeline": model, "platt": platt, "threshold": threshold, "features": list(features.columns),
                 "target": target, "selected": best}, checkpoint)
    checkpoint_sha = sha256_file(checkpoint)
    predictions = run.directory / "predictions_test.csv"
    with predictions.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["group", "label", "probability_calibrated"])
        # Full precision (repr), so metrics recomputed from this file reproduce the report exactly.
        writer.writerows([[g, int(t), repr(float(p))] for g, t, p in zip(g_test, y_test, p_test)])
    counts = {part: int(mask.sum()) for part, mask in masks.items()}
    positives = {part: int(y[mask].sum()) for part, mask in masks.items()}
    limitations = [
        f"Population: {spec['population']} Results do not transfer to other populations without external evaluation.",
        "Probabilities are Platt-calibrated on the validation part of this cohort only; they are not calibrated for any clinical population.",
        "Small public cohort: confidence intervals are wide." if counts["test"] < 200 else "Single public cohort; no external test set.",
        ("Re-evaluated after test exposure (2026-11-14 duplicate audit): this split's test part overlaps the first run's inspected test part, "
         "so it is not an independent final test."),
        *spec.get("extra_limitations", []),
        "Research-only output; not validated for clinical use.",
    ]
    dataset_version = hashlib.sha256(pd.util.hash_pandas_object(pd.concat([features, y], axis=1), index=False).values.tobytes()).hexdigest()
    report = {
        "model_id": spec["model_id"], "run_id": run.run_id, "task_id": name, "task_type": "tabular_binary_classification", "target": target,
        "dataset": f"UCI {spec['uci']}", "dataset_id": spec["dataset_id"], "dataset_version": dataset_version, "dataset_license": LICENCE,
        "training_rights": {key: gate.get(key) for key in ("authorization_status", "training_purpose", "license_name")},
        "split_method": ("StratifiedGroupKFold 70/15/15 by outcome; one person's rows and every exact duplicate record stay in one part"
                         if unit != "row" else "StratifiedKFold-equivalent 70/15/15 by outcome (one row per person, no duplicate records)"),
        "duplicate_handling": {"exact_duplicate_records": duplicates, "rule": "identical records (all features and label) are grouped into one part"},
        "evaluation_status": "RE_EVALUATED_AFTER_TEST_EXPOSURE_NOT_INDEPENDENT_FINAL_TEST",
        "split_counts": counts, "positives": positives, "features": list(features.columns),
        "model_selection": {"validation_auroc": validation, "selected": best, "rule": "highest validation AUROC; logistic regression on ties"},
        "test_n": counts["test"], "metrics": metrics, "confidence_intervals_95": intervals,
        "calibration": {"method": "Platt scaling on the validation part", "operating_threshold": "Youden's J on the validation part"},
        "checkpoint": {"path": checkpoint_ref(checkpoint), "sha256": checkpoint_sha}, "held_out_predictions": checkpoint_ref(predictions),
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "limitations": limitations,
    }
    report_path = REPORTS / f"{spec['model_id']}.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    ci = intervals["auroc"]
    card = [
        f"# Model card: {spec['display_name']}", "",
        f"- **Model id:** `{spec['model_id']}` (registry status `READY_UNVALIDATED`; research-only)",
        f"- **Target:** {target}.", f"- **Data:** UCI dataset {spec['uci']} ({LICENCE}); {spec['population']}",
        f"- **Split:** {report['split_method']}: {counts['train']} development, {counts['val']} validation, {counts['test']} test "
        f"({positives['test']} positive).", f"- **Selected model:** `{best}` (validation AUROC {validation[best]:.3f}).",
        f"- **Checkpoint:** `{checkpoint_ref(checkpoint)}`, SHA-256 `{checkpoint_sha}`.", "", "## Test results (evaluated once)", "",
        f"- AUROC {metrics['auroc']:.3f}" + (f" (95% CI {ci['low']:.3f}-{ci['high']:.3f})" if ci.get("status") == "COMPUTED" else "") + f"; AUPRC {metrics['auprc']:.3f}.",
        f"- At the validation threshold {threshold:.3f}: sensitivity {metrics['sensitivity']:.3f}, specificity {metrics['specificity']:.3f}.",
        f"- Brier {metrics['brier']:.3f} vs {metrics['brier_prevalence_baseline']:.3f} for the prevalence-only baseline; ECE {metrics['ece_10_bins']:.3f}.", "",
        "## Limitations", "", *[f"- {item}" for item in limitations], "", f"Full report: `{relative(report_path)}`.",
    ]
    (MODEL_CARDS / f"{spec['model_id']}.md").write_text("\n".join(card) + "\n", encoding="utf-8")
    skill = metrics["brier_skill"] or 0
    # A model judged exploratory on its first evaluation is not promoted by a re-split after its test was inspected.
    held_back = name in EXPLORATORY_ON_FIRST_EVALUATION
    if held_back:
        skill = min(skill, 0.0)
        limitations.insert(-1, "Kept exploratory: the first evaluation (2026-11-14) showed no skill over the prevalence baseline; a re-split after "
                               "that test was inspected cannot promote it. An independent final test is required.")
    register_model({
        "model_id": spec["model_id"], "display_name": spec["display_name"], "domain": "clinical_tabular", "task": "tabular_classification",
        "anatomy": spec["anatomy"], "framework": f"scikit-learn ({best.split('_')[0]})", "adapter": "ml_training.tabular", "source_repository": "medtwin",
        "dependency_environment": ".venv", "weights_path": checkpoint_ref(checkpoint), "device": "cpu",
        "supported_inputs": [f"tabular features: {', '.join(features.columns)}"], "supported_modalities": ["CLINICAL_TABULAR"],
        "inference_input": "tabular_classification", "supported_classes": [target], "status": "READY_UNVALIDATED", "validated": False,
        "processor_only": False, "research_inference": True, "limitations": limitations,
        "validation_readiness": {"validation_ready": False, "readiness": "INTERNAL_HELD_OUT_ONLY" if skill > 0 else "NO_HELD_OUT_BRIER_SKILL_OVER_PREVALENCE",
                                 "run_scope": "RESEARCH" if skill > 0 else "EXPLORATORY_ONLY", "evidence": {"auroc": metrics["auroc"], "brier_skill": metrics["brier_skill"]}},
        "artifact_bundle": {
            "dataset_version": dataset_version, "dataset_license": LICENCE, "split_manifest_path": relative(report_path),
            "task_definition": target, "label_definition": {"positive": target}, "preprocessing_version": "tabular-impute-scale-onehot-v1",
            "checkpoint_path": checkpoint_ref(checkpoint), "checkpoint_sha256": checkpoint_sha, "calibration": {"method": "Platt scaling on validation"},
            "decision_thresholds": {"positive": threshold}, "abstention_thresholds": None, "held_out_predictions_path": checkpoint_ref(predictions),
            "evaluation_report_path": relative(report_path), "model_card_path": relative(MODEL_CARDS / f"{spec['model_id']}.md"),
        },
    })
    run.log(event="done", cohort=name, selected=best, auroc=metrics["auroc"], brier_skill=metrics["brier_skill"], checkpoint_sha256=checkpoint_sha)
    return {"cohort": name, "test_n": counts["test"], "auroc": round(metrics["auroc"], 3), "ci": [round(ci.get("low", float("nan")), 3), round(ci.get("high", float("nan")), 3)],
            "sensitivity": round(metrics["sensitivity"], 3), "specificity": round(metrics["specificity"], 3), "brier_skill": round(skill, 3), "selected": best}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cohort", choices=sorted(COHORTS))
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    names = sorted(COHORTS) if args.all else [args.cohort]
    if names == [None]:
        parser.error("choose --cohort or --all")
    for name in names:
        print(json.dumps(train_cohort(name)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
