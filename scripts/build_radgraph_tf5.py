"""Build a traceable local RadGraph fork for Transformers 5 without editing upstream.

Patches tokenizer calls and special-token assembly, safe checkpoint loading,
safe TAR extraction and the local version. Installing it does not authorize clinical use.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.18+medtwin.tf5.2"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(source, destination, reuse=False):
    source, destination = source.resolve(), destination.resolve()
    destination.relative_to((ROOT / "_derived/vendor").resolve())
    if destination.exists():
        if reuse:
            record = json.loads((destination / "medtwin-build.json").read_text())
            if record["version"] != VERSION:
                raise ValueError("Existing build version differs")
            for relative, expected in record["build_files"].items():
                if not (destination / relative).is_file() or digest(destination / relative) != expected:
                    raise ValueError(f"Existing build was changed: {relative}")
            actual = {p.relative_to(destination).as_posix() for p in (destination / "radgraph").rglob("*.py")}
            expected = {name for name in record["build_files"] if name.startswith("radgraph/") and name.endswith(".py")}
            if actual != expected:
                raise ValueError("Existing build has unexpected Python modules")
            return record
        raise ValueError("Build destination already exists; preserve it and choose a new destination")
    destination.mkdir(parents=True)
    shutil.copytree(source / "radgraph", destination / "radgraph", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("setup.py", "README.md", "LICENSE", "LICENSE.txt"):
        if (source / name).is_file():
            shutil.copy2(source / name, destination / name)
    changes = {}
    def patch(relative, old, new, expected=1):
        path = destination / relative
        text = path.read_text(encoding="utf-8")
        if text.count(old) != expected:
            raise ValueError(f"Unexpected upstream source for {relative}: patch count changed")
        before = digest(path)
        path.write_text(text.replace(old, new), encoding="utf-8")
        changes.setdefault(relative, {"upstream_sha256": before})["patched_sha256"] = digest(path)
    patch("setup.py", 'version="0.1.18"', f'version="{VERSION}"')
    patch("radgraph/allennlp/data/tokenizers/pretrained_transformer_tokenizer.py", ".encode_plus(", "(", 4)
    patch("radgraph/allennlp/data/token_indexers/pretrained_transformer_indexer.py",
          "self._tokenizer.build_inputs_with_special_tokens(segment)",
          "([token.text_id for token in self._allennlp_tokenizer.single_sequence_start_tokens] + segment + [token.text_id for token in self._allennlp_tokenizer.single_sequence_end_tokens])")
    patch("radgraph/radgraph.py", "model_state = torch.load(model_state_path)", "model_state = torch.load(model_state_path, map_location=self.device, weights_only=True)")
    patch("radgraph/radgraph.py", "tar.extractall(path=model_dir)", 'tar.extractall(path=model_dir, filter="data")')
    inventory = {p.relative_to(destination).as_posix(): digest(p) for p in destination.rglob("*") if p.is_file()}
    record = {"version": VERSION, "upstream": "https://github.com/Stanford-AIMI/radgraph", "source": str(source),
              "changes": changes, "build_files": inventory, "scope": "Local compatibility fork; not a clinical validation or commercial-rights approval"}
    (destination / "medtwin-build.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "radgraph-master")
    parser.add_argument("--destination", type=Path, default=ROOT / "_derived/vendor/radgraph-tf5-v2")
    parser.add_argument("--reuse-if-verified", action="store_true")
    args = parser.parse_args()
    record = build(args.source, args.destination, args.reuse_if_verified)
    print(json.dumps({"version": record["version"], "destination": str(args.destination), "changed_files": list(record["changes"])}))
