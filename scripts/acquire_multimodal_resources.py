"""Reviewed image/text, image/tabular, localization and 2D/3D research resources.

--plan saves versioned public metadata and small model configuration files.
--run resumes verified artifact downloads and then the earlier CT download jobs.
No credentials, paid models, downloaded Python execution or model activation.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from acquire_public_datasets import ROOT, digest, download, now, read_url, write_json

MANIFEST = ROOT / "dataset_registry/multimodal_resources.json"
STATE = ROOT / "artifacts/downloads/multimodal_status.json"
PROVENANCE = ROOT / "artifacts/downloads/provenance/multimodal"
ROOTS = {"datasets": Path("C:/MedTwin_Datasets"), "models": ROOT / "artifacts/third_party"}
RESERVES = {"datasets": 60 * 1024**3, "models": 20 * 1024**3}
BIOMED = "microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224"


def api(url):
    return json.loads(read_url(url))


def snapshot(name, payload):
    write_json(PROVENANCE / name, payload)


def hf_files(repo, folder, selected):
    info = api(f"https://huggingface.co/api/models/{repo}")
    revision = info["sha"]
    tree = api(f"https://huggingface.co/api/models/{repo}/tree/{revision}?recursive=true&limit=1000")
    snapshot(folder + "/model-metadata.json", info)
    items = []
    for item in tree:
        name = item["path"]
        if item["type"] != "file" or name not in selected:
            continue
        url = f"https://huggingface.co/{repo}/resolve/{revision}/{name}"
        if item.get("lfs"):
            checksum = item["lfs"]["oid"]
        else:
            data = read_url(url)
            blob = b"blob " + str(len(data)).encode() + b"\0" + data
            if hashlib.sha1(blob).hexdigest() != item["oid"]:
                raise ValueError(f"Pinned Git blob differs: {repo}/{name}")
            checksum = hashlib.sha256(data).hexdigest()
            target = ROOTS["models"] / folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_bytes() != data:
                raise ValueError(f"Refusing to overwrite a different model configuration: {target}")
            target.write_bytes(data)
        items.append({"resource": "biomedclip", "root": "models", "relative_path": f"{folder}/{name}",
                      "url": url, "bytes": item["size"], "hash_algorithm": "sha256", "hash": checksum,
                      "source_revision": revision, "source_git_oid": item["oid"]})
    if not selected.issubset({Path(i["relative_path"]).name for i in items}):
        raise ValueError(f"Required files missing from {repo}")
    return items, revision


def kaggle(ref, resource, relative, expected_license):
    metadata = api("https://www.kaggle.com/api/v1/datasets/view/" + ref)
    if metadata["licenseName"] != expected_license:
        raise ValueError(f"Kaggle source licence changed: {ref}")
    snapshot(resource + "/kaggle-metadata.json", metadata)
    version = metadata["currentVersionNumber"]
    url = f"https://www.kaggle.com/api/v1/datasets/download/{ref}?datasetVersionNumber={version}"
    # Kaggle's download endpoint supports GET, not HEAD. Read only the header/magic here.
    with urllib.request.urlopen(url, timeout=60) as response:
        size = int(response.headers["Content-Length"])
        checksum = re.search(r"(?:^|,)\s*crc32c=([^,\s]+)", response.headers.get("x-goog-hash", ""))
        if not checksum or response.read(4) != b"PK\x03\x04":
            raise ValueError(f"Expected a public ZIP with a Google Storage CRC32C: {ref}")
        expected = base64.b64decode(checksum.group(1)).hex()
    return {"resource": resource, "root": "datasets", "relative_path": relative, "url": url,
            "bytes": size, "hash_algorithm": "crc32c", "hash": expected,
            "integrity_source": "Google Storage x-goog-hash CRC32C over the compressed ZIP; local SHA-256 recorded after transfer",
            "dataset_version": version}


def osf_page(url):
    while url:
        page = api(url)
        yield from page["data"]
        url = page.get("links", {}).get("next")


def plan():
    items = []
    node = api("https://api.osf.io/v2/nodes/89kps/")
    licence_url = node["data"]["relationships"]["license"]["links"]["related"]["href"]
    licence = api(licence_url)
    if licence["data"]["attributes"]["name"] != "CC0 1.0 Universal":
        raise ValueError("VQA-RAD licence changed")
    snapshot("vqa-rad/node.json", node)
    snapshot("vqa-rad/license.json", licence)
    listing = list(osf_page("https://api.osf.io/v2/nodes/89kps/files/osfstorage/?page[size]=100"))
    folder = next(x for x in listing if x["attributes"]["name"] == "VQA_RAD Image Folder")
    images_url = folder["relationships"]["files"]["links"]["related"]["href"] + "?page[size]=100"
    images = list(osf_page(images_url))
    selected = [x for x in listing if x["attributes"]["name"] in ("VQA_RAD Dataset Public.json", "Readme.docx")]
    selected += images
    snapshot("vqa-rad/files.json", selected)
    for entry in selected:
        attr = entry["attributes"]
        if attr["kind"] != "file":
            raise ValueError("Unexpected nested VQA-RAD directory")
        name = attr["name"]
        if Path(name).name != name:
            raise ValueError("Unsafe OSF filename")
        relative = f"VQA_RAD/images/{name}" if entry in images else f"VQA_RAD/{name}"
        items.append({"resource": "vqa-rad", "root": "datasets", "relative_path": relative,
                      "url": entry["links"]["download"], "bytes": attr["size"], "hash_algorithm": "sha256",
                      "hash": attr["extra"]["hashes"]["sha256"], "file_version": attr["current_version"]})
    items.append(kaggle("mahdavi1202/skin-cancer", "pad-ufes-20", "PAD_UFES20/pad-ufes20-v1.zip",
                        "Attribution 4.0 International (CC BY 4.0)"))
    items.append(kaggle("awsaf49/cbis-ddsm-breast-cancer-image-dataset", "cbis-ddsm", "CBIS_DDSM/cbis-ddsm-v1.zip", "CC BY-SA 3.0"))
    model_items, revision = hf_files(BIOMED, "biomedclip", {"open_clip_config.json", "open_clip_pytorch_model.bin",
                                                         "LICENSE.md", "README.md", "tokenizer.json", "tokenizer_config.json",
                                                         "special_tokens_map.json", "vocab.txt"})
    items += model_items
    model_config = json.loads((ROOTS["models"] / "biomedclip/open_clip_config.json").read_text())
    bert = model_config["model_cfg"]["text_cfg"]["hf_model_name"]
    config_items, bert_revision = hf_files(bert, "biomedclip/text_encoder", {"config.json"})
    items += config_items
    resources = [
        {"id": "pad-ufes-20", "purpose": "2D clinical image + patient/lesion attributes for image/tabular fusion",
         "source": "https://data.mendeley.com/datasets/zr7vgbcyr2/1", "mirror": "https://www.kaggle.com/datasets/mahdavi1202/skin-cancer",
         "licence": "CC BY 4.0", "scope": "2,298 clinical skin images; patient and lesion IDs; six diagnoses; no lesion masks or 3D geometry",
         "limitations": "Publisher download endpoints returned 403; the public Kaggle copy carries matching attribution terms. Verify original counts/joins before training; split by patient, not image. This is the original PAD-UFES-20, not restricted PAD-UFES-20+."},
        {"id": "vqa-rad", "purpose": "paired radiology image/question/answer fusion benchmark",
         "source": "https://osf.io/89kps/", "licence": "CC0 1.0 Universal (OSF project licence)", "images": len(images),
         "limitations": "2D published teaching images; not DICOM volumes or an outcome-linked longitudinal report corpus. Group identical images across question splits; patient independence is not established."},
        {"id": "cbis-ddsm", "purpose": "2D mammography classification, clinical-table fusion and lesion localization data",
         "source": "https://www.kaggle.com/datasets/awsaf49/cbis-ddsm-breast-cancer-image-dataset", "licence": "CC BY-SA 3.0 (Kaggle distribution); retain original TCIA attribution and terms",
         "limitations": "JPEG conversion of CBIS-DDSM, not native CT/MRI or 3D mammography. Verify full/crop/ROI coordinate correspondence and patient disjointness before detection training."},
        {"id": "biomedclip", "purpose": "paired biomedical image/text feature encoder for research fusion and retrieval",
         "source": "https://huggingface.co/" + BIOMED, "licence": "MIT", "revision": revision, "text_config_revision": bert_revision,
         "limitations": "Downloaded weights are not an activated MedTwin model, a lesion detector, or clinical validation. Local research initialization/feature checks are separate from task-specific training."}]
    result = {"schema_version": 1, "planned_at": now(), "authorization": "Owner requested suitable multimodal, 2D training/localization and 2D/3D resources on 2026-11-07.",
              "roots": {k: str(v) for k, v in ROOTS.items()}, "reserve_bytes": RESERVES,
              "resources": resources, "artifacts": items,
              "existing_reuse": ["PTB-XL ECG + age/sex and the existing fusion model", "Kvasir/GastroVision and ARCADE", "fracture detection and MURA",
                                 "ISLES multi-channel MRI", "MSD BrainTumour multi-channel MRI", "ACDC", "KiTS19 acquisition", "LIDC and CQ500 CT", "MSD liver/pancreas"],
              "not_automatically_acquired": ["Credentialed MIMIC image/report/EHR data and VinDr; no unofficial access bypass",
                                              "Unlicensed or activation-required model checkpoints",
                                              "Arbitrary standalone 2D images as ground-truth 3D anatomy; geometry or paired projection/volume labels are required"]}
    write_json(MANIFEST, result)
    print(json.dumps({"artifacts": len(items), "bytes": sum(i["bytes"] for i in items), "vqa_images": len(images), "manifest": str(MANIFEST)}), flush=True)


def resume_prior_ct_jobs(state):
    import psutil
    jobs = [("lidc_download.cmd", "lidc_download", 25), ("cq500_download.cmd", "cq500_download", 35),
            ("liver_download.cmd", "Task03_Liver.tar", 14)]
    state.setdefault("prior_ct_jobs", {})
    for script, marker, allowance_gib in jobs:
        running = []
        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                if marker.lower() in " ".join(proc.info["cmdline"] or []).lower():
                    running.append(proc.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if running:
            state["prior_ct_jobs"][script] = {"status": "ALREADY_RUNNING", "pids": running}
            continue
        if shutil.disk_usage(ROOTS["datasets"]).free < RESERVES["datasets"] + allowance_gib * 1024**3:
            state["prior_ct_jobs"][script] = {"status": "DEFERRED_STORAGE", "required_headroom_gib": allowance_gib}
            continue
        path = ROOT / "artifacts/training/resumable" / script
        print(f"Resuming prior CT download: {script}", flush=True)
        state["prior_ct_jobs"][script] = {"status": "RUNNING"}
        write_json(STATE, state)
        completed = subprocess.run(["cmd.exe", "/d", "/c", str(path)], cwd=ROOT, creationflags=subprocess.CREATE_NO_WINDOW)
        # Exit status alone does not prove these older downloaders verified every case.
        state["prior_ct_jobs"][script] = {"status": "EXITED_REQUIRES_LOG_REVIEW", "exit_code": completed.returncode}
        write_json(STATE, state)


def run(resume_existing):
    import msvcrt
    manifest = json.loads(MANIFEST.read_text())
    STATE.parent.mkdir(parents=True, exist_ok=True)
    lock = (STATE.parent / "multimodal_acquisition.lock").open("a+b")
    lock.seek(0)
    if not lock.read(1):
        lock.write(b"0")
        lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print("A multimodal acquisition worker is already running.", flush=True)
        return 2
    state = json.loads(STATE.read_text()) if STATE.exists() else {"items": {}}
    state.update(status="RUNNING", pid=os.getpid(), started_at=now())
    failures = 0
    # Small files first, then the encoder, then the two larger Kaggle archives.
    items = sorted(manifest["artifacts"], key=lambda i: (i["resource"] in ("pad-ufes-20", "cbis-ddsm"), i["bytes"]))
    try:
        # OSF's small teaching images are independent. Four transfers avoid a long
        # sequence of redirect/connection setup delays without parallelizing large archives.
        small = [item for item in items if item["bytes"] <= 2 * 1024**2]
        state.update(current="Verifying/downloading small files with four transfers", updated_at=now())
        write_json(STATE, state)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(download, item, Path(manifest["roots"][item["root"]]),
                                   manifest["reserve_bytes"][item["root"]]): item for item in small}
            for future in as_completed(futures):
                item = futures[future]
                key = item["root"] + ":" + item["relative_path"]
                try:
                    status = future.result()
                    target = Path(manifest["roots"][item["root"]]) / item["relative_path"]
                    state["items"][key] = {"status": status, "bytes": item["bytes"], "publisher_checksum": item["hash"],
                                           "checksum_algorithm": item["hash_algorithm"], "sha256": digest(target), "verified_at": now()}
                    print(f"Small file {key} {status}", flush=True)
                except Exception as exc:
                    # The sequential loop retries failed small files once after this batch.
                    state["items"][key] = {"status": "RETRY_PENDING", "error": str(exc), "updated_at": now()}
                state["updated_at"] = now()
                write_json(STATE, state)
        for index, item in enumerate(items, 1):
            key = item["root"] + ":" + item["relative_path"]
            if item in small and state["items"].get(key, {}).get("status") in ("VERIFIED_PRESENT", "DOWNLOADED_VERIFIED"):
                continue
            state.update(current=key, updated_at=now())
            write_json(STATE, state)
            root = Path(manifest["roots"][item["root"]])
            root.mkdir(parents=True, exist_ok=True)
            print(f"{index}/{len(items)} {key} starting", flush=True)
            try:
                status = download(item, root, manifest["reserve_bytes"][item["root"]])
                target = root / item["relative_path"]
                state["items"][key] = {"status": status, "bytes": item["bytes"], "publisher_checksum": item["hash"],
                                       "checksum_algorithm": item["hash_algorithm"], "sha256": digest(target), "verified_at": now()}
                print(f"{index}/{len(items)} {key} {status}", flush=True)
                if item["resource"] == "biomedclip" and item["relative_path"].endswith("open_clip_pytorch_model.bin"):
                    checked = subprocess.run([sys.executable, str(ROOT / "scripts/verify_multimodal_stack.py"), "--require-pretrained"], cwd=ROOT)
                    state["encoder_verification"] = {"status": "PASSED" if checked.returncode == 0 else "FAILED_REQUIRES_REVIEW",
                                                       "exit_code": checked.returncode, "checked_at": now()}
            except Exception as exc:
                failures += 1
                state["items"][key] = {"status": "FAILED", "error": str(exc), "updated_at": now()}
                print(f"{key} FAILED: {exc}", flush=True)
                if isinstance(exc, OSError):
                    state["status"] = "PAUSED_STORAGE_OR_IO"
                    break
            write_json(STATE, state)
        else:
            state["status"] = "ARTIFACTS_COMPLETE" if not failures else "INCOMPLETE_WITH_FAILURES"
            if not failures:
                prepared = subprocess.run([sys.executable, str(ROOT / "scripts/prepare_multimodal_resources.py")], cwd=ROOT)
                state["preparation"] = {"status": "PASSED" if prepared.returncode == 0 else "FAILED_REQUIRES_REVIEW",
                                         "exit_code": prepared.returncode, "checked_at": now()}
            if resume_existing:
                resume_prior_ct_jobs(state)
            if not failures:
                state["status"] = "COMPLETE_REVIEW_PRIOR_CT_LOGS" if resume_existing else "ARTIFACTS_COMPLETE"
    finally:
        state["updated_at"] = now()
        write_json(STATE, state)
        lock.close()
    return 0 if state["status"] in ("ARTIFACTS_COMPLETE", "COMPLETE_REVIEW_PRIOR_CT_LOGS") else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--resume-existing", action="store_true", help="after the new resources, resume the earlier CT download scripts, subject to space")
    args = parser.parse_args()
    if args.plan:
        plan()
    return run(args.resume_existing) if args.run else 0


if __name__ == "__main__":
    sys.exit(main())
