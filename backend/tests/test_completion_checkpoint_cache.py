"""Registry-wide preflight must not rehash every unchanged artifact on each page."""
from app.services import model_inference


def test_registry_sized_walk_reuses_hashes_but_changed_artifact_is_rechecked(tmp_path, monkeypatch):
    paths = []
    calls = []
    original = model_inference._sha256
    def counted(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(model_inference, "_sha256", counted)
    model_inference._cached_hash.cache_clear()
    try:
        for n in range(40):
            path = tmp_path / f"artifact-{n}.bin"
            path.write_bytes(f"immutable checkpoint {n}".encode())
            paths.append(path)
        first = [model_inference._checkpoint_hash(path) for path in paths]
        assert [model_inference._checkpoint_hash(path) for path in paths] == first
        assert len(calls) == len(paths)
        paths[0].write_bytes(b"changed checkpoint, different byte size")
        assert model_inference._checkpoint_hash(paths[0]) != first[0]
        assert len(calls) == len(paths) + 1
    finally:
        model_inference._cached_hash.cache_clear()
