"""Bounded, secret-free runtime inventory; never changes host security policy."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path


def probe(include_torch: bool = False) -> dict:
    packages = {}
    for name in ("torch", "torchvision", "monai", "numpy", "fastapi", "pytest", "rapidocr-onnxruntime"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    result = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "interpreter": sys.executable,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": packages,
        "torch": {"status": "NOT_PROBED"},
        "security_policy_changed": False,
    }
    if include_torch:
        try:
            import torch
            value = torch.tensor([1.0, 2.0]).square().sum().item()
            result["torch"] = {
                "status": "VERIFIED_IMPORT_AND_TENSOR_OPERATION",
                "version": torch.__version__,
                "cuda_available": torch.cuda.is_available(),
                "cuda_runtime": torch.version.cuda,
                "tensor_control": value,
            }
        except (ImportError, OSError, RuntimeError) as exc:
            result["torch"] = {"status": "BLOCKED", "exception": type(exc).__name__, "reason": str(exc)}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--torch", action="store_true", help="Import torch and execute a small tensor control")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = probe(args.torch)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 1 if result["torch"]["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
