"""Echo video input contract and clip sampling (synthetic arrays), and the served model on one public EchoNet test video when present."""
import csv
from pathlib import Path

import numpy as np
import pytest

from app.services import echo_inference as echo
from tests.conftest import get_auth_headers

ROOT = Path(__file__).resolve().parents[2]

ENVELOPE = {"fps_range": [18.0, 138.0], "max_coloured_pixel_fraction": 0.05}


def video(frames=100, size=112, fps=50.0, colour=False):
    data = np.random.default_rng(0).integers(0, 200, size=(frames, size, size, 1), dtype=np.uint8).repeat(3, axis=3)
    if colour:
        data[..., 0] = 255
    return echo.EchoVideo(data, fps, frames)


def test_clip_sampling_covers_the_video_and_ends_at_the_last_frame():
    assert echo.needed_frames() == 63
    assert echo.clip_starts(62) == []
    assert echo.clip_starts(63) == [0]
    starts = echo.clip_starts(100)
    assert starts[0] == 0 and starts[-1] == 100 - 63 and all(b - a <= echo.TEST_STRIDE for a, b in zip(starts, starts[1:]))
    clip = echo.clip(video().frames, 5)
    assert clip.shape == (32, 112, 112, 3)


def test_normalise_gives_channel_first_float_clips():
    x = echo.normalise(echo.clip(video().frames, 0), np.array([30.0, 30.0, 30.0]), np.array([40.0, 40.0, 40.0]))
    assert x.shape == (3, 32, 112, 112) and x.dtype == np.float32


@pytest.mark.parametrize("kwargs,message", [
    ({"size": 224}, "112 x 112"),
    ({"frames": 40}, "at least 63"),
    ({"fps": 240.0}, "frames per second"),
    ({"colour": True}, "coloured"),
])
def test_videos_outside_the_development_format_are_refused_not_resized(kwargs, message):
    with pytest.raises(echo.EchoInputError, match=message):
        echo.check_video(video(**kwargs), ENVELOPE)


def test_a_development_format_video_passes_with_its_facts():
    facts = echo.check_video(video(), ENVELOPE)
    assert facts["frames"] == 100 and facts["size"] == [112, 112] and facts["clips"] == len(echo.clip_starts(100))


def test_bands_follow_the_universal_heart_failure_definition():
    assert "reduced" in echo.interpretation(35.0) and "mildly reduced" in echo.interpretation(45.0)
    assert "preserved" in echo.interpretation(60.0) and echo.interpretation(float("nan")) is None


def _served_echo_model():
    from app.services import model_inference

    try:
        return model_inference.get_model("echonet_ef_r2plus1d")
    except model_inference.InferenceNotPermitted:
        pytest.skip("EchoNet model not registered or not runnable here")


def _write_video(path: Path, size: int, frames: int = 80) -> None:
    import cv2

    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 50.0, (size, size))
    rng = np.random.default_rng(1)
    for _ in range(frames):
        writer.write(rng.integers(0, 120, size=(size, size, 3), dtype=np.uint8))
    writer.release()


def test_served_echo_model_estimates_ef_on_a_public_test_video_and_refuses_other_formats(client, test_users, tmp_path):
    model = _served_echo_model()
    manifest = ROOT / model["artifact_bundle"]["split_manifest_path"]
    with manifest.open(encoding="utf-8", newline="") as handle:
        row = next((r for r in csv.DictReader(handle) if r["split"] == "test" and int(r["frames"]) >= 100), None)
    if row is None or not Path(row["path"]).is_file():
        pytest.skip("EchoNet test videos not available")
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", headers=headers, json={"pseudonymous_id": "SYNTHETIC-ECHO"}).json()["id"]

    def upload(name: str, data: bytes) -> int:
        response = client.post(f"/api/v1/cases/{case_id}/uploads", headers=headers, data={"deidentified": "true"}, files={"file": (name, data, "video/mp4")})
        assert response.status_code == 201, response.text
        return response.json()["id"]

    request = {"model_id": model["model_id"], "declared_input_type": "ECHO"}
    video_id = upload("public-echonet-test.mp4", Path(row["path"]).read_bytes())
    response = client.post(f"/api/v1/uploads/{video_id}/research-inference", headers=headers, json=request)
    assert response.status_code in (200, 201, 202), response.text
    body = response.json()
    run = body if "research_output" in body else client.get(f"/api/v1/research-inference/{body['queued_job']['result_ref']['run_id']}", headers=headers).json()
    output = run["research_output"]
    assert output["type"] == "regression" and 0 <= output["ef_percent"] <= 100 and len(output["clip_ef_percent"]) == len(echo.clip_starts(int(row["frames"])))
    assert output["input_content_check"]["distribution"]["status"] == "PASSED"
    wide = tmp_path / "wide.mp4"
    _write_video(wide, 224)
    refused = client.post(f"/api/v1/uploads/{upload('wide.mp4', wide.read_bytes())}/research-inference", headers=headers, json=request)
    assert refused.status_code in (400, 422) and "112 x 112" in refused.text, refused.text


def test_the_network_runs_on_a_clip_and_yields_stage_features():
    torch = pytest.importorskip("torch")
    network = echo.build_network()
    device = torch.device("cpu")
    result = echo.predict(network, video(frames=70), np.zeros(3, np.float32), np.ones(3, np.float32), device)
    assert len(result["clip_ef_percent"]) == len(echo.clip_starts(70)) and np.isfinite(result["ef_percent"])
    features = echo.clip_features(network, video(frames=70), np.zeros(3, np.float32), np.ones(3, np.float32), device)
    assert len(features) == 5 and features[0].shape == (11,)


def test_a_wrong_size_video_is_refused_on_its_first_frame(tmp_path):
    path = tmp_path / "wide.mp4"
    _write_video(path, 224, frames=5)
    with pytest.raises(echo.EchoInputError, match="112 x 112"):
        echo.read_video(path)
