#!/bin/sh
# Clinical NLP runtime inside WSL (Ubuntu): medSpaCy (ConText, sections) and MedCAT (concept linking).
# Kept apart from venv-nlp: scispaCy 0.5.5 pins spaCy 3.7 / NumPy 1.26, while medSpaCy 1.3 on
# Python 3.12 needs spaCy 3.8 and MedCAT 2 needs NumPy 2. Both packages are installed from the
# source trees already in the project (medspacy-master, cogstack-nlp-main/medcat).
# User-space only (no sudo); reuses the checksum-verified uv from setup_nlp_wsl.sh.
#   wsl -d Ubuntu -- sh /mnt/d/project/scripts/setup_clinical_nlp_wsl.sh
set -eu
UV_VERSION="0.13.4"
PROJECT="${1:-/mnt/d/project}"
BASE="$HOME/.medtwin"
UV="$BASE/uv-$UV_VERSION/uv"
VENV="$BASE/venv-clinical"
[ -x "$UV" ] || { echo "run scripts/setup_nlp_wsl.sh first (it installs uv $UV_VERSION)"; exit 1; }

[ -x "$VENV/bin/python" ] || "$UV" venv "$VENV" --python 3.12 --quiet
"$UV" pip install --python "$VENV/bin/python" --quiet -r "$PROJECT/backend/requirements-clinical-nlp.txt"
# medSpaCy itself: its dependencies (including medspacy_quickumls) come from the requirements file above.
"$UV" pip install --python "$VENV/bin/python" --quiet --no-deps "$PROJECT/medspacy-master/medspacy-master"
# The MedCAT tree is a source download without Git tags, so setuptools-scm is told the release it is.
SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MEDCAT="2.3.0" \
  "$UV" pip install --python "$VENV/bin/python" --quiet --no-deps "$PROJECT/cogstack-nlp-main/medcat"
MEDCAT_DISABLE_VERSION_CHECK=true "$VENV/bin/python" - <<'EOF'
import medspacy, medcat, spacy
nlp = medspacy.load()
doc = nlp("There is no evidence of pneumonia.")
print("medspacy", medspacy.__version__, "pipes", nlp.pipe_names)
print("medcat", medcat.__version__, "spacy", spacy.__version__)
EOF
