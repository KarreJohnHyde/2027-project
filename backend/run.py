"""
Development server runner for MedTwin Backend.
Usage:
    python run.py
Or:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""

import sys
from pathlib import Path
import uvicorn

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
