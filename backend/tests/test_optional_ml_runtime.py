"""Native ML import refusal must not hide the independent document API."""
import os
import subprocess
import sys
import textwrap
from pathlib import Path


def test_application_reports_optional_native_ml_refusal_without_crashing(tmp_path):
    script = textwrap.dedent("""
        import importlib.abc
        import sys
        class RefusedTorch(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == 'torch':
                    raise OSError(4551, 'Synthetic application-control refusal')
        sys.meta_path.insert(0, RefusedTorch())
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as client:
            response = client.get('/api/v1/system/readiness')
            assert response.status_code == 200, response.text
            result = response.json()
            assert result['ready'] is True, result
            assert result['checks']['ml_runtime'] == {
                'ready': False, 'optional': True, 'status': 'UNAVAILABLE',
                'error_type': 'OSError', 'scope': 'API_PROCESS_IMPORT_ONLY'}
            health = client.get('/api/v1/system/health').json()
            assert health['cuda_available'] is False
            assert health['health_scope'] == 'API_AND_DATABASE_ONLY'
        print('OPTIONAL_NATIVE_REFUSAL_REPORTED')
    """)
    env = {
        **os.environ,
        "ENVIRONMENT": "test",
        "DATABASE_URL": f"sqlite:///{(tmp_path / 'isolated.db').as_posix()}",
        "UPLOAD_DIR": str(tmp_path / "uploads"),
        "DEV_SEED_ENABLED": "false",
        "MEDTWIN_STORAGE_ENCRYPTION": "off",
        "MEDTWIN_DB_ENCRYPTION": "off",
    }
    completed = subprocess.run(
        [sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert "OPTIONAL_NATIVE_REFUSAL_REPORTED" in completed.stdout
