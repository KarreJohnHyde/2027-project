import hashlib
import importlib.util
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("acquisition", Path(__file__).parents[1] / "acquire_public_datasets.py")
acquisition = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acquisition)


@pytest.fixture
def publisher():
    payload = bytes(range(256)) * 1000
    ranges = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            start = int(self.headers.get("Range", "bytes=0-").split("=")[1].split("-")[0])
            ranges.append(start)
            self.send_response(206 if start else 200)
            self.send_header("Content-Length", str(len(payload) - start))
            if start:
                self.send_header("Content-Range", f"bytes {start}-{len(payload)-1}/{len(payload)}")
            self.end_headers()
            self.wfile.write(payload[start:])

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    item = {"relative_path": "dataset/image.bin", "url": f"http://127.0.0.1:{server.server_port}/image.bin",
            "bytes": len(payload), "hash_algorithm": "sha256", "hash": hashlib.sha256(payload).hexdigest()}
    yield payload, ranges, item
    server.shutdown()
    server.server_close()
    thread.join()


def test_resumes_partial_and_verifies_hash(tmp_path, publisher):
    payload, ranges, item = publisher
    part = tmp_path / "dataset/image.bin.part"
    part.parent.mkdir()
    part.write_bytes(payload[:10000])
    assert acquisition.download(item, tmp_path, reserve=0) == "DOWNLOADED_VERIFIED"
    assert ranges == [10000]
    assert part.with_suffix("").read_bytes() == payload
    assert not part.exists()
    assert acquisition.download(item, tmp_path, reserve=0) == "VERIFIED_PRESENT"
    assert ranges == [10000]


def test_corrupt_download_never_becomes_final(tmp_path, publisher):
    _, _, item = publisher
    item["hash"] = "0" * 64
    with pytest.raises(ValueError, match="hash/size mismatch"):
        acquisition.download(item, tmp_path, reserve=0)
    assert not (tmp_path / item["relative_path"]).exists()
    assert list((tmp_path / "dataset").glob("*.invalid-*"))


def test_wrong_existing_file_is_preserved(tmp_path, publisher):
    _, ranges, item = publisher
    target = tmp_path / item["relative_path"]
    target.parent.mkdir()
    target.write_bytes(b"existing data")
    with pytest.raises(ValueError, match="Existing final file differs"):
        acquisition.download(item, tmp_path, reserve=0)
    assert target.read_bytes() == b"existing data"
    assert ranges == []


def test_disk_reserve_stops_before_transfer(tmp_path, publisher):
    _, ranges, item = publisher
    with pytest.raises(OSError, match="Disk reserve"):
        acquisition.download(item, tmp_path, reserve=10**20)
    assert ranges == []


def test_manifest_cannot_escape_destination(tmp_path, publisher):
    _, ranges, item = publisher
    item["relative_path"] = "../outside.bin"
    with pytest.raises(ValueError):
        acquisition.download(item, tmp_path, reserve=0)
    assert ranges == []
