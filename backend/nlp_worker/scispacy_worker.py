"""scispaCy entity worker, run inside the isolated NLP environment (WSL venv-nlp).

Reads {"text": str, "models": [str, ...]} as JSON on stdin and writes
{"models": [{"name", "version", "spacy_version"}], "entities": [{"model", "label",
"start", "end", "text"}]} to stdout. It performs no network access and keeps nothing.
Kept free of MedTwin imports: the NLP environment has spaCy, not the backend stack.
"""

import json
import sys


def main() -> int:
    request = json.load(sys.stdin)
    import spacy

    text = request["text"]
    models, entities = [], []
    for name in request["models"]:
        nlp = spacy.load(name)
        # Entities need only the NER pipe; the parser and lemmatizer just cost time.
        nlp.select_pipes(disable=[pipe for pipe in ("parser", "lemmatizer") if pipe in nlp.pipe_names])
        models.append({"name": name, "version": nlp.meta.get("version"), "spacy_version": spacy.__version__})
        for ent in nlp(text).ents:
            entities.append({"model": name, "label": ent.label_, "start": ent.start_char, "end": ent.end_char, "text": ent.text})
    json.dump({"models": models, "entities": entities}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
