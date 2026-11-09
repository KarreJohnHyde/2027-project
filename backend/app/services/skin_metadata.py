"""Train-only encoding and explicit-input checks for PAD clinical-image research.

Only age, documented gender and lesion region are features. Diagnosis, biopsy,
patient IDs and arbitrary JSON attributes are never accepted as model features.
"""
from __future__ import annotations

import math
import numpy as np

FIELDS = {"age", "gender", "region"}
VERSION = "pad-age-gender-region-train-only-v1"


def clean_category(value):
    return str(value or "").strip().upper()


def age_value(value):
    if isinstance(value, bool):
        raise ValueError("Age must be numeric, not a boolean")
    if value is None or str(value).strip() == "":
        return None
    try:
        age = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Age must be numeric") from exc
    if not math.isfinite(age) or not 0 <= age <= 120:
        raise ValueError("Age must be finite and between 0 and 120 years")
    return age


def fit_encoder(training_features):
    ages = [age_value(row.get("age")) for row in training_features]
    finite = np.array([age for age in ages if age is not None], dtype=float)
    if not len(finite):
        raise ValueError("No training ages for metadata preprocessing")
    categories = {field: sorted({clean_category(row.get(field)) for row in training_features} - {""})
                  for field in ("gender", "region")}
    return {"version": VERSION, "fitted_on": "train", "age_mean": float(finite.mean()),
            "age_std": max(float(finite.std()), 1.0), "age_median": float(np.median(finite)),
            "age_range": [float(finite.min()), float(finite.max())], "categories": categories,
            "dimension": 2 + sum(len(values) + 2 for values in categories.values())}


def encode(features, schema):
    if schema.get("version") != VERSION or schema.get("fitted_on") != "train":
        raise ValueError("Metadata preprocessing contract is invalid")
    if set(features) - FIELDS:
        raise ValueError("Only age, gender and region are permitted clinical features")
    age = age_value(features.get("age"))
    result = [((age if age is not None else schema["age_median"]) - schema["age_mean"]) / schema["age_std"], float(age is None)]
    for field in ("gender", "region"):
        value = clean_category(features.get(field))
        categories = schema["categories"][field]
        result.extend(float(value == category) for category in categories)
        result.extend([float(not value), float(bool(value) and value not in categories)])
    output = np.asarray(result, dtype=np.float32)
    if len(output) != schema["dimension"] or not np.isfinite(output).all():
        raise ValueError("Invalid encoded metadata dimensions or values")
    return output


def check_serving_features(features, schema):
    if not isinstance(features, dict) or not features:
        raise ValueError("Explicit clinical features are required for the image/tabular model")
    encoded = encode(features, schema)
    age = age_value(features.get("age"))
    if age is None or not schema["age_range"][0] <= age <= schema["age_range"][1]:
        raise ValueError("A documented age inside the training age range is required")
    region = clean_category(features.get("region"))
    if region not in schema["categories"]["region"]:
        raise ValueError("A documented lesion region represented in training is required")
    gender = clean_category(features.get("gender"))
    if gender and gender not in schema["categories"]["gender"]:
        raise ValueError("Provided gender is outside the recorded training categories")
    return encoded
