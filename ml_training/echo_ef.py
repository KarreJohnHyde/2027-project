"""Ejection-fraction regression on EchoNet-Dynamic (R(2+1)-D ResNet-18, random initialisation).

Protocol: the publisher's TRAIN / VAL / TEST split (one video per patient). Train on random 32-frame clips
(every second frame) with small random shifts; select the epoch with the lowest validation MAE on one
centre clip per video; evaluate the frozen checkpoint once on the test videos that pass the serving
input gate, averaging every clip at a stride of 16 frames, through the serving functions
(app.services.echo_inference). Confidence intervals resample patients (one video each).

    python -m ml_training.echo_ef --epochs 30
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset

from ml_training.common import (MODEL_CARDS, REPORTS, ROOT, Run, bootstrap_ci, checkpoint_ref, device, load_resume, read_samples, register_model,
                                relative, save_resume, seed_worker, set_seed)

sys.path.insert(0, str(ROOT / "backend"))
from app.services import echo_inference as echo  # noqa: E402  (serving functions)

TASK_ID = "echonet-ef-regression"
MODEL_ID = "echonet_ef_r2plus1d"


def task_entry() -> tuple[dict, dict]:
    tasks = json.loads((ROOT / "dataset_registry" / "tasks.json").read_text(encoding="utf-8"))
    return next((d, t) for d in tasks["datasets"] for t in d["tasks"] if t["task_id"] == TASK_ID)


def channel_statistics(rows: list[dict], n: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    chosen = rng.choice(len(rows), size=min(n, len(rows)), replace=False)
    total, squares, count = np.zeros(3), np.zeros(3), 0
    for index in chosen:
        frames = echo.read_video(Path(rows[index]["path"])).frames.astype(np.float64)
        total += frames.sum(axis=(0, 1, 2))
        squares += (frames ** 2).sum(axis=(0, 1, 2))
        count += frames.shape[0] * frames.shape[1] * frames.shape[2]
    mean = total / count
    return mean.astype(np.float32), np.sqrt(squares / count - mean ** 2).astype(np.float32)


class ClipSet(Dataset):
    """Random clips with zero-padded short videos (training only) and a random shift of up to ``pad`` pixels."""

    def __init__(self, rows: list[dict], mean: np.ndarray, std: np.ndarray, train: bool, pad: int = 8):
        self.rows, self.mean, self.std, self.train, self.pad = rows, mean, std, train, pad

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int):
        row = self.rows[index]
        frames = echo.read_video(Path(row["path"])).frames
        need = echo.needed_frames()
        if len(frames) < need:
            frames = np.concatenate([frames, np.zeros((need - len(frames), *frames.shape[1:]), dtype=frames.dtype)])
        if self.train:
            start = int(np.random.randint(0, len(frames) - need + 1))
        else:
            starts = echo.clip_starts(len(frames), stride=1)
            start = starts[len(starts) // 2]
        x = echo.normalise(echo.clip(frames, start), self.mean, self.std)
        if self.train and self.pad:
            padded = np.pad(x, ((0, 0), (0, 0), (self.pad, self.pad), (self.pad, self.pad)))
            i, j = np.random.randint(0, 2 * self.pad + 1, size=2)
            x = padded[:, :, i:i + echo.SIZE, j:j + echo.SIZE]
        return torch.from_numpy(np.ascontiguousarray(x)), torch.tensor(float(row["ef"]), dtype=torch.float32)


def regression_metrics(truth: np.ndarray, predicted: np.ndarray) -> dict:
    error = predicted - truth
    total = float(((truth - truth.mean()) ** 2).sum())
    return {"mae": float(np.abs(error).mean()), "rmse": float(np.sqrt((error ** 2).mean())), "bias": float(error.mean()),
            "r2": float(1 - (error ** 2).sum() / total) if total else None, "n": int(len(truth))}


def auroc(labels: np.ndarray, scores: np.ndarray) -> float | None:
    positives, negatives = scores[labels == 1], scores[labels == 0]
    if not len(positives) or not len(negatives):
        return None
    order = np.argsort(np.concatenate([positives, negatives]), kind="mergesort")
    ranks = np.empty(len(order))
    ranks[order] = np.arange(1, len(order) + 1)
    values = np.concatenate([positives, negatives])
    for value in np.unique(values):  # average ranks of ties
        tied = values == value
        ranks[tied] = ranks[tied].mean()
    return float((ranks[:len(positives)].sum() - len(positives) * (len(positives) + 1) / 2) / (len(positives) * len(negatives)))


def evaluate_split(network, rows: list[dict], mean: np.ndarray, std: np.ndarray, envelope: dict, dev) -> dict:
    """Serving path per video: read, input gate, multi-clip average."""
    accepted, refused, truth, predicted, names = 0, {}, [], [], []
    for row in rows:
        video = echo.read_video(Path(row["path"]))
        try:
            echo.check_video(video, envelope)
        except echo.EchoInputError as exc:
            code = str(exc).split(":")[0]
            refused[code] = refused.get(code, 0) + 1
            continue
        accepted += 1
        truth.append(float(row["ef"]))
        predicted.append(echo.predict(network, video, mean, std, dev)["ef_percent"])
        names.append(row["group_id"])
    truth_array, predicted_array = np.array(truth), np.array(predicted)
    groups = np.array(names)
    metrics = regression_metrics(truth_array, predicted_array)
    ci = {key: bootstrap_ci(lambda index, key=key: regression_metrics(truth_array[index], predicted_array[index])[key], len(truth), groups, unit="patient (one video)")
          for key in ("mae", "rmse", "r2")}
    reduced = (truth_array < 50).astype(int)
    discrimination = {"definition": "reference EF below 50%", "positives": int(reduced.sum()), "auroc_of_negative_estimate": auroc(reduced, -predicted_array),
                      "auroc_95ci": bootstrap_ci(lambda index: auroc(reduced[index], -predicted_array[index]), len(truth), groups, unit="patient (one video)")}
    return {"videos": len(rows), "accepted_by_gate": accepted, "refused_by_gate": refused, "metrics": metrics, "metrics_95ci": ci,
            "reduced_ef_discrimination": discrimination, "predictions": [{"video": n, "reference_ef": t, "estimated_ef": round(p, 3)}
                                                                         for n, t, p in zip(names, truth, predicted)]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20261106)
    parser.add_argument("--limit", type=int, default=0, help="Smoke test: use this many videos per split.")
    parser.add_argument("--resume-file", type=Path, default=None,
                        help="Training state written after every epoch; an existing file for the same settings is resumed.")
    args = parser.parse_args()

    dataset, task = task_entry()
    if not task["training_eligible"]:
        raise SystemExit(f"{TASK_ID} is not training-eligible: {task['flags']}")
    prep = task["preparation"]
    rows = read_samples(Path(prep["sample_manifest"]))
    splits = {split: [row for row in rows if row["split"] == split] for split in ("train", "val", "test")}
    if args.limit:
        splits = {split: items[:args.limit] for split, items in splits.items()}
    set_seed(args.seed)
    torch.backends.cudnn.benchmark = True  # recorded; reruns can differ slightly
    torch.backends.cudnn.deterministic = False
    dev = device()
    mean, std = channel_statistics(splits["train"], 500 if not args.limit else 8, args.seed)
    fps = np.array([float(row["fps"]) for row in splits["train"]])
    envelope = {"size": [echo.SIZE, echo.SIZE], "fps_range": [float(fps.min()), float(fps.max())], "min_frames": echo.needed_frames(),
                "max_coloured_pixel_fraction": 0.05, "development_split": "train"}
    run = Run(MODEL_ID, TASK_ID, {**vars(args), "dataset_version": prep["dataset_version"], "mean": mean.tolist(), "std": std.tolist(), "envelope": envelope})
    network = echo.build_network().to(dev)
    with torch.no_grad():
        network.fc.bias.fill_(float(np.mean([float(row["ef"]) for row in splits["train"]])))
    identity = {key: getattr(args, key) for key in ("epochs", "batch_size", "lr", "weight_decay", "seed", "limit")} | {"dataset_version": prep["dataset_version"]}
    resumed = load_resume(args.resume_file, identity)
    start_epoch = 1 if resumed is None else int(resumed["epoch"]) + 1
    # A resumed run draws a fresh data order for the remaining epochs (recorded in the report).
    loader = DataLoader(ClipSet(splits["train"], mean, std, train=True), batch_size=args.batch_size, shuffle=True, num_workers=args.workers,
                        worker_init_fn=seed_worker, generator=torch.Generator().manual_seed(args.seed + start_epoch - 1),
                        persistent_workers=args.workers > 0, drop_last=True, pin_memory=dev.type == "cuda")
    val_loader = DataLoader(ClipSet(splits["val"], mean, std, train=False), batch_size=args.batch_size, num_workers=args.workers,
                            persistent_workers=args.workers > 0)
    optimizer = torch.optim.AdamW(network.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    steps = args.epochs * max(1, len(loader))
    scheduler = torch.optim.lr_scheduler.OneCycleLR(optimizer, max_lr=args.lr, total_steps=steps, pct_start=0.1)
    scaler = torch.amp.GradScaler("cuda", enabled=dev.type == "cuda")
    best_state, best_mae, best_epoch = None, math.inf, -1
    if resumed is not None:
        network.load_state_dict(resumed["model"])
        optimizer.load_state_dict(resumed["optimizer"])
        scheduler.load_state_dict(resumed["scheduler"])
        scaler.load_state_dict(resumed["scaler"])
        best_state, best_mae, best_epoch = resumed["best_state"], float(resumed["best_mae"]), int(resumed["best_epoch"])
        run.log(resumed_from_epoch=int(resumed["epoch"]), resume_file=str(args.resume_file), best_epoch_so_far=best_epoch)
    for epoch in range(start_epoch, args.epochs + 1):
        started = time.monotonic()
        network.train()
        running = 0.0
        for clips, targets in loader:
            clips, targets = clips.to(dev, non_blocking=True), targets.to(dev, non_blocking=True)
            with torch.autocast(dev.type, dtype=torch.float16, enabled=dev.type == "cuda"):
                loss = torch.nn.functional.mse_loss(network(clips).float().flatten(), targets)
            optimizer.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(network.parameters(), 10.0)
            scaler.step(optimizer)
            scaler.update()
            scheduler.step()
            running += loss.item()
        network.eval()
        errors = []
        with torch.no_grad(), torch.autocast(dev.type, dtype=torch.float16, enabled=dev.type == "cuda"):
            for clips, targets in val_loader:
                errors += (network(clips.to(dev)).float().flatten().cpu() - targets).abs().tolist()
        val_mae = float(np.mean(errors))
        run.log(epoch=epoch, train_mse=round(running / max(1, len(loader)), 3), val_mae_centre_clip=round(val_mae, 3),
                epoch_seconds=round(time.monotonic() - started, 1), gpu_peak_mib=int(torch.cuda.max_memory_allocated() / 2**20) if dev.type == "cuda" else None)
        if val_mae < best_mae:
            best_state, best_mae, best_epoch = copy.deepcopy({k: v.cpu() for k, v in network.state_dict().items()}), val_mae, epoch
            torch.save({"state_dict": best_state, "epoch": epoch}, run.directory / "best_state.pt")
        save_resume(args.resume_file, identity, {"epoch": epoch, "model": network.state_dict(), "optimizer": optimizer.state_dict(),
                                                 "scheduler": scheduler.state_dict(), "scaler": scaler.state_dict(), "best_state": best_state,
                                                 "best_mae": best_mae, "best_epoch": best_epoch})
    network.load_state_dict(best_state)
    # Plain floats: the serving loader deserialises with weights_only=True.
    payload = {"kind": "echo_ef_regressor", "arch": echo.ARCH, "state_dict": best_state, "mean": [float(v) for v in mean], "std": [float(v) for v in std],
               "clip_frames": echo.CLIP_FRAMES,
               "frame_period": echo.PERIOD, "size": echo.SIZE, "test_stride": echo.TEST_STRIDE, "envelope": envelope, "task_id": TASK_ID,
               "dataset_version": prep["dataset_version"], "preprocessing": "RGB uint8 -> channel z-score with training statistics; no resizing"}
    checkpoint_path, checkpoint_sha = run.save_checkpoint(payload)
    validation = evaluate_split(network, splits["val"], mean, std, envelope, dev)
    test = evaluate_split(network, splits["test"], mean, std, envelope, dev)
    run.write_json("predictions_test.json", test.pop("predictions"))
    validation.pop("predictions")
    report = {
        "model_id": MODEL_ID, "run_id": run.run_id, "task_id": TASK_ID, "task_type": "video_regression", "dataset": dataset["title"], "dataset_id": dataset["id"],
        "dataset_version": prep["dataset_version"], "dataset_license": dataset["license"], "split_method": prep["split_method"], "split_counts": prep["per_split"],
        "selection": {"criterion": "validation MAE, one centre clip per video", "best_epoch": best_epoch, "val_mae_centre_clip": best_mae, "epochs_run": args.epochs,
                      "resumed_from_epoch": None if resumed is None else int(resumed["epoch"])},
        "evaluation_protocol": f"serving path: input gate, then the mean of {echo.CLIP_FRAMES}-frame clips (every {echo.PERIOD}nd frame) at a stride of {echo.TEST_STRIDE} frames",
        "validation": validation, "test": test, "input_envelope": envelope,
        "checkpoint": {"path": checkpoint_ref(checkpoint_path), "sha256": checkpoint_sha}, "held_out_predictions": checkpoint_ref(run.directory / "predictions_test.json"),
        "training_seconds": run.elapsed_seconds, "config": {**vars(args), "resume_file": None if args.resume_file is None else str(args.resume_file)},
        "limitations": [
            "Internal test on the publisher's EchoNet-Dynamic split (one centre); no external or clinical validation.",
            "EchoNet-format input only: 112 x 112 apical-4-chamber videos with the sector cropped and masked; other formats are refused, never resized.",
            "One estimate per video from averaged clips; no beat-by-beat segmentation and no end-systolic/end-diastolic frame selection.",
            "Trained from random initialisation (no pretrained video weights); evaluated under float16 autocast on CUDA.",
            "Research-only output; not for diagnosis or treatment decisions.",
        ],
        "citation": dataset["license"].get("citation"),
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS / f"{MODEL_ID}.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    m, ci = test["metrics"], test["metrics_95ci"]

    def interval(item: dict) -> str:
        return f"{item['low']:.2f}-{item['high']:.2f}" if item.get("status") == "COMPUTED" else "not computed"

    card = [
        "# Model card: Left-ventricular ejection fraction from echocardiography video (EchoNet-Dynamic, research)", "",
        f"- **Model id:** `{MODEL_ID}` (registry status `READY_UNVALIDATED`; research-only)",
        f"- **Task:** {task['target']}.",
        f"- **Data:** {dataset['title']} ({dataset['license']['name']}; owner authorisation recorded {dataset['license'].get('authorized_on')}); "
        f"dataset version `{prep['dataset_version'][:16]}`; {prep['split_method']}; split {prep['per_split']}.",
        f"- **Architecture:** R(2+1)-D ResNet-18 (torchvision), random initialisation; best validation epoch {best_epoch} of {args.epochs}.",
        f"- **Input:** EchoNet-format MP4/AVI, {echo.SIZE} x {echo.SIZE} pixels, {envelope['fps_range'][0]:g}-{envelope['fps_range'][1]:g} frames per second, "
        f"at least {echo.needed_frames()} frames.",
        f"- **Checkpoint:** `{checkpoint_ref(checkpoint_path)}`, SHA-256 `{checkpoint_sha}`.", "",
        f"## Held-out test results ({test['accepted_by_gate']} of {test['videos']} test videos accepted by the input gate, evaluated once through the serving function)", "",
        f"- MAE {m['mae']:.2f} EF points (95% CI {interval(ci['mae'])}); RMSE {m['rmse']:.2f} ({interval(ci['rmse'])}); R² {m['r2']:.3f} ({interval(ci['r2'])}); bias {m['bias']:+.2f}.",
        f"- Reference EF below 50%: AUROC {test['reduced_ef_discrimination']['auroc_of_negative_estimate']:.3f} "
        f"({interval(test['reduced_ef_discrimination']['auroc_95ci'])}), {test['reduced_ef_discrimination']['positives']} positives.",
        "", "## Limitations", "", *[f"- {item}" for item in report["limitations"]], "", f"Full report: `{relative(report_path)}`.",
    ]
    MODEL_CARDS.mkdir(parents=True, exist_ok=True)
    (MODEL_CARDS / f"{MODEL_ID}.md").write_text("\n".join(card) + "\n", encoding="utf-8")
    register_model({
        "model_id": MODEL_ID, "display_name": "Ejection fraction from apical-4-chamber echo video (EchoNet-Dynamic, research)", "domain": "cardiology",
        "task": "video_regression", "anatomy": "heart", "framework": "torchvision r2plus1d_18", "adapter": "app.services.echo_inference",
        "source_repository": "medtwin/training", "dependency_environment": ".venv", "weights_path": checkpoint_ref(checkpoint_path), "device": "cuda_or_cpu",
        "supported_inputs": ["video/mp4", "video/x-msvideo"], "supported_modalities": ["ECHO"], "supported_classes": ["ejection_fraction_percent"],
        "status": "READY_UNVALIDATED", "validated": False, "research_inference": True, "inference_input": "echo_video", "limitations": report["limitations"],
        "artifact_bundle": {
            "dataset_version": prep["dataset_version"], "dataset_license": dataset["license"]["name"], "split_manifest_path": relative(Path(prep["sample_manifest"])),
            "task_definition": task["target"], "label_definition": {"source": "FileList.csv EF (tracing-derived)", "unit": "percent"},
            "preprocessing_version": "echonet-112-clip32-period2-zscore-v1", "checkpoint_path": checkpoint_ref(checkpoint_path), "checkpoint_sha256": checkpoint_sha,
            "calibration": None, "decision_thresholds": None, "abstention_thresholds": None, "input_envelope": envelope,
            "held_out_predictions_path": checkpoint_ref(run.directory / "predictions_test.json"), "evaluation_report_path": relative(report_path),
            "model_card_path": relative(MODEL_CARDS / f"{MODEL_ID}.md"),
        },
    })
    run.log(event="done", test_mae=m["mae"], test_r2=m["r2"], checkpoint_sha256=checkpoint_sha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
