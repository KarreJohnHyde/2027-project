"""Shared training utilities: determinism, run directories, checkpoints, provenance."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import random
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "training"
REPORTS = ROOT / "docs" / "validation" / "models"
MODEL_CARDS = ROOT / "docs" / "models"


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True


def seed_worker(worker_id: int) -> None:
    seed = torch.initial_seed() % 2**32
    np.random.seed(seed)
    random.seed(seed)


def device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def read_samples(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_revision() -> dict:
    def run(*args: str) -> str | None:
        try:
            return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
    status = run("status", "--porcelain", "--untracked-files=no")
    return {"commit": run("rev-parse", "HEAD"), "working_tree_clean": None if status is None else status == ""}


def environment() -> dict:
    info = {
        "python": sys.version.split()[0], "platform": platform.platform(), "torch": torch.__version__,
        "cuda_runtime": torch.version.cuda, "cudnn": torch.backends.cudnn.version(),
        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
    }
    for package in ("torchvision", "monai", "numpy", "pycocotools"):
        try:
            from importlib.metadata import version

            info[package] = version(package)
        except Exception:  # noqa: BLE001
            info[package] = None
    return info


@dataclass
class Run:
    model_id: str
    task_id: str
    config: dict[str, Any]
    run_id: str = ""
    directory: Path = field(default_factory=Path)
    started: float = field(default_factory=time.monotonic)

    def __post_init__(self) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run_id = f"{self.model_id}-{stamp}"
        self.directory = ARTIFACTS / self.run_id
        self.directory.mkdir(parents=True, exist_ok=True)
        self.write_json("config.json", {"model_id": self.model_id, "task_id": self.task_id, "run_id": self.run_id,
                                        "config": self.config, "environment": environment(), "git": git_revision(),
                                        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})

    def log(self, **values) -> None:
        values = {"t": round(time.monotonic() - self.started, 1), **values}
        print(json.dumps(values), flush=True)
        with (self.directory / "log.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(values) + "\n")

    def write_json(self, name: str, payload: Any) -> Path:
        path = self.directory / name
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    def save_checkpoint(self, payload: dict) -> tuple[Path, str]:
        path = self.directory / "model.pt"
        torch.save(payload, path)
        return path, sha256_file(path)

    @property
    def elapsed_seconds(self) -> float:
        return round(time.monotonic() - self.started, 1)


def bootstrap_ci(metric, n: int, groups: np.ndarray | None, rounds: int = 1000, seed: int = 20261024, unit: str | None = None) -> dict:
    """Percentile bootstrap; resamples groups (near-duplicate groups unless `unit` names them) or rows with replacement."""
    rng = np.random.default_rng(seed)
    if groups is not None:
        unique = np.unique(groups)
        members = {group: np.flatnonzero(groups == group) for group in unique}
    values = []
    for _ in range(rounds):
        if groups is not None:
            chosen = rng.choice(unique, size=len(unique), replace=True)
            index = np.concatenate([members[group] for group in chosen])
        else:
            index = rng.integers(0, n, size=n)
        value = metric(index)
        if value is not None and np.isfinite(value):
            values.append(value)
    if len(values) < rounds * 0.9:
        return {"status": "NOT_COMPUTED_TOO_MANY_DEGENERATE_RESAMPLES"}
    low, high = np.percentile(values, [2.5, 97.5])
    return {"status": "COMPUTED", "low": float(low), "high": float(high), "resamples": len(values),
            "unit": unit or ("near-duplicate group" if groups is not None else "image")}


def register_model(entry: dict) -> None:
    """Adds or replaces a model in model_registry/models.json (artifact bundle schema v1)."""
    path = ROOT / "model_registry" / "models.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    registry["models"] = [model for model in registry["models"] if model["model_id"] != entry["model_id"]] + [entry]
    path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT)).replace("\\", "/")


def checkpoint_ref(path: Path) -> str:
    """Checkpoints live outside Git; record them relative to the repository."""
    return relative(path)


def cross_split_component_summary(rows: list[dict]) -> dict[str, Any]:
    """Describe duplicate components that span publisher splits.

    A directly confirmed duplicate pair is not the only possible leakage path:
    near-duplicate grouping is transitive. If any member of a component occurs in
    another split, exclude the whole component from the conservative test subset.
    """
    splits_by_group: dict[str, set[str]] = {}
    for row in rows:
        group = str(row.get("group_id", "")).strip()
        split = str(row.get("split", "")).strip()
        if group and split:
            splits_by_group.setdefault(group, set()).add(split)
    crossing = {group for group, splits in splits_by_group.items() if len(splits) > 1}
    members = [row for row in rows if str(row.get("group_id", "")).strip() in crossing]
    return {
        "group_ids": crossing,
        "near_duplicate_components_crossing_splits": len(crossing),
        "images_in_crossing_components": len(members),
        "test_images_in_crossing_components": sum(1 for row in members if row.get("split") == "test"),
        "exclusion_rule": "exclude every test image in a transitive near-duplicate component that spans publisher splits",
    }


def env_flag(name: str, default: str) -> str:
    return os.getenv(name, default)
