"""Offline software checks for the optional fusion and 2D/3D research stack.

Synthetic inputs prove execution only. No clinical predictions or validation claims.
--require-pretrained additionally requires the verified local BiomedCLIP checkpoint.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from importlib.metadata import distributions, version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify(require_pretrained=False):
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import numpy as np
    import torch
    import torchio as tio
    import kornia
    import highdicom
    import trimesh
    from PIL import Image
    from skimage.measure import marching_cubes
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, JPEG2000Lossless, JPEGLSLossless
    from diffdrr.data import read
    from diffdrr.drr import DRR
    import open_clip

    before = {}
    for line in (ROOT / "artifacts/audits/installed-after-2026-11-07.txt").read_text().splitlines():
        name, old = line.split("==", 1)
        before[name] = old
    changed = {name: {"before": old, "after": version(name)} for name, old in before.items() if version(name) != old}
    assert not changed, changed
    device = "cuda" if torch.cuda.is_available() else "cpu"
    image = torch.rand(1, 1, 32, 32, device=device)
    warped = kornia.geometry.transform.warp_perspective(image, torch.eye(3, device=device)[None], (32, 32))
    assert torch.allclose(warped, image, atol=1e-4)
    to_reference = highdicom.spatial.PixelToReferenceTransformer(
        image_position=[10.0, 20.0, 30.0], image_orientation=[1.0, 0.0, 0.0, 0.0, 1.0, 0.0], pixel_spacing=[0.7, 0.8])
    reference_points = to_reference(np.array([[0, 0], [5, 6]]))
    assert np.allclose(reference_points, [[10, 20, 30], [14, 24.2, 30]])

    grid = np.indices((20, 20, 20)).astype(np.float32)
    sphere = ((grid - 9.5) ** 2).sum(0) < 25
    affine = np.diag([1.0, 2.0, 3.0, 1.0])
    subject = tio.Subject(image=tio.ScalarImage(tensor=torch.tensor(sphere, dtype=torch.float32)[None], affine=affine),
                          label=tio.LabelMap(tensor=torch.tensor(sphere, dtype=torch.uint8)[None], affine=affine))
    resampled = tio.Resample(2)(subject)
    assert np.allclose(resampled.image.spacing, (2, 2, 2))
    assert set(torch.unique(resampled.label.data).tolist()) <= {0, 1}
    vertices, faces, _, _ = marching_cubes(sphere.astype(np.float32), level=0.5, spacing=(1, 2, 3))
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    glb = mesh.export(file_type="glb")
    assert glb[:4] == b"glTF" and len(mesh.faces) > 0

    pixels = np.arange(64 * 64, dtype=np.uint16).reshape(64, 64)
    codec_checks = []
    for syntax in (JPEGLSLossless, JPEG2000Lossless):
        ds = Dataset()
        ds.file_meta = FileMetaDataset()
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.Rows, ds.Columns = pixels.shape
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.BitsAllocated = ds.BitsStored = 16
        ds.HighBit = 15
        ds.PixelRepresentation = 0
        ds.PixelData = pixels.tobytes()
        ds.compress(syntax)
        ds.decompress()
        assert np.array_equal(ds.pixel_array, pixels)
        codec_checks.append(syntax.name)

    ct = np.full((20, 20, 20), -1000, dtype=np.float32)
    ct[sphere] = 50
    ct[7:13, 7:13, 7:13] = 500
    ct[8:12, 8:12, 8:12] = 1200
    ct_subject = read(tio.ScalarImage(tensor=torch.tensor(ct)[None], affine=np.eye(4)), orientation="AP")
    renderer = DRR(ct_subject, sdd=1020, height=32, delx=2, renderer="trilinear").to(device)
    rotations = torch.tensor([[torch.pi / 2 + 0.01, 0.02, 0.03]], device=device, requires_grad=True)
    translations = torch.tensor([[0.0, 850.0, 0.0]], device=device, requires_grad=True)
    projection = renderer(rotations, translations, parameterization="euler_angles", convention="ZXY")
    assert projection.shape == (1, 1, 32, 32) and torch.isfinite(projection).all()
    assert projection.max() > 0
    projection.square().mean().backward()
    assert rotations.grad is not None and torch.isfinite(rotations.grad).all()
    assert translations.grad is not None and torch.isfinite(translations.grad).all()

    folder = ROOT / "artifacts/third_party/biomedclip"
    checkpoint = folder / "open_clip_pytorch_model.bin"
    if require_pretrained and not checkpoint.is_file():
        raise FileNotFoundError("BiomedCLIP checkpoint is still downloading")
    configuration = json.loads((folder / "open_clip_config.json").read_text())
    cfg = copy.deepcopy(configuration["model_cfg"])
    cfg["text_cfg"].update(hf_model_name=str(folder / "text_encoder"), hf_tokenizer_name=str(folder), hf_model_pretrained=False)
    name = "medtwin_local_biomedclip"
    open_clip.factory._MODEL_CONFIGS[name] = cfg
    model, _, preprocess = open_clip.create_model_and_transforms(name, pretrained=str(checkpoint) if checkpoint.is_file() else None,
                                                               pretrained_hf=False, device=device)
    model.eval()
    tokenizer = open_clip.get_tokenizer(name)
    batch = preprocess(Image.new("RGB", (224, 224), (128, 128, 128)))[None].to(device)
    tokens = tokenizer(["a biomedical research image", "a research diagram"]).to(device)
    with torch.inference_mode():
        visual = model.encode_image(batch)
        textual = model.encode_text(tokens)
    assert visual.shape == (1, 512) and textual.shape == (2, 512)
    assert torch.isfinite(visual).all() and torch.isfinite(textual).all()
    selected = ["torchio", "kornia", "trimesh", "highdicom", "open-clip-torch", "pylibjpeg", "pylibjpeg-libjpeg",
                "pylibjpeg-openjpeg", "diffdrr", "google-crc32c"]
    result = {"scope": "synthetic execution checks only; no clinical validation", "device": device,
              "versions": {name: version(name) for name in selected}, "previous_packages_unchanged": len(before),
              "packages_in_environment": len(list(distributions())), "kornia_identity_warp": "PASS",
              "torchio_spacing_and_label_resampling": "PASS", "dicom_pixel_to_3d_reference": "PASS", "dicom_lossless_round_trips": codec_checks,
              "native_frame_mesh_glb": {"vertices": len(vertices), "faces": len(faces), "bytes": len(glb)},
              "diffdrr_projection_and_pose_gradients": {"shape": list(projection.shape), "status": "PASS"},
              "biomedclip": {"image_shape": list(visual.shape), "text_shape": list(textual.shape),
                             "pretrained_checkpoint_loaded": checkpoint.is_file(),
                             "status": "PRETRAINED_ENCODER_EXECUTED" if checkpoint.is_file() else "ARCHITECTURE_ONLY_PRETRAINED_DOWNLOAD_PENDING"}}
    output = ROOT / "artifacts/audits/multimodal-stack-2026-11-07.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-pretrained", action="store_true")
    verify(parser.parse_args().require_pretrained)
