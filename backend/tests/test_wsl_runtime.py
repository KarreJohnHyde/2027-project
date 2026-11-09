"""WSL tool plumbing: shell quoting of configured paths, report text kept out of errors, malformed replies."""

from pathlib import Path

import pytest

from app.services import wsl_runtime


def test_paths_are_quoted_and_home_still_expands():
    script = wsl_runtime.command("~/.medtwin/venv nlp/bin/python; rm -rf x", Path("D:/project/backend/nlp_worker/w's.py"))[-1]
    assert script.startswith('"$HOME"/')
    assert "'.medtwin/venv nlp/bin/python; rm -rf x'" in script, "metacharacters stay inside one quoted word"
    assert script.endswith("'/mnt/d/project/backend/nlp_worker/w'\"'\"'s.py'")


def test_failure_summary_keeps_only_the_exception_type():
    stderr = "Traceback (most recent call last):\nValueError: [E1010] Unable to set entity information for 'pleural effusion'"
    assert wsl_runtime.failure_summary(1, stderr) == "exited with 1 (ValueError)"
    assert "pleural" not in wsl_runtime.failure_summary(1, "the patient's pleural effusion")


def test_malformed_replies_raise_value_error():
    for reply in ("", "loading model...", "[1, 2]", '{"tools": {}}'):
        with pytest.raises(ValueError):
            wsl_runtime.parse_payload(reply, ("tools", "context"))
    assert wsl_runtime.parse_payload('{"tools": {}, "context": []}', ("tools", "context")) == {"tools": {}, "context": []}
