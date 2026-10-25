"""Source revision of the running code, so recorded results can be tied to a commit."""

from __future__ import annotations

import os
import subprocess
from typing import Any, Optional

from app.config import PROJECT_ROOT


def _git(*args: str) -> Optional[str]:
    try:
        completed = subprocess.run(["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=5, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip()


def code_revision() -> dict[str, Any]:
    """The commit and whether tracked files differ from it.

    MEDTWIN_CODE_COMMIT takes precedence for deployments built without a .git
    directory; its working-tree state is then unknown (None)."""
    configured = os.getenv("MEDTWIN_CODE_COMMIT", "").strip()
    if configured:
        return {"commit": configured, "source": "MEDTWIN_CODE_COMMIT", "working_tree_clean": None}
    commit = _git("rev-parse", "HEAD")
    if not commit:
        return {"commit": None, "source": "NOT_RECORDED", "working_tree_clean": None}
    status = _git("status", "--porcelain", "--untracked-files=no")
    return {"commit": commit, "source": "git", "working_tree_clean": None if status is None else status == ""}
