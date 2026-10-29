"""Build step of the Vercel backend service (vercel.json: services.backend.buildCommand).

Vercel bundles only this service's root (backend/), but the API reads generated evidence that
lives beside it in the repository: the model and dataset registries, validation reports, the
traceability matrix, the anatomy manifest and software-benchmark results. This copies the same
files the backend Docker image copies into backend/deployment_files/, which app.config uses
when it exists. Vercel never bundles a directory named public/, so the anatomy manifest is
staged as anatomy/manifest.json. A missing source fails the build instead of the API.

    python vercel_build.py [target directory]
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
REPOSITORY = BACKEND.parent
# (source relative to the repository, destination relative to the staged project root)
STAGED = (
    ("model_registry", "model_registry"),
    ("dataset_registry/datasets.json", "dataset_registry/datasets.json"),
    ("dataset_registry/tasks.json", "dataset_registry/tasks.json"),
    ("docs/research/traceability.json", "docs/research/traceability.json"),
    ("docs/validation", "docs/validation"),
    ("docs/anatomy/derivatives.json", "docs/anatomy/derivatives.json"),
    ("public/anatomy/manifest.json", "anatomy/manifest.json"),
    ("benchmarks/results", "benchmarks/results"),
)


def stage(target: Path) -> list[str]:
    missing = [source for source, _ in STAGED if not (REPOSITORY / source).exists()]
    if missing:
        raise SystemExit(f"vercel_build: repository files missing from the build: {', '.join(missing)}")
    if target.exists():
        shutil.rmtree(target)
    for source, destination in STAGED:
        origin, copy = REPOSITORY / source, target / destination
        copy.parent.mkdir(parents=True, exist_ok=True)
        if origin.is_dir():
            shutil.copytree(origin, copy, ignore=shutil.ignore_patterns("*.md"))
        else:
            shutil.copy2(origin, copy)
    return [destination for _, destination in STAGED]


if __name__ == "__main__":
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else BACKEND / "deployment_files"
    staged = stage(destination)
    print(f"vercel_build: staged {len(staged)} evidence paths in {destination}")
