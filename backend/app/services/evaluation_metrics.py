"""Reproducible evaluation of uploaded held-out predictions.

Metrics are computed only from prediction files supplied by the user; MedTwin
never generates the predictions it evaluates. Confidence intervals use the
percentile bootstrap with a recorded seed. When a group column (for example a
patient identifier) is supplied, groups rather than rows are resampled, so
correlated rows from one patient do not narrow the interval.
"""

from __future__ import annotations

import csv
import io
import math
from typing import Any, Callable, Optional

import numpy as np
from scipy import ndimage, stats

DEFAULT_BOOTSTRAP = 1000
DEFAULT_SEED = 20261024
MIN_ROWS_FOR_CI = 20
MIN_PER_CLASS_FOR_CI = 5


class EvaluationInputError(ValueError):
    """The uploaded predictions cannot support the requested evaluation."""


# Column names used by MedTwin_2_Validation_Kit/evaluate_medtw.py, accepted as aliases
# so a prediction file scored by the kit can be scored here unchanged.
KIT_ALIASES: dict[str, tuple[str, ...]] = {"y_score": ("score",), "group_id": ("patient_id",)}
ACCURACY_TARGET = 0.95


def parse_csv(content: bytes, required: list[str], optional: list[str] = (), aliases: Optional[dict[str, tuple[str, ...]]] = None, keep_empty: bool = False) -> tuple[dict[str, list[str]], int]:
    """Columns by canonical name. Rows missing a required value are dropped and counted,
    unless keep_empty is set (a missing value is then itself the observation)."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise EvaluationInputError("Predictions must be UTF-8 CSV.") from exc
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise EvaluationInputError("CSV has no header row.")
    fields = [name.strip() for name in reader.fieldnames]
    aliases = aliases or {}
    source: dict[str, str] = {}
    for name in [*required, *optional]:
        found = next((candidate for candidate in (name, *aliases.get(name, ())) if candidate in fields), None)
        if found:
            source[name] = found
    missing = [name for name in required if name not in source]
    if missing:
        accepted = "; ".join(f"{name} (or {', '.join(aliases[name])})" if name in aliases else name for name in missing)
        raise EvaluationInputError(f"Missing required column(s): {accepted}. Present: {', '.join(fields)}.")
    columns: dict[str, list[str]] = {name: [] for name in source}
    dropped = 0
    for row in reader:
        clean = {key.strip(): (value or "").strip() for key, value in row.items() if key is not None}
        if not keep_empty and any(clean.get(source[name], "") == "" for name in required):
            dropped += 1
            continue
        for name, column in source.items():
            columns[name].append(clean.get(column, ""))
    return columns, dropped


def _floats(values: list[str], name: str) -> np.ndarray:
    try:
        array = np.array([float(value) for value in values], dtype=float)
    except ValueError as exc:
        raise EvaluationInputError(f"Column '{name}' must be numeric.") from exc
    if not np.all(np.isfinite(array)):
        raise EvaluationInputError(f"Column '{name}' contains non-finite values.")
    return array


def _bootstrap(metric: Callable[[np.ndarray], Optional[float]], n: int, groups: Optional[np.ndarray], rounds: int, seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    if groups is not None:
        unique = np.unique(groups)
        members = {group: np.flatnonzero(groups == group) for group in unique}
    values = []
    skipped = 0
    for _ in range(rounds):
        if groups is not None:
            chosen = rng.choice(unique, size=len(unique), replace=True)
            index = np.concatenate([members[group] for group in chosen])
        else:
            index = rng.integers(0, n, size=n)
        value = metric(index)
        if value is None or not math.isfinite(value):
            skipped += 1
            continue
        values.append(value)
    if len(values) < rounds * 0.9:
        return {"status": "NOT_COMPUTED_TOO_MANY_DEGENERATE_RESAMPLES", "skipped_resamples": skipped}
    low, high = np.percentile(values, [2.5, 97.5])
    return {"status": "COMPUTED", "low": float(low), "high": float(high), "resamples": len(values), "skipped_resamples": skipped}


def _ratio(numerator: float, denominator: float) -> Optional[float]:
    return None if denominator == 0 else numerator / denominator


def _auroc(y: np.ndarray, score: np.ndarray) -> Optional[float]:
    positives = int(y.sum())
    negatives = len(y) - positives
    if positives == 0 or negatives == 0:
        return None
    ranks = stats.rankdata(score)
    return float((ranks[y == 1].sum() - positives * (positives + 1) / 2) / (positives * negatives))


def _average_precision(y: np.ndarray, score: np.ndarray) -> Optional[float]:
    positives = int(y.sum())
    if positives == 0:
        return None
    order = np.argsort(-score, kind="mergesort")
    y_sorted, s_sorted = y[order], score[order]
    distinct = np.r_[np.flatnonzero(np.diff(s_sorted)), len(s_sorted) - 1]
    tp = np.cumsum(y_sorted)[distinct]
    fp = (distinct + 1) - tp
    precision = tp / (tp + fp)
    recall = tp / positives
    previous = np.r_[0.0, recall[:-1]]
    return float(np.sum((recall - previous) * precision))


def _curves(y: np.ndarray, score: np.ndarray, limit: int = 200) -> dict[str, Any]:
    positives = int(y.sum())
    negatives = len(y) - positives
    order = np.argsort(-score, kind="mergesort")
    y_sorted, s_sorted = y[order], score[order]
    distinct = np.r_[np.flatnonzero(np.diff(s_sorted)), len(s_sorted) - 1]
    tp = np.cumsum(y_sorted)[distinct]
    fp = (distinct + 1) - tp
    thresholds = s_sorted[distinct]
    tpr = np.r_[0.0, tp / positives] if positives else np.zeros(len(tp) + 1)
    fpr = np.r_[0.0, fp / negatives] if negatives else np.zeros(len(fp) + 1)
    precision = tp / (tp + fp)
    recall = tp / positives if positives else np.zeros(len(tp))
    step = max(1, len(thresholds) // limit)
    keep = list(range(0, len(thresholds), step)) + [len(thresholds) - 1]
    roc = [{"fpr": float(fpr[0]), "tpr": float(tpr[0]), "threshold": None}] + [
        {"fpr": float(fpr[i + 1]), "tpr": float(tpr[i + 1]), "threshold": float(thresholds[i])} for i in sorted(set(keep))
    ]
    pr = [{"recall": float(recall[i]), "precision": float(precision[i]), "threshold": float(thresholds[i])} for i in sorted(set(keep))]
    return {"roc": roc, "pr": pr}


def _confusion(y: np.ndarray, predicted: np.ndarray) -> dict[str, int]:
    return {
        "tp": int(np.sum((predicted == 1) & (y == 1))),
        "fp": int(np.sum((predicted == 1) & (y == 0))),
        "tn": int(np.sum((predicted == 0) & (y == 0))),
        "fn": int(np.sum((predicted == 0) & (y == 1))),
    }


def _threshold_metrics(confusion: dict[str, int]) -> dict[str, Optional[float]]:
    tp, fp, tn, fn = confusion["tp"], confusion["fp"], confusion["tn"], confusion["fn"]
    n = tp + fp + tn + fn
    sensitivity = _ratio(tp, tp + fn)
    specificity = _ratio(tn, tn + fp)
    denominator = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return {
        "accuracy": _ratio(tp + tn, n),
        "balanced_accuracy": None if sensitivity is None or specificity is None else (sensitivity + specificity) / 2,
        "sensitivity_recall": sensitivity,
        "specificity": specificity,
        "precision_ppv": _ratio(tp, tp + fp),
        "npv": _ratio(tn, tn + fn),
        "f1": _ratio(2 * tp, 2 * tp + fp + fn),
        "mcc": None if denominator == 0 else (tp * tn - fp * fn) / denominator,
    }


def _calibration(y: np.ndarray, probability: np.ndarray, bins: int = 10) -> dict[str, Any]:
    edges = np.linspace(0.0, 1.0, bins + 1)
    rows, ece = [], 0.0
    for index in range(bins):
        upper_inclusive = index == bins - 1
        mask = (probability >= edges[index]) & ((probability <= edges[index + 1]) if upper_inclusive else (probability < edges[index + 1]))
        count = int(mask.sum())
        if count == 0:
            continue
        mean_predicted = float(probability[mask].mean())
        observed = float(y[mask].mean())
        ece += count / len(y) * abs(observed - mean_predicted)
        rows.append({"bin_low": float(edges[index]), "bin_high": float(edges[index + 1]), "count": count, "mean_predicted": mean_predicted, "observed_fraction": observed})
    return {"bins": rows, "expected_calibration_error": ece, "bin_scheme": f"{bins} equal-width bins on [0, 1]"}


def evaluate_classification(content: bytes, threshold: Optional[float] = None, rounds: int = DEFAULT_BOOTSTRAP, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    columns, dropped = parse_csv(content, ["y_true", "y_score"], ["group_id"], aliases=KIT_ALIASES)
    y = _floats(columns["y_true"], "y_true")
    if not set(np.unique(y)).issubset({0.0, 1.0}):
        raise EvaluationInputError("y_true must be binary (0/1). Multi-class evaluation needs y_true and y_pred labels.")
    y = y.astype(int)
    score = _floats(columns["y_score"], "y_score")
    n = len(y)
    if n < 2 or len(np.unique(y)) < 2:
        raise EvaluationInputError("Both classes must be present.")
    probability_scale = bool(np.all((score >= 0) & (score <= 1)))
    cut = threshold if threshold is not None else (0.5 if probability_scale else 0.0)
    predicted = (score >= cut).astype(int)
    confusion = _confusion(y, predicted)
    point = _threshold_metrics(confusion)
    point["auroc"] = _auroc(y, score)
    point["auprc_average_precision"] = _average_precision(y, score)
    point["brier_score"] = float(np.mean((score - y) ** 2)) if probability_scale else None
    groups = np.array(columns["group_id"]) if "group_id" in columns else None

    positives, negatives = int(y.sum()), int(n - y.sum())
    intervals: dict[str, Any] = {}
    if n >= MIN_ROWS_FOR_CI and min(positives, negatives) >= MIN_PER_CLASS_FOR_CI:
        def resampled(name: str):
            def metric(index: np.ndarray) -> Optional[float]:
                yy, ss = y[index], score[index]
                if len(np.unique(yy)) < 2:
                    return None
                if name == "auroc":
                    return _auroc(yy, ss)
                if name == "auprc_average_precision":
                    return _average_precision(yy, ss)
                if name == "brier_score":
                    return float(np.mean((ss - yy) ** 2))
                return _threshold_metrics(_confusion(yy, (ss >= cut).astype(int)))[name]
            return metric
        for index, name in enumerate(("auroc", "auprc_average_precision", "accuracy", "sensitivity_recall", "specificity", "f1", "mcc", "brier_score")):
            if point.get(name) is None:
                continue
            intervals[name] = _bootstrap(resampled(name), n, groups, rounds, seed + index)
    else:
        intervals["status"] = "NOT_COMPUTED_SMALL_SAMPLE"
        intervals["requirement"] = f"n >= {MIN_ROWS_FOR_CI} and at least {MIN_PER_CLASS_FOR_CI} per class"

    # The manuscript's > 95 % objective may be asserted only with an uncertainty interval (Sec. X).
    accuracy_interval = intervals.get("accuracy", {})
    accuracy_target = {
        "objective": f"accuracy > {ACCURACY_TARGET} for this prespecified task (an objective, not an assumed result)",
        "point_estimate_exceeds": point["accuracy"] is not None and point["accuracy"] > ACCURACY_TARGET,
        "ci_lower_bound_exceeds": accuracy_interval["low"] > ACCURACY_TARGET if accuracy_interval.get("status") == "COMPUTED" else None,
    }

    return {
        "task_type": "classification",
        "accuracy_target": accuracy_target,
        "n": n,
        "n_groups": int(len(np.unique(groups))) if groups is not None else None,
        "dropped_rows_missing_values": dropped,
        "prevalence": positives / n,
        "threshold": cut,
        "threshold_source": "REQUEST" if threshold is not None else "DEFAULT_FOR_SCORE_SCALE",
        "score_scale": "PROBABILITY_0_1" if probability_scale else "UNBOUNDED_SCORE",
        "confusion_matrix": confusion,
        "metrics": point,
        "confidence_intervals_95": intervals,
        "curves": _curves(y, score),
        "calibration": _calibration(y, score) if probability_scale else {"status": "NOT_APPLICABLE_SCORES_NOT_PROBABILITIES"},
        "bootstrap": {"method": "percentile", "resamples": rounds, "seed": seed, "unit": "group_id" if groups is not None else "row"},
        "assumptions": [
            "Rows are held-out predictions not used for model fitting or threshold selection.",
            "Bootstrap intervals assume the evaluated rows (or groups) are representative and independent.",
            "Calibration bins are descriptive; the expected calibration error depends on the binning scheme.",
        ],
    }


def evaluate_multiclass(content: bytes) -> dict[str, Any]:
    columns, dropped = parse_csv(content, ["y_true", "y_pred"])
    truth, predicted = columns["y_true"], columns["y_pred"]
    labels = sorted(set(truth) | set(predicted))
    index = {label: position for position, label in enumerate(labels)}
    matrix = np.zeros((len(labels), len(labels)), dtype=int)
    for true_label, predicted_label in zip(truth, predicted):
        matrix[index[true_label], index[predicted_label]] += 1
    per_class = []
    for label in labels:
        k = index[label]
        tp = matrix[k, k]
        fp = matrix[:, k].sum() - tp
        fn = matrix[k, :].sum() - tp
        per_class.append({"label": label, "support": int(matrix[k, :].sum()), "precision": _ratio(tp, tp + fp), "recall": _ratio(tp, tp + fn), "f1": _ratio(2 * tp, 2 * tp + fp + fn)})
    defined = [row["f1"] for row in per_class if row["f1"] is not None]
    return {
        "task_type": "multiclass",
        "n": int(matrix.sum()),
        "dropped_rows_missing_values": dropped,
        "labels": labels,
        "confusion_matrix": matrix.tolist(),
        "metrics": {"accuracy": float(np.trace(matrix) / matrix.sum()) if matrix.sum() else None, "macro_f1": float(np.mean(defined)) if defined else None},
        "per_class": per_class,
    }


def evaluate_regression(content: bytes, alpha: Optional[float] = None, rounds: int = DEFAULT_BOOTSTRAP, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    columns, dropped = parse_csv(content, ["y_true", "y_pred"], ["lower", "upper", "group_id"])
    y = _floats(columns["y_true"], "y_true")
    prediction = _floats(columns["y_pred"], "y_pred")
    n = len(y)
    if n < 2:
        raise EvaluationInputError("At least two rows are required.")
    error = prediction - y
    total = float(np.sum((y - y.mean()) ** 2))
    metrics: dict[str, Any] = {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error ** 2))),
        "median_absolute_error": float(np.median(np.abs(error))),
        "mean_error_bias": float(np.mean(error)),
        "r_squared": None if total == 0 else 1 - float(np.sum(error ** 2)) / total,
    }
    intervals_block: dict[str, Any] = {"status": "NOT_SUPPLIED"}
    if "lower" in columns and "upper" in columns and all(columns["lower"]) and all(columns["upper"]):
        lower = _floats(columns["lower"], "lower")
        upper = _floats(columns["upper"], "upper")
        if np.any(lower > upper):
            raise EvaluationInputError("Every lower bound must be <= its upper bound.")
        inside = (y >= lower) & (y <= upper)
        intervals_block = {"status": "COMPUTED", "coverage": float(inside.mean()), "mean_width": float(np.mean(upper - lower))}
        if alpha is not None:
            if not 0 < alpha < 1:
                raise EvaluationInputError("alpha must be in (0, 1).")
            score = (upper - lower) + (2 / alpha) * (lower - y) * (y < lower) + (2 / alpha) * (y - upper) * (y > upper)
            intervals_block.update({"nominal_coverage": 1 - alpha, "mean_interval_score": float(np.mean(score)), "interval_score_reference": "Gneiting & Raftery (2007), JASA 102:359-378."})
    groups = np.array(columns["group_id"]) if "group_id" in columns else None
    confidence: dict[str, Any] = {}
    if n >= MIN_ROWS_FOR_CI:
        confidence["mae"] = _bootstrap(lambda index: float(np.mean(np.abs(error[index]))), n, groups, rounds, seed)
        confidence["rmse"] = _bootstrap(lambda index: float(np.sqrt(np.mean(error[index] ** 2))), n, groups, rounds, seed + 1)
    else:
        confidence = {"status": "NOT_COMPUTED_SMALL_SAMPLE", "requirement": f"n >= {MIN_ROWS_FOR_CI}"}
    return {
        "task_type": "regression",
        "n": n,
        "n_groups": int(len(np.unique(groups))) if groups is not None else None,
        "dropped_rows_missing_values": dropped,
        "metrics": metrics,
        "prediction_intervals": intervals_block,
        "confidence_intervals_95": confidence,
        "bootstrap": {"method": "percentile", "resamples": rounds, "seed": seed, "unit": "group_id" if groups is not None else "row"},
        "residuals_sample": [{"y_true": float(a), "y_pred": float(b)} for a, b in list(zip(y, prediction))[:500]],
    }


def evaluate_survival(content: bytes, rounds: int = DEFAULT_BOOTSTRAP, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    columns, dropped = parse_csv(content, ["time", "event", "risk_score"], ["group_id"])
    time = _floats(columns["time"], "time")
    event = _floats(columns["event"], "event")
    risk = _floats(columns["risk_score"], "risk_score")
    if not set(np.unique(event)).issubset({0.0, 1.0}):
        raise EvaluationInputError("event must be 0 (censored) or 1 (event).")
    if len(time) > 5000:
        raise EvaluationInputError("Harrell's C here is limited to 5,000 rows.")

    def harrell(index: np.ndarray) -> Optional[float]:
        t, e, r = time[index], event[index], risk[index]
        earlier = (t[:, None] < t[None, :]) & (e[:, None] == 1)
        comparable = earlier.sum()
        if comparable == 0:
            return None
        concordant = (earlier & (r[:, None] > r[None, :])).sum()
        tied = (earlier & (r[:, None] == r[None, :])).sum()
        return float((concordant + 0.5 * tied) / comparable)

    n = len(time)
    all_rows = np.arange(n)
    c_index = harrell(all_rows)
    groups = np.array(columns["group_id"]) if "group_id" in columns else None
    return {
        "task_type": "survival",
        "n": n,
        "events": int(event.sum()),
        "dropped_rows_missing_values": dropped,
        "metrics": {"harrell_c_index": c_index},
        "confidence_intervals_95": {"harrell_c_index": _bootstrap(harrell, n, groups, min(rounds, 500), seed)} if n >= MIN_ROWS_FOR_CI and event.sum() >= MIN_PER_CLASS_FOR_CI else {"status": "NOT_COMPUTED_SMALL_SAMPLE"},
        "assumptions": ["Higher risk_score means earlier expected event.", "Censoring is independent of the risk score.", "Time-dependent discrimination and Brier scores need horizon-specific predictions and are not computed here."],
    }


def _load_mask(content: bytes, name: str = "mask") -> np.ndarray:
    """A 2D binary mask (0/1 or 0/255) from PNG-like images or .npy; anything else is rejected
    rather than thresholded, so probability maps cannot pass as masks."""
    from PIL import Image

    try:
        if content[:6] == b"\x93NUMPY":
            array = np.load(io.BytesIO(content), allow_pickle=False)
        else:
            with Image.open(io.BytesIO(content)) as image:
                array = np.asarray(image.convert("L") if image.mode not in ("L", "1", "I", "I;16") else image)
    except Exception as exc:
        raise EvaluationInputError(f"{name} could not be decoded: {exc}") from exc
    if array.ndim != 2:
        raise EvaluationInputError(f"{name} must be a 2D mask; got shape {list(array.shape)}.")
    if not np.isin(np.unique(array), [0, 1, 255]).all():
        raise EvaluationInputError(f"{name} must be binary (0/1 or 0/255); save masks losslessly without anti-aliasing.")
    return array > 0


EMPTY_MASK_CONVENTION = "Both masks empty: Dice = IoU = 1; exactly one empty: Dice = IoU = 0 (MedTwin 2 validation kit convention)."


def _overlap(truth: np.ndarray, predicted: np.ndarray) -> tuple[float, float]:
    intersection = int((truth & predicted).sum())
    total = int(truth.sum()) + int(predicted.sum())
    union = int((truth | predicted).sum())
    return (2 * intersection / total if total else 1.0), (intersection / union if union else 1.0)


def _surface_distances(truth: np.ndarray, predicted: np.ndarray, spacing: tuple[float, float]) -> Optional[dict[str, float]]:
    if not truth.any() or not predicted.any():
        return None
    sampling = (spacing[1], spacing[0])
    surface_a, surface_b = _surface(truth), _surface(predicted)
    to_b = ndimage.distance_transform_edt(~surface_b, sampling=sampling)[surface_a]
    to_a = ndimage.distance_transform_edt(~surface_a, sampling=sampling)[surface_b]
    return {
        "hausdorff": float(max(to_b.max(), to_a.max())),
        "hausdorff_95": float(max(np.percentile(to_b, 95), np.percentile(to_a, 95))),
        "average_symmetric_surface_distance": float((to_b.sum() + to_a.sum()) / (len(to_b) + len(to_a))),
    }


def _surface(mask: np.ndarray) -> np.ndarray:
    return mask & ~ndimage.binary_erosion(mask, border_value=0)


def evaluate_segmentation(reference: bytes, prediction: bytes, spacing: tuple[float, float] = (1.0, 1.0), unit: str = "px") -> dict[str, Any]:
    truth = _load_mask(reference, "Reference mask")
    predicted = _load_mask(prediction, "Predicted mask")
    if truth.shape != predicted.shape:
        raise EvaluationInputError(f"Mask shapes differ: {truth.shape} vs {predicted.shape}.")
    a, b = int(truth.sum()), int(predicted.sum())
    dice, iou = _overlap(truth, predicted)
    metrics: dict[str, Any] = {
        "reference_pixels": a,
        "predicted_pixels": b,
        "dice": dice,
        "iou": iou,
        "volumetric_similarity": 1.0 if a + b == 0 else 1 - abs(a - b) / (a + b),
    }
    distances = _surface_distances(truth, predicted, spacing)
    if distances is None:
        metrics.update({"hausdorff": None, "hausdorff_95": None, "average_symmetric_surface_distance": None, "surface_distance_status": "UNDEFINED_EMPTY_MASK"})
    else:
        metrics.update({**distances, "surface_distance_status": "COMPUTED"})
    return {
        "task_type": "segmentation",
        "n": 1,
        "mask_shape": list(truth.shape),
        "spacing": {"x": spacing[0], "y": spacing[1], "unit": unit},
        "metrics": metrics,
        "empty_mask_convention": EMPTY_MASK_CONVENTION,
        "assumptions": ["Masks must be binary 0/1 or 0/255.", "Distances use the stated pixel spacing; 'px' means spacing was not provided."],
    }


MAX_ARCHIVE_PAIRS = 5000
MAX_ARCHIVE_UNCOMPRESSED = 512 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200


def evaluate_segmentation_batch(archive: bytes, spacing: tuple[float, float] = (1.0, 1.0), unit: str = "px", rounds: int = DEFAULT_BOOTSTRAP, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    """A ZIP holding manifest.csv (patient_id,reference_mask,predicted_mask) and the masks it names,
    the layout of the validation kit's segmentation CSV."""
    import zipfile

    try:
        bundle = zipfile.ZipFile(io.BytesIO(archive))
    except zipfile.BadZipFile as exc:
        raise EvaluationInputError("Upload a ZIP archive containing manifest.csv and the masks it lists.") from exc
    members = {info.filename.replace("\\", "/").removeprefix("./"): info for info in bundle.infolist() if not info.is_dir()}
    if sum(info.file_size for info in members.values()) > MAX_ARCHIVE_UNCOMPRESSED:
        raise EvaluationInputError("Archive expands beyond 512 MB.")
    if any(info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO for info in members.values()):
        raise EvaluationInputError("Archive contains an implausibly compressed member and was not expanded.")
    manifest_name = next((name for name in members if name.rsplit("/", 1)[-1] == "manifest.csv"), None)
    if manifest_name is None:
        raise EvaluationInputError("Archive has no manifest.csv.")
    columns, dropped = parse_csv(bundle.read(members[manifest_name]), ["patient_id", "reference_mask", "predicted_mask"])
    n = len(columns["patient_id"])
    if n == 0:
        raise EvaluationInputError("manifest.csv lists no mask pairs.")
    if n > MAX_ARCHIVE_PAIRS:
        raise EvaluationInputError(f"At most {MAX_ARCHIVE_PAIRS} mask pairs per archive.")
    base = manifest_name.rsplit("/", 1)[0] + "/" if "/" in manifest_name else ""

    def read(path: str) -> bytes:
        key = path.replace("\\", "/").removeprefix("./")
        info = members.get(base + key) or members.get(key)
        if info is None:
            raise EvaluationInputError(f"Mask '{path}' listed in manifest.csv is not in the archive.")
        return bundle.read(info)

    rows, dice, iou, empty, hd95 = [], [], [], [], []
    for patient, reference_path, predicted_path in zip(columns["patient_id"], columns["reference_mask"], columns["predicted_mask"]):
        truth = _load_mask(read(reference_path), reference_path)
        predicted = _load_mask(read(predicted_path), predicted_path)
        if truth.shape != predicted.shape:
            raise EvaluationInputError(f"Mask shapes differ for {reference_path}: {truth.shape} vs {predicted.shape}.")
        pair_dice, pair_iou = _overlap(truth, predicted)
        distances = _surface_distances(truth, predicted, spacing)
        dice.append(pair_dice)
        iou.append(pair_iou)
        empty.append(not truth.any())
        hd95.append(distances["hausdorff_95"] if distances else None)
        rows.append({"patient_id": patient, "reference_mask": reference_path, "dice": pair_dice, "iou": pair_iou, "reference_empty": not truth.any(), "hausdorff_95": hd95[-1]})

    dice_array, iou_array, empty_array = np.array(dice), np.array(iou), np.array(empty)
    nonempty = ~empty_array
    defined_hd95 = [value for value in hd95 if value is not None]
    groups = np.array(columns["patient_id"])
    confidence: dict[str, Any] = {}
    if n >= MIN_ROWS_FOR_CI:
        confidence["mean_dice"] = _bootstrap(lambda index: float(dice_array[index].mean()), n, groups, rounds, seed)
        confidence["mean_iou"] = _bootstrap(lambda index: float(iou_array[index].mean()), n, groups, rounds, seed + 1)
    else:
        confidence = {"status": "NOT_COMPUTED_SMALL_SAMPLE", "requirement": f"n >= {MIN_ROWS_FOR_CI}"}
    return {
        "task_type": "segmentation_batch",
        "n": n,
        "n_groups": int(len(np.unique(groups))),
        "dropped_rows_missing_values": dropped,
        "spacing": {"x": spacing[0], "y": spacing[1], "unit": unit},
        "metrics": {
            "mean_dice": float(dice_array.mean()),
            "mean_iou": float(iou_array.mean()),
            "mean_dice_nonempty_reference": float(dice_array[nonempty].mean()) if nonempty.any() else None,
            "mean_iou_nonempty_reference": float(iou_array[nonempty].mean()) if nonempty.any() else None,
            "mean_hausdorff_95": float(np.mean(defined_hd95)) if defined_hd95 else None,
            "n_empty_reference_masks": int(empty_array.sum()),
            "n_nonempty_reference_masks": int(nonempty.sum()),
            "n_pairs_with_surface_distance": len(defined_hd95),
        },
        "confidence_intervals_95": confidence,
        "bootstrap": {"method": "percentile", "resamples": rounds, "seed": seed, "unit": "patient_id"},
        "empty_mask_convention": EMPTY_MASK_CONVENTION,
        "per_pair": rows[:1000],
        "assumptions": ["2D masks only; this is not a 3D volume evaluator.", "Hausdorff distances are averaged over pairs where both masks are non-empty."],
    }


def evaluate_forecast(content: bytes, rounds: int = DEFAULT_BOOTSTRAP, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    """MAE and RMSE per (target, horizon), the validation kit's forecast definition (Eq. 5-6).
    Errors are never pooled across targets, whose units differ."""
    columns, dropped = parse_csv(content, ["patient_id", "target", "horizon", "y_true", "y_pred"])
    y = _floats(columns["y_true"], "y_true")
    prediction = _floats(columns["y_pred"], "y_pred")
    if len(y) == 0:
        raise EvaluationInputError("No complete forecast rows.")
    keys = list(zip(columns["target"], columns["horizon"]))
    patients = np.array(columns["patient_id"])
    groups = []
    for index, (target, horizon) in enumerate(sorted(set(keys))):
        rows = np.array([position for position, key in enumerate(keys) if key == (target, horizon)])
        error = prediction[rows] - y[rows]
        entry: dict[str, Any] = {
            "target": target,
            "horizon": horizon,
            "n": int(len(rows)),
            "n_patients": int(len(np.unique(patients[rows]))),
            "mae": float(np.mean(np.abs(error))),
            "rmse": float(np.sqrt(np.mean(error ** 2))),
            "mean_error_bias": float(np.mean(error)),
        }
        if len(rows) >= MIN_ROWS_FOR_CI:
            entry["confidence_intervals_95"] = {
                "mae": _bootstrap(lambda sample: float(np.mean(np.abs(error[sample]))), len(rows), patients[rows], rounds, seed + 2 * index),
                "rmse": _bootstrap(lambda sample: float(np.sqrt(np.mean(error[sample] ** 2))), len(rows), patients[rows], rounds, seed + 2 * index + 1),
            }
        else:
            entry["confidence_intervals_95"] = {"status": "NOT_COMPUTED_SMALL_SAMPLE", "requirement": f"n >= {MIN_ROWS_FOR_CI}"}
        groups.append(entry)
    return {
        "task_type": "forecast",
        "n": int(len(y)),
        "n_groups": int(len(np.unique(patients))),
        "dropped_rows_missing_values": dropped,
        "metrics": {"targets_evaluated": len(groups)},
        "per_target_and_horizon": groups,
        "bootstrap": {"method": "percentile", "resamples": rounds, "seed": seed, "unit": "patient_id"},
        "assumptions": ["Predictions come from a chronological held-out split of genuinely longitudinal data.", "Units and target definitions are identical within each (target, horizon) group."],
    }


def evaluate_lab_extraction(content: bytes, abs_tolerance: float = 0.0) -> dict[str, Any]:
    """The validation kit's pre-matched numeric lab extraction audit."""
    if abs_tolerance < 0:
        raise EvaluationInputError("Tolerance must be non-negative.")
    required = ["patient_id", "source_id", "analyte_code", "reference_value", "predicted_value", "reference_unit", "predicted_unit"]
    columns, _ = parse_csv(content, required, keep_empty=True)
    n = len(columns["patient_id"])
    if n == 0:
        raise EvaluationInputError("No labeled evaluation rows supplied.")
    keys = list(zip(columns["patient_id"], columns["source_id"], columns["analyte_code"]))
    if len(set(keys)) != len(keys):
        raise EvaluationInputError("Duplicate observations. Disambiguate collection time or test method in source_id.")

    def number(value: str) -> float:
        try:
            parsed = float(value)
        except ValueError:
            return math.nan
        return parsed if math.isfinite(parsed) else math.nan

    reference = np.array([number(value) for value in columns["reference_value"]])
    predicted = np.array([number(value) for value in columns["predicted_value"]])
    observed = np.isfinite(reference) & np.isfinite(predicted)
    units = np.array([a.strip().lower() == b.strip().lower() for a, b in zip(columns["reference_unit"], columns["predicted_unit"])])
    matches = observed & units & (np.abs(np.where(observed, reference - predicted, np.inf)) <= abs_tolerance)
    per_analyte = []
    for code in sorted(set(columns["analyte_code"])):
        rows = np.array([index for index, value in enumerate(columns["analyte_code"]) if value == code])
        per_analyte.append({"analyte_code": code, "n": int(len(rows)), "match_rate": float(matches[rows].mean())})
    return {
        "task_type": "lab_extraction",
        "n": n,
        "n_groups": int(len(set(columns["patient_id"]))),
        "metrics": {
            "value_and_unit_exact_match_rate_at_tolerance": float(matches.mean()),
            "extracted_numeric_rate": float(observed.mean()),
            "unit_match_rate": float(units.mean()),
            "matched_correct": int(matches.sum()),
        },
        "tolerance_in_reference_units": abs_tolerance,
        "per_analyte": per_analyte,
        "caveat": "Does not compute missed observations, false-positive extraction, document-level NER precision/recall, OCR error or medical correctness; requires independently annotated corpora.",
    }


def evaluate_detection(predictions: bytes, annotations: bytes) -> dict[str, Any]:
    """COCO bbox evaluation with pycocotools' standard COCOeval, as in the validation kit (Eq. 11)."""
    import contextlib
    import json

    try:
        from pycocotools.coco import COCO
        from pycocotools.cocoeval import COCOeval
    except ImportError:
        return {"task_type": "detection", "n": 0, "status": "DEPENDENCY_MISSING", "reason": "Install pycocotools; classification accuracy is never substituted for mAP."}
    try:
        reference = json.loads(annotations.decode("utf-8-sig"))
        detections = json.loads(predictions.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationInputError(f"Both files must be COCO JSON: {exc}") from exc
    if not isinstance(reference, dict) or not {"images", "annotations", "categories"} <= reference.keys():
        raise EvaluationInputError("Reference must be a COCO annotations object with images, annotations and categories.")
    if not isinstance(detections, list) or not detections:
        raise EvaluationInputError("Predictions must be a non-empty COCO results list of {image_id, category_id, bbox, score}.")
    if any(not isinstance(item, dict) or not {"image_id", "category_id", "bbox", "score"} <= item.keys() for item in detections):
        raise EvaluationInputError("Every detection needs image_id, category_id, bbox [x, y, w, h] and score.")
    image_ids = {image["id"] for image in reference["images"]}
    unknown = sorted({item["image_id"] for item in detections} - image_ids, key=str)
    if unknown:
        raise EvaluationInputError(f"Detections reference images absent from the reference set: {unknown[:5]}.")
    derived_area = 0
    for annotation in reference["annotations"]:
        if not {"id", "image_id", "category_id", "bbox"} <= annotation.keys():
            raise EvaluationInputError("Every reference annotation needs id, image_id, category_id and bbox.")
        if "area" not in annotation:
            annotation["area"] = float(annotation["bbox"][2]) * float(annotation["bbox"][3])
            derived_area += 1
    with contextlib.redirect_stdout(io.StringIO()) as log:
        ground_truth = COCO()
        ground_truth.dataset = reference
        ground_truth.createIndex()
        results = ground_truth.loadRes(detections)
        evaluator = COCOeval(ground_truth, results, "bbox")
        evaluator.evaluate()
        evaluator.accumulate()
        evaluator.summarize()
    names = ["map_50_95", "ap_50", "ap_75", "ap_small", "ap_medium", "ap_large", "ar_1", "ar_10", "ar_100", "ar_small", "ar_medium", "ar_large"]
    metrics = {name: (None if value < 0 else float(value)) for name, value in zip(names, evaluator.stats)}
    precision = evaluator.eval["precision"]  # [iou, recall, category, area, max detections]
    per_category = []
    for position, category_id in enumerate(int(value) for value in evaluator.params.catIds):
        values = precision[:, :, position, 0, -1]
        valid = values[values > -1]
        name = str(ground_truth.cats.get(category_id, {}).get("name", category_id))
        per_category.append({"category_id": category_id, "name": name, "ap_50_95": float(valid.mean()) if valid.size else None, "reference_boxes": len(ground_truth.getAnnIds(catIds=[category_id]))})
    return {
        "task_type": "detection",
        "n": len(image_ids),
        "n_groups": None,
        "metrics": metrics,
        "per_category": per_category,
        "detections": len(detections),
        "reference_boxes": len(reference["annotations"]),
        "reference_area_derived_from_bbox": derived_area,
        "evaluation_protocol": "pycocotools COCOeval bbox: IoU 0.50:0.05:0.95, 101-point interpolated precision, area ranges all/small/medium/large, max 1/10/100 detections. -1 (undefined) is reported as null.",
        "summary_text": log.getvalue().strip(),
    }
