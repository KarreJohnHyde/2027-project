"""Run real, offline learning experiments on the verified BloodMNIST28 splits.

This is a small blood-cell benchmark, not a clinical inference adapter. It does
not train on uploads, alter registered weights or activate models.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from ml_training.learning_strategies import fit_feature_learners, OfflineQPolicy, policy_state, eligibility


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def run(source, output, seed=42):
    expected = next(item for item in json.loads((ROOT / "dataset_registry/public_acquisition.json").read_text())["artifacts"]
                    if item["relative_path"] == "MedMNIST/bloodmnist.npz")
    with source.open("rb") as handle:
        actual = hashlib.file_digest(handle, expected["hash_algorithm"]).hexdigest()
    if actual != expected["hash"]:
        raise ValueError("BloodMNIST publisher checksum mismatch.")
    with np.load(source, allow_pickle=False) as data:
        images = {split: data[f"{split}_images"] for split in ("train", "val", "test")}
        labels = {split: data[f"{split}_labels"].reshape(-1).astype(np.int64) for split in images}
    # Preserve the official test set, removing exact image duplicates from other splits.
    hashes = {key: [hashlib.sha256(image.tobytes()).hexdigest() for image in values] for key, values in images.items()}
    forbidden = set(hashes["test"])
    removed = {}
    for key in ("val", "train"):
        keep = []
        for index, value in enumerate(hashes[key]):
            if value not in forbidden:
                keep.append(index)
                forbidden.add(value)
        removed[key] = len(images[key]) - len(keep)
        images[key], labels[key] = images[key][keep], labels[key][keep]
    x = {key: value.reshape(len(value), -1).astype(np.float32) / 255.0 for key, value in images.items()}
    labeled, _ = train_test_split(np.arange(len(x["train"])), train_size=0.2, random_state=seed, stratify=labels["train"])
    seed_labels = np.full(len(x["train"]), -1, dtype=np.int64)
    seed_labels[labeled] = labels["train"][labeled]
    learners = fit_feature_learners(x["train"], seed_labels, seed=seed)
    encoded = {key: learners["transform"].transform(values) for key, values in x.items() if key != "train"}
    probs = {key: [learners[name].predict_proba(values) for name in ("baseline", "semi_supervised")]
             for key, values in encoded.items()}
    policy = OfflineQPolicy()
    rng = np.random.default_rng(seed)
    # Terminal one-step Q-learning = an offline contextual bandit. Both experts can
    # be scored because public validation labels are known (full-information rewards).
    # Reward +1 correct, -1 incorrect, 0 defer is a benchmark utility, not clinical benefit.
    for _ in range(30):
        for i in rng.permutation(len(x["val"])):
            row = [p[i] for p in probs["val"]]
            mask = eligibility(row)
            for action in np.flatnonzero(mask):
                reward = 0 if action == 2 else (1 if np.argmax(row[action]) == labels["val"][i] else -1)
                policy.update(policy_state(row), int(action), reward, allowed=mask)
    metrics = {}
    predictions = {}
    for index, name in enumerate(("supervised_seed", "semi_supervised")):
        pred = probs["test"][index].argmax(1)
        predictions[name] = pred
        metrics[name] = {"accuracy": float(accuracy_score(labels["test"], pred)),
                         "balanced_accuracy": float(balanced_accuracy_score(labels["test"], pred)),
                         "macro_f1": float(f1_score(labels["test"], pred, average="macro"))}
    actions = np.array([policy.select(policy_state(row), eligibility(row)) for row in zip(*probs["test"])])
    accepted = actions != 2
    chosen = np.array([predictions["supervised_seed"][i] if a == 0 else predictions["semi_supervised"][i] if a == 1 else -1 for i, a in enumerate(actions)])
    scores = learners["novelty"].score_samples(encoded["test"])
    metrics["offline_workflow_policy"] = {"coverage": float(accepted.mean()), "deferred": int((~accepted).sum()),
        "selective_accuracy": float(accuracy_score(labels["test"][accepted], chosen[accepted])) if accepted.any() else None,
        "mean_benchmark_reward": float(np.where(accepted, np.where(chosen == labels["test"], 1, -1), 0).mean()),
        "actions": {name: int((actions == i).sum()) for i, name in enumerate(("supervised_seed", "semi_supervised", "defer"))}}
    metrics["unsupervised_novelty"] = {"score_median": float(np.median(scores)), "score_min": float(scores.min()),
                                        "notice": "Distribution novelty; no disease interpretation or ground-truth anomaly claim."}
    output.mkdir(parents=True, exist_ok=True)
    # Local trusted research artifacts only. No joblib/unpickle endpoint is exposed.
    import joblib
    joblib.dump({"learners": learners, "policy": policy}, output / "research_learners.joblib", compress=3)
    np.savez_compressed(output / "test_predictions.npz", labels=labels["test"], **predictions,
                        policy_actions=actions, policy_predictions=chosen, novelty_scores=scores)
    report = {"schema_version": 1, "status": "RESEARCH_BENCHMARK_ONLY", "dataset": "BloodMNIST28", "seed": seed,
              "source_sha256": digest(source), "source_publisher_checksum": actual,
              "scope": "Eight blood-cell categories at 28x28; not arbitrary microscopy or disease diagnosis.",
              "splits": {key: len(value) for key, value in x.items()}, "removed_exact_duplicates": removed,
              "patient_independence": "Unknown: benchmark has no patient identifiers; image-hash separation only.",
              "preprocessing_fit": "training only", "label_fraction": 0.2,
              **{key: learners[key] for key in ("labeled_rows", "unlabeled_rows", "pseudo_labeled_rows")},
              "policy_training": "Public validation only; terminal masked Q-learning; 30 seeded passes; +1/-1/0 benchmark utility",
              "test_usage": "Frozen one-time evaluation; no fitting or threshold selection on test.", "metrics": metrics,
              "activation": "DISABLED: no serving adapter, external validation or clinical approval",
              "artifacts": {name: {"sha256": digest(output / name), "bytes": (output / name).stat().st_size}
                            for name in ("research_learners.joblib", "test_predictions.npz")}}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("C:/MedTwin_Datasets/MedMNIST/bloodmnist.npz"))
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/research_learning/bloodmnist-v1")
    args = parser.parse_args()
    print(json.dumps(run(args.source, args.output), indent=2))
