#!/bin/sh
# Biomedical NLP runtime inside WSL (Ubuntu). Windows Smart App Control blocks
# spaCy's native extensions on the host, so scispaCy runs here instead.
# User-space only (no sudo): a pinned, checksum-verified uv provisions a
# standalone Python 3.12 venv under ~/.medtwin/venv-nlp. Model packages are the
# ones already downloaded and hash-locked on the Windows side.
set -eu
UV_VERSION="0.13.4"
PROJECT="${1:-/mnt/d/project}"
BASE="$HOME/.medtwin"
UV="$BASE/uv-$UV_VERSION/uv"
VENV="$BASE/venv-nlp"
mkdir -p "$BASE"

if [ ! -x "$UV" ]; then
  archive="uv-x86_64-unknown-linux-gnu.tar.gz"
  url="https://github.com/astral-sh/uv/releases/download/$UV_VERSION/$archive"
  tmp="$(mktemp -d)"
  curl -sSfL "$url" -o "$tmp/$archive"
  curl -sSfL "$url.sha256" -o "$tmp/$archive.sha256"
  (cd "$tmp" && sha256sum -c "$archive.sha256")
  mkdir -p "$BASE/uv-$UV_VERSION"
  tar -xzf "$tmp/$archive" -C "$BASE/uv-$UV_VERSION" --strip-components=1
  rm -rf "$tmp"
fi
"$UV" --version

[ -x "$VENV/bin/python" ] || "$UV" venv "$VENV" --python 3.12 --quiet
"$UV" pip install --python "$VENV/bin/python" --quiet -r "$PROJECT/backend/requirements-nlp.txt"
for model in en_core_sci_sm-0.5.4.tar.gz en_ner_bc5cdr_md-0.5.4.tar.gz; do
  "$UV" pip install --python "$VENV/bin/python" --quiet --no-deps "$PROJECT/_derived/nlp-models/$model"
done
"$VENV/bin/python" - <<'EOF'
import spacy, scispacy
for name in ("en_core_sci_sm", "en_ner_bc5cdr_md"):
    nlp = spacy.load(name)
    doc = nlp("Aspirin was given and no evidence of hepatitis was found.")
    print(name, nlp.meta.get("version"), "licence:", nlp.meta.get("license"), "labels:", sorted({e.label_ for e in doc.ents}), "entities:", len(doc.ents))
print("spacy", spacy.__version__, "scispacy", scispacy.__version__)
EOF
