"""Left-ventricular ejection fraction from an apical-4-chamber echocardiography video (research).

The network is an R(2+1)-D ResNet-18 trained from random initialisation on EchoNet-Dynamic
(ml_training/echo_ef.py). Video reading, clip sampling and normalisation live here and the trainer
imports them, so the held-out evaluation ran the serving code.

The development videos are EchoNet's own format: 112 x 112 pixels, the ultrasound sector already
cropped and everything outside it masked. Videos in any other format are refused, never resized into
it: a full-screen export with the scanner's interface is a different input.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

CLIP_FRAMES = 32
PERIOD = 2  # every second frame, as in EchoNet-Dynamic
SIZE = 112
TEST_STRIDE = 16  # clip starts for the multi-clip average
ARCH = "r2plus1d_18"
VIDEO_SUFFIXES = {".mp4", ".avi"}


class EchoInputError(Exception):
    """The video is outside the format the model was developed on."""


@dataclass
class EchoVideo:
    frames: np.ndarray  # (T, H, W, 3) uint8, RGB
    fps: float
    source_frames: int


MAX_DECODED_BYTES = 256 * 1024 * 1024


def read_video(path: Path, max_frames: int = 2000, require_size: bool = True) -> EchoVideo:
    """Decode the video; with ``require_size`` a frame size other than the development size is refused on the first
    frame, before anything else is buffered."""
    import cv2

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise EchoInputError("VIDEO_UNREADABLE: the file could not be decoded as a video.")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    frames = []
    try:
        while len(frames) < max_frames:
            ok, frame = capture.read()
            if not ok:
                break
            if not frames and require_size and frame.shape[:2] != (SIZE, SIZE):
                height, width = frame.shape[:2]
                raise EchoInputError(f"MODEL_INPUT_INCOMPATIBLE: frames are {width} x {height} pixels; the model was developed on "
                                     f"EchoNet-format {SIZE} x {SIZE} videos with the sector cropped and masked. The video was not resized.")
            if (len(frames) + 1) * frame.nbytes > MAX_DECODED_BYTES:
                raise EchoInputError("VIDEO_TOO_LARGE: the decoded video exceeds the reading limit.")
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    finally:
        capture.release()
    if not frames:
        raise EchoInputError("VIDEO_UNREADABLE: no frame could be decoded.")
    return EchoVideo(np.stack(frames), fps, len(frames))


def needed_frames() -> int:
    return (CLIP_FRAMES - 1) * PERIOD + 1


def clip_starts(n_frames: int, stride: int = TEST_STRIDE) -> list[int]:
    """Start frames of every evaluation clip (at least one; the last clip ends at the last frame)."""
    last = n_frames - needed_frames()
    if last < 0:
        return []
    starts = list(range(0, last + 1, stride))
    if starts[-1] != last:
        starts.append(last)
    return starts


def clip(frames: np.ndarray, start: int) -> np.ndarray:
    return frames[start:start + needed_frames():PERIOD]


def normalise(clip_frames: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    """(T, H, W, 3) uint8 -> (3, T, H, W) float32 standardised with the training videos' channel statistics."""
    x = clip_frames.astype(np.float32)
    x = (x - np.asarray(mean, dtype=np.float32).reshape(1, 1, 1, 3)) / np.asarray(std, dtype=np.float32).reshape(1, 1, 1, 3)
    return np.ascontiguousarray(x.transpose(3, 0, 1, 2), dtype=np.float32)


def check_video(video: EchoVideo, envelope: dict[str, Any]) -> dict[str, Any]:
    """Format checks against the development videos; raises EchoInputError with the reason."""
    _, height, width, _ = video.frames.shape
    if (height, width) != (SIZE, SIZE):
        raise EchoInputError(f"MODEL_INPUT_INCOMPATIBLE: frames are {width} x {height} pixels; the model was developed on "
                             f"EchoNet-format {SIZE} x {SIZE} videos with the sector cropped and masked. The video was not resized.")
    if video.source_frames < needed_frames():
        raise EchoInputError(f"MODEL_INPUT_INCOMPATIBLE: {video.source_frames} frames; at least {needed_frames()} are needed for one "
                             f"{CLIP_FRAMES}-frame clip at every {PERIOD}nd frame.")
    low, high = envelope.get("fps_range", [None, None])
    if low is not None and not (low <= video.fps <= high):
        raise EchoInputError(f"MODEL_INPUT_INCOMPATIBLE: {video.fps:.1f} frames per second is outside the development range "
                             f"{low:g}-{high:g}; clips would cover a different part of the heart cycle.")
    spread = video.frames.max(axis=3).astype(np.int16) - video.frames.min(axis=3)
    coloured = float(np.mean(spread > 24))
    limit = envelope.get("max_coloured_pixel_fraction")
    if limit is not None and coloured > limit:
        raise EchoInputError(f"MODEL_INPUT_INCOMPATIBLE: {coloured:.1%} of pixels are coloured (Doppler or overlays); development "
                             f"videos have at most {limit:.1%}.")
    return {"frames": video.source_frames, "fps": round(video.fps, 3), "size": [width, height], "coloured_pixel_fraction": round(coloured, 5),
            "clips": len(clip_starts(video.source_frames))}


def build_network():
    from torchvision.models.video import r2plus1d_18

    return r2plus1d_18(weights=None, num_classes=1)


def stage_modules(network) -> list:
    return [network.layer1, network.layer2, network.layer3, network.layer4]


def predict(network, video: EchoVideo, mean: np.ndarray, std: np.ndarray, device, batch: int = 8) -> dict[str, Any]:
    """Mean EF over every evaluation clip, with the per-clip values."""
    import torch

    starts = clip_starts(video.source_frames)
    values: list[float] = []
    network.eval()
    with torch.no_grad(), torch.autocast(device.type, dtype=torch.float16, enabled=device.type == "cuda"):
        for index in range(0, len(starts), batch):
            tensors = np.stack([normalise(clip(video.frames, start), mean, std) for start in starts[index:index + batch]])
            values += network(torch.from_numpy(tensors).to(device)).float().flatten().cpu().tolist()
    return {"ef_percent": float(np.mean(values)), "clip_ef_percent": [round(value, 3) for value in values], "clip_starts": starts,
            "clip_frames": CLIP_FRAMES, "frame_period": PERIOD}


def clip_features(network, video: EchoVideo, mean: np.ndarray, std: np.ndarray, device) -> list[np.ndarray]:
    """Applicability features of the centre clip: input statistics, then each stage's spatio-temporal mean."""
    import torch

    starts = clip_starts(video.source_frames, stride=1)
    start = starts[len(starts) // 2]
    tensor = torch.from_numpy(normalise(clip(video.frames, start), mean, std)[None]).to(device)
    captured: list = []
    hooks = [stage.register_forward_hook(lambda module, inputs, output: captured.append(output.float().mean(dim=(2, 3, 4))))
             for stage in stage_modules(network)]
    try:
        network.eval()
        with torch.no_grad(), torch.autocast(device.type, dtype=torch.float16, enabled=device.type == "cuda"):
            network(tensor)
    finally:
        for hook in hooks:
            hook.remove()
    x = tensor.float()[0].reshape(3, -1)
    grey = x.mean(dim=0)
    statistics = torch.cat([x.mean(dim=1), x.std(dim=1), torch.quantile(grey, torch.tensor([.05, .25, .5, .75, .95], device=grey.device))])
    return [statistics.cpu().numpy().astype(np.float64)] + [values.cpu().numpy()[0].astype(np.float64) for values in captured]


FEATURE_VERSION = "echo-input-statistics+r2plus1d-stages-v1"


def statistics(payload: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    return np.asarray(payload["mean"], dtype=np.float32), np.asarray(payload["std"], dtype=np.float32)


def interpretation(ef: float) -> Optional[str]:
    """Which band of the universal heart-failure definition (Bozkurt et al. 2021) the estimate falls in;
    a description of the number, never a diagnosis."""
    if not np.isfinite(ef):
        return None
    if ef <= 40:
        return "estimate in the reduced range (40% or below)"
    if ef < 50:
        return "estimate in the mildly reduced range (41-49%)"
    return "estimate in the preserved range (50% or above)"
