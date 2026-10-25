"""Research survival models on public time-to-event cohorts (Cox proportional hazards).

Two cohorts, both CC BY 4.0 on the UCI Machine Learning Repository:

heart-failure  299 heart-failure patients (Chicco & Jurman 2020, data of Ahmad et al.
               2017); death during follow-up (4-285 days). Stratified 70/30 split
               (seed 20261024); the L2 penalty is chosen by 5-fold cross-validated
               C-index inside the training part. The follow-up `time` column is the
               survival time only, never a predictor.
pbc            Mayo Clinic primary biliary cirrhosis cohort (Dickson et al. 1989). As in
               the original Mayo model, the 312 randomized-trial patients are the
               development cohort and the 106 non-randomized patients the hold-out
               cohort. Covariates are the Mayo model's: age, log bilirubin, log albumin,
               log prothrombin time, oedema. Death is the event; liver transplantation
               (status CL) is censored at transplant, a competing risk noted as a
               limitation.

Cox model: Breslow partial likelihood with an L2 penalty on standardised covariates,
fitted by Newton-Raphson; Breslow baseline cumulative hazard. Held-out evaluation, run
once: Harrell's C, IPCW time-dependent Brier scores (Graf et al. 1999; censoring
distribution from the training cohort), integrated Brier score against a Kaplan-Meier
reference, and grouped calibration at each horizon. Bootstrap CIs resample patients.

  python -m ml_training.survival --cohort heart-failure
  python -m ml_training.survival --cohort pbc
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from ml_training.common import MODEL_CARDS, REPORTS, ROOT, Run, bootstrap_ci, checkpoint_ref, register_model, relative, set_seed

SEED = 20261024

COHORTS = {
    "heart-failure": {
        "file": "heart_failure_clinical_records_dataset.csv", "model_id": "heart_failure_survival_cox", "anatomy": "heart",
        "display_name": "Heart-failure mortality Cox model (research; UCI heart failure clinical records)",
        "dataset": "Heart failure clinical records (UCI id 519)", "dataset_id": "uci-heart-failure-clinical-records",
        "license": {"status": "VERIFIED", "name": "CC BY 4.0", "source": "https://archive.ics.uci.edu/dataset/519/heart+failure+clinical+records",
                    "verified_on": "2026-10-25",
                    "citation": "Chicco D, Jurman G. Machine learning can predict survival of patients with heart failure from serum creatinine and ejection fraction alone. BMC Med Inform Decis Mak 20, 16 (2020)."},
        "horizons_days": [90, 180], "time_unit": "days",
        "population": "299 heart-failure patients with LVEF <= 45% (NYHA III-IV), Faisalabad Institute of Cardiology and Allied Hospital, Pakistan, April-December 2015 (Ahmad et al., PLoS ONE 2017).",
    },
    "pbc": {
        "file": "cirrhosis.csv", "model_id": "pbc_mayo_survival_cox", "anatomy": "liver",
        "display_name": "Primary biliary cirrhosis mortality Cox model, Mayo covariates (research)",
        "dataset": "Cirrhosis patient survival, Mayo Clinic PBC (UCI id 878)", "dataset_id": "uci-cirrhosis-mayo-pbc",
        "license": {"status": "VERIFIED", "name": "CC BY 4.0", "source": "https://archive.ics.uci.edu/dataset/878/cirrhosis+patient+survival+prediction+dataset-1",
                    "verified_on": "2026-10-25",
                    "citation": "Dickson ER, Grambsch PM, Fleming TR, Fisher LD, Langworthy A. Prognosis in primary biliary cirrhosis: model for decision making. Hepatology 10(1):1-7 (1989)."},
        "horizons_days": [365, 1095, 1826], "time_unit": "days",
        "population": "Mayo Clinic primary biliary cirrhosis patients 1974-1984: 312 randomized trial patients (development) and 106 consenting non-randomized patients (hold-out).",
    },
}


def load_cohort(name: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str], np.ndarray, dict]:
    """Returns X, time, event, feature names, split labels and a preparation summary."""
    path = ROOT / COHORTS[name]["file"]
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
    if name == "heart-failure":
        features = ["age", "anaemia", "log_creatinine_phosphokinase", "diabetes", "ejection_fraction", "high_blood_pressure",
                    "log_platelets", "log_serum_creatinine", "serum_sodium", "sex", "smoking"]
        X = np.array([[float(r["age"]), float(r["anaemia"]), math.log(float(r["creatinine_phosphokinase"])), float(r["diabetes"]),
                       float(r["ejection_fraction"]), float(r["high_blood_pressure"]), math.log(float(r["platelets"])),
                       math.log(float(r["serum_creatinine"])), float(r["serum_sodium"]), float(r["sex"]), float(r["smoking"])] for r in rows])
        time = np.array([float(r["time"]) for r in rows])
        event = np.array([int(r["DEATH_EVENT"]) for r in rows])
        rng = np.random.default_rng(SEED)
        split = np.empty(len(rows), dtype=object)
        for value in (0, 1):  # stratified by event
            index = rng.permutation(np.flatnonzero(event == value))
            cut = int(round(0.7 * len(index)))
            split[index[:cut]], split[index[cut:]] = "train", "test"
        summary = {"rows": len(rows), "excluded": 0, "split_method": "stratified by death event, 70/30, seed 20261024"}
        return X, time, event, features, split, summary
    features = ["age_years", "log_bilirubin", "log_albumin", "log_prothrombin", "edema"]
    edema = {"N": 0.0, "S": 0.5, "Y": 1.0}
    kept, X, time, event, split = [], [], [], [], []
    for r in rows:
        if r["Prothrombin"] in ("", "NA") or r["Bilirubin"] in ("", "NA") or r["Albumin"] in ("", "NA"):
            continue
        kept.append(r)
        X.append([float(r["Age"]) / 365.25, math.log(float(r["Bilirubin"])), math.log(float(r["Albumin"])),
                  math.log(float(r["Prothrombin"])), edema[r["Edema"]]])
        time.append(float(r["N_Days"]))
        event.append(1 if r["Status"] == "D" else 0)
        split.append("test" if r["Drug"] in ("", "NA") else "train")
    summary = {"rows": len(rows), "excluded": len(rows) - len(kept), "excluded_reason": "missing bilirubin, albumin or prothrombin",
               "transplants_censored": sum(1 for r in kept if r["Status"] == "CL"),
               "split_method": "development = randomized trial patients (Drug recorded); hold-out = non-randomized patients (as in Dickson et al. 1989)"}
    return np.array(X), np.array(time), np.array(event), features, np.array(split, dtype=object), summary


def cox_fit(X: np.ndarray, time: np.ndarray, event: np.ndarray, penalty: float, iterations: int = 50) -> np.ndarray:
    """Penalised Breslow partial likelihood, Newton-Raphson on standardised X."""
    order = np.argsort(-time, kind="mergesort")  # descending time: cumulative sums give risk sets
    X, time, event = X[order], time[order], event[order]
    beta = np.zeros(X.shape[1])
    for _ in range(iterations):
        eta = X @ beta
        w = np.exp(eta - eta.max())
        s0 = np.cumsum(w)
        s1 = np.cumsum(w[:, None] * X, axis=0)
        s2 = np.cumsum(w[:, None, None] * X[:, :, None] * X[:, None, :], axis=0)
        # Ties (Breslow): all subjects with the same time share the risk set ending at the last of them.
        last = np.r_[np.flatnonzero(np.diff(time) != 0), len(time) - 1]
        position = np.searchsorted(last, np.arange(len(time)))
        s0, s1, s2 = s0[last][position], s1[last][position], s2[last][position]
        d = event.astype(bool)
        mean = s1[d] / s0[d, None]
        gradient = (X[d] - mean).sum(0) - penalty * beta
        hessian = -(s2[d] / s0[d, None, None] - mean[:, :, None] * mean[:, None, :]).sum(0) - penalty * np.eye(X.shape[1])
        step = np.linalg.solve(hessian, gradient)
        beta = beta - step
        if np.abs(step).max() < 1e-9:
            break
    return beta


def breslow(X: np.ndarray, time: np.ndarray, event: np.ndarray, beta: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Baseline cumulative hazard at each distinct event time."""
    risk = np.exp(X @ beta)
    times = np.unique(time[event == 1])
    hazard = np.array([event[time == t].sum() / risk[time >= t].sum() for t in times])
    return times, np.cumsum(hazard)


def survival_at(times: np.ndarray, cumhaz: np.ndarray, linear: np.ndarray, horizon: float) -> np.ndarray:
    index = np.searchsorted(times, horizon, side="right") - 1
    h0 = cumhaz[index] if index >= 0 else 0.0
    return np.exp(-h0 * np.exp(linear))


def harrell_c(time: np.ndarray, event: np.ndarray, risk: np.ndarray) -> float | None:
    earlier = (time[:, None] < time[None, :]) & (event[:, None] == 1)
    comparable = earlier.sum()
    if comparable == 0:
        return None
    concordant = (earlier & (risk[:, None] > risk[None, :])).sum()
    tied = (earlier & (risk[:, None] == risk[None, :])).sum()
    return float((concordant + 0.5 * tied) / comparable)


def kaplan_meier(time: np.ndarray, indicator: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    times = np.unique(time[indicator == 1])
    surv, value = [], 1.0
    for t in times:
        at_risk = (time >= t).sum()
        value *= 1 - (indicator[time == t].sum() / at_risk)
        surv.append(value)
    return times, np.array(surv)


def step(times: np.ndarray, values: np.ndarray, t: float, left: bool = False) -> float:
    """Right-continuous step function (left limit with left=True); 1 before the first jump."""
    index = np.searchsorted(times, t, side="left" if left else "right") - 1
    return float(values[index]) if index >= 0 else 1.0


def ipcw_brier(time: np.ndarray, event: np.ndarray, survival: np.ndarray, horizon: float, censor_km) -> float:
    """Graf et al. (1999) Brier score at one horizon with inverse-probability-of-censoring weights."""
    c_times, c_surv = censor_km
    total = 0.0
    for t, e, s in zip(time, event, survival):
        if t <= horizon and e == 1:
            g = step(c_times, c_surv, t, left=True)
            total += (s ** 2) / g if g > 0 else 0.0
        elif t > horizon:
            g = step(c_times, c_surv, horizon)
            total += ((1 - s) ** 2) / g if g > 0 else 0.0
    return total / len(time)


def km_risk(time: np.ndarray, event: np.ndarray, horizon: float) -> float:
    times, surv = kaplan_meier(time, event)
    return 1 - step(times, surv, horizon)


def evaluate(time, event, linear, model, horizons, censor_km, reference_km, grid) -> dict:
    risk = linear
    c_index = harrell_c(time, event, risk)
    brier = {}
    for horizon in horizons:
        predicted = survival_at(model["times"], model["cumhaz"], linear, horizon)
        reference = np.full(len(time), step(reference_km[0], reference_km[1], horizon))
        brier[str(horizon)] = {"model": ipcw_brier(time, event, predicted, horizon, censor_km),
                               "kaplan_meier_reference": ipcw_brier(time, event, reference, horizon, censor_km)}
    ibs_model = float(np.trapezoid([ipcw_brier(time, event, survival_at(model["times"], model["cumhaz"], linear, t), t, censor_km) for t in grid], grid) / (grid[-1] - grid[0]))
    ibs_reference = float(np.trapezoid([ipcw_brier(time, event, np.full(len(time), step(reference_km[0], reference_km[1], t)), t, censor_km) for t in grid], grid) / (grid[-1] - grid[0]))
    return {"harrell_c": c_index, "brier": brier, "integrated_brier_model": ibs_model, "integrated_brier_kaplan_meier": ibs_reference,
            "integrated_brier_skill": 1 - ibs_model / ibs_reference if ibs_reference > 0 else None}


def calibration(time, event, linear, model, horizon: float, groups: int = 3) -> list[dict]:
    predicted_risk = 1 - survival_at(model["times"], model["cumhaz"], linear, horizon)
    edges = np.quantile(predicted_risk, np.linspace(0, 1, groups + 1))
    table = []
    for g in range(groups):
        mask = (predicted_risk >= edges[g]) & ((predicted_risk <= edges[g + 1]) if g == groups - 1 else (predicted_risk < edges[g + 1]))
        if mask.sum() == 0:
            continue
        table.append({"group": g + 1, "n": int(mask.sum()), "events": int(event[mask].sum()), "mean_predicted_risk": float(predicted_risk[mask].mean()),
                      "observed_risk_kaplan_meier": km_risk(time[mask], event[mask], horizon)})
    return table


def choose_penalty(X, time, event, candidates=(0.0, 0.01, 0.1, 1.0, 10.0), folds: int = 5) -> tuple[float, dict]:
    rng = np.random.default_rng(SEED)
    fold = np.empty(len(time), dtype=int)
    for value in (0, 1):
        index = rng.permutation(np.flatnonzero(event == value))
        fold[index] = np.arange(len(index)) % folds
    scores = {}
    for penalty in candidates:
        values = []
        for k in range(folds):
            train, held = fold != k, fold == k
            beta = cox_fit(X[train], time[train], event[train], penalty)
            values.append(harrell_c(time[held], event[held], X[held] @ beta))
        scores[str(penalty)] = float(np.mean([v for v in values if v is not None]))
    best = max(candidates, key=lambda p: (scores[str(p)], p))  # ties favour the larger (more conservative) penalty
    return best, scores


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", choices=sorted(COHORTS), required=True)
    args = parser.parse_args()
    set_seed(SEED)
    spec = COHORTS[args.cohort]
    run = Run(spec["model_id"], f"{args.cohort}-survival", vars(args))
    X_raw, time, event, features, split, summary = load_cohort(args.cohort)
    train, test = split == "train", split == "test"
    mean, std = X_raw[train].mean(0), X_raw[train].std(0) + 1e-12
    X = (X_raw - mean) / std
    if args.cohort == "pbc":
        penalty, cv_scores = 0.0, {"note": "unpenalised: the five-covariate Mayo specification is fixed in advance"}
    else:
        penalty, cv_scores = choose_penalty(X[train], time[train], event[train])
    beta = cox_fit(X[train], time[train], event[train], penalty)
    times, cumhaz = breslow(X[train], time[train], event[train], beta)
    model = {"times": times, "cumhaz": cumhaz}
    censor_km = kaplan_meier(time[train], 1 - event[train])  # censoring distribution, development cohort
    reference_km = kaplan_meier(time[train], event[train])
    test_event_times = np.sort(time[test & (event == 1)])
    grid = np.linspace(np.quantile(test_event_times, 0.1), np.quantile(test_event_times, 0.9), 50)
    linear = X[test] @ beta
    held_out = evaluate(time[test], event[test], linear, model, spec["horizons_days"], censor_km, reference_km, grid)
    calibrations = {str(h): calibration(time[test], event[test], linear, model, h) for h in spec["horizons_days"]}
    t_test, e_test = time[test], event[test]
    intervals = {"harrell_c": bootstrap_ci(lambda idx: harrell_c(t_test[idx], e_test[idx], linear[idx]), len(t_test), None)}
    intervals["harrell_c"]["unit"] = "patient"
    hazard_ratios = {name: {"hr_per_sd": float(math.exp(b)), "coefficient_standardised": float(b), "sd": float(s)} for name, b, s in zip(features, beta, std)}

    dataset_version = hashlib.sha256((ROOT / spec["file"]).read_bytes()).hexdigest()
    checkpoint_path, checkpoint_sha = run.save_checkpoint({
        "kind": "cox_proportional_hazards", "features": features, "feature_mean": mean.tolist(), "feature_sd": std.tolist(), "coefficients": beta.tolist(),
        "baseline_times": times.tolist(), "baseline_cumulative_hazard": cumhaz.tolist(), "penalty": penalty, "dataset_version": dataset_version,
        "time_unit": spec["time_unit"], "transforms": {"log_*": "natural log of the raw value"},
    })
    predictions_path = run.directory / "predictions_test.csv"
    with predictions_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time", "event", "linear_predictor", *[f"survival_{h}d" for h in spec["horizons_days"]]])
        for t, e, lp in zip(t_test, e_test, linear):
            writer.writerow([t, e, f"{lp:.6f}", *[f"{float(survival_at(times, cumhaz, np.array([lp]), h)[0]):.6f}" for h in spec["horizons_days"]]])

    counts = {"train": int(train.sum()), "test": int(test.sum())}
    events = {"train": int(event[train].sum()), "test": int(event[test].sum())}
    limitations = [
        f"Population: {spec['population']} Predictions do not transfer to other populations without external validation.",
        "Cox proportional-hazards assumption not formally tested; small held-out cohort, so confidence intervals are wide.",
        "Research-only survival estimates; not validated for clinical decision-making.",
    ]
    if args.cohort == "pbc":
        limitations.insert(1, "Liver transplantation is a competing risk censored at transplant; mortality risk may be underestimated.")
    report = {
        "model_id": spec["model_id"], "run_id": run.run_id, "task_id": f"{args.cohort}-survival", "task_type": "survival",
        "dataset": spec["dataset"], "dataset_id": spec["dataset_id"], "dataset_version": dataset_version, "dataset_license": spec["license"],
        "split_method": summary["split_method"], "split_counts": counts, "events": events, "preparation": summary, "features": features,
        "penalty": {"l2": penalty, "selection": "5-fold cross-validated C-index within the development cohort" if args.cohort != "pbc" else "fixed", "cv_scores": cv_scores},
        "hazard_ratios": hazard_ratios, "test_n": counts["test"], "horizons_days": spec["horizons_days"],
        "metrics": held_out, "confidence_intervals_95": intervals, "calibration": calibrations,
        "integrated_brier_grid_days": [float(grid[0]), float(grid[-1])],
        "checkpoint": {"path": checkpoint_ref(checkpoint_path), "sha256": checkpoint_sha}, "held_out_predictions": checkpoint_ref(predictions_path),
        "training_seconds": run.elapsed_seconds, "config": vars(args),
        "reporting_context": {"dataset": spec["dataset"], "dataset_version": dataset_version[:16], "split": "held-out", "checkpoint": f"sha256:{checkpoint_sha}"},
        "limitations": limitations,
    }
    report_path = REPORTS / f"{spec['model_id']}.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    ci = intervals["harrell_c"]
    lines = [
        f"# Model card: {spec['display_name']}", "",
        f"- **Model id:** `{spec['model_id']}` (registry status `READY_UNVALIDATED`; research-only)",
        f"- **Data:** {spec['dataset']} ({spec['license']['name']}; {spec['license']['source']}). Dataset version `{dataset_version[:16]}`.",
        f"- **Population:** {spec['population']}",
        f"- **Split:** {summary['split_method']}: {counts['train']} development ({events['train']} deaths), {counts['test']} held out ({events['test']} deaths).",
        f"- **Model:** Cox proportional hazards (Breslow), covariates {', '.join(features)}; L2 penalty {penalty}.",
        f"- **Checkpoint:** `{checkpoint_ref(checkpoint_path)}`, SHA-256 `{checkpoint_sha}`.", "",
        "## Held-out results (evaluated once)", "",
        f"- Harrell's C {held_out['harrell_c']:.3f}" + (f" (95% CI {ci['low']:.3f}-{ci['high']:.3f})" if ci.get('status') == 'COMPUTED' else "") + ".",
        f"- Integrated Brier score {held_out['integrated_brier_model']:.3f} vs {held_out['integrated_brier_kaplan_meier']:.3f} for the Kaplan-Meier reference (skill {held_out['integrated_brier_skill']:.3f}).",
        *[f"- Brier at {h} days: {held_out['brier'][str(h)]['model']:.3f} (Kaplan-Meier reference {held_out['brier'][str(h)]['kaplan_meier_reference']:.3f})." for h in spec["horizons_days"]], "",
        "## Limitations", "", *[f"- {item}" for item in limitations], "", f"Full report: `{relative(report_path)}`.",
    ]
    (MODEL_CARDS / f"{spec['model_id']}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    register_model({
        "model_id": spec["model_id"], "display_name": spec["display_name"], "domain": "prognosis", "task": "survival_prediction", "anatomy": spec["anatomy"],
        "framework": "numpy (ml_training/survival.py)", "adapter": "ml_training.survival", "source_repository": "medtwin", "dependency_environment": ".venv",
        "weights_path": checkpoint_ref(checkpoint_path), "device": "cpu", "supported_inputs": [f"tabular covariates: {', '.join(features)}"],
        "supported_modalities": ["CLINICAL_TABULAR"], "inference_input": "tabular_survival", "supported_classes": ["time_to_death"],
        "status": "READY_UNVALIDATED", "validated": False, "processor_only": False, "research_inference": True, "limitations": limitations,
        # Discrimination alone is not enough: without held-out Brier skill over the Kaplan-Meier
        # reference the absolute risks are no better than the population average.
        "validation_readiness": {
            "validation_ready": False,
            "readiness": "INTERNAL_HELD_OUT_ONLY" if (held_out["integrated_brier_skill"] or 0) > 0 else "NO_HELD_OUT_BRIER_SKILL_OVER_KAPLAN_MEIER",
            "run_scope": "RESEARCH" if (held_out["integrated_brier_skill"] or 0) > 0 else "EXPLORATORY_ONLY",
            "evidence": {"harrell_c": held_out["harrell_c"], "integrated_brier_skill": held_out["integrated_brier_skill"]},
        },
        "artifact_bundle": {
            "dataset_version": dataset_version, "dataset_license": spec["license"]["name"], "split_manifest_path": relative(report_path),
            "task_definition": "Time to all-cause death; " + ("transplant censored" if args.cohort == "pbc" else "censored at end of follow-up"),
            "label_definition": {"event": "death", "time_unit": spec["time_unit"]}, "preprocessing_version": f"{args.cohort}-cox-v1",
            "checkpoint_path": checkpoint_ref(checkpoint_path), "checkpoint_sha256": checkpoint_sha, "calibration": {"method": "Breslow baseline hazard"},
            "decision_thresholds": None, "abstention_thresholds": None, "held_out_predictions_path": checkpoint_ref(predictions_path),
            "evaluation_report_path": relative(report_path), "model_card_path": relative(MODEL_CARDS / f"{spec['model_id']}.md"),
        },
    })
    run.log(event="done", harrell_c=held_out["harrell_c"], ibs=held_out["integrated_brier_model"], ibs_km=held_out["integrated_brier_kaplan_meier"], checkpoint_sha256=checkpoint_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
