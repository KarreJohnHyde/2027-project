"""Release gate: no patient identifiers or credentials in tracked/untracked files or build output.

The history check is separate (scripts/privacy_scan.py --history and the pre-push
guard), because history still holds the blob described in
docs/security/PHI_RELEASE_BLOCKER.md until an authorized purge."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNER = ROOT / "scripts" / "privacy_scan.py"


def test_release_scope_has_no_identifier_or_credential_findings():
    command = [sys.executable, "-I", str(SCANNER), "--tree"]
    if (ROOT / "dist").exists():
        command += ["--paths", str(ROOT / "dist")]
    result = subprocess.run(command, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout[-3000:]


def test_scanner_detects_identifiers_without_printing_them(tmp_path):
    # Built at runtime so this file itself contains no matching literal.
    name_field = '"patient' + '_name": "Fixture ' + 'Person"'
    report_id = "ZZ-" + "LAB-" + "2024-0001"
    sample = tmp_path / "leak.json"
    sample.write_text("{" + name_field + ', "report_id": "' + report_id + '"}\n', encoding="utf-8")
    result = subprocess.run([sys.executable, "-I", str(SCANNER), "--paths", str(sample), "--allowlist", ""],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 1
    assert "PATIENT_NAME_FIELD" in result.stdout and "LAB_REPORT_ID" in result.stdout
    assert "Fixture Person" not in result.stdout and report_id not in result.stdout
