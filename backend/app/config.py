"""
Configuration settings for MedTwin Research Framework.
Follows IEEE manuscript specification with environment variable overrides and safe defaults.
"""

import json
import os
import secrets
from pathlib import Path
from typing import List

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Application metadata
PROJECT_NAME: str = os.getenv("PROJECT_NAME", "MedTwin Research Framework")
VERSION: str = "0.2.0"
DESCRIPTION: str = (
    "Software-only multimodal clinical evidence research prototype with "
    "generic L1 anatomy and explicit validation gates."
)

# Runtime environment
ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development").strip().lower()
DEBUG: bool = os.getenv("DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}

# API Configuration
API_PREFIX: str = "/api/v1"

# Security & Authentication
_configured_secret = os.getenv("SECRET_KEY", "").strip()
if ENVIRONMENT in {"production", "staging"} and len(_configured_secret) < 32:
    raise RuntimeError("SECRET_KEY must contain at least 32 characters outside development/test environments.")
SECRET_KEY: str = _configured_secret or secrets.token_urlsafe(48)
ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24)))

# Development bootstrap is opt-in and fully environment controlled. No password is
# embedded in source or accepted as an authentication fallback.
DEV_SEED_ENABLED: bool = os.getenv("DEV_SEED_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
DEV_SEED_USERNAME: str = os.getenv("DEV_SEED_USERNAME", "").strip()
DEV_SEED_PASSWORD: str = os.getenv("DEV_SEED_PASSWORD", "")
DEV_SEED_EMAIL: str = os.getenv("DEV_SEED_EMAIL", "").strip()
DEV_SEED_FULL_NAME: str = os.getenv("DEV_SEED_FULL_NAME", "MedTwin Development User").strip()
DEV_SEED_ROLE: str = os.getenv("DEV_SEED_ROLE", "clinician").strip().lower()
DEV_SEED_CASE_ENABLED: bool = os.getenv("DEV_SEED_CASE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}

# Database Configuration
_configured_database_url = os.getenv("DATABASE_URL", "").strip()
if ENVIRONMENT == "test" and not _configured_database_url:
    raise RuntimeError("DATABASE_URL must be explicitly set when ENVIRONMENT=test.")
DATABASE_URL: str = _configured_database_url or f"sqlite:///{BASE_DIR / 'medtwin.db'}"

# File Storage & Limits
UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", os.getenv("UPLOAD_DIRECTORY", str(BASE_DIR / "uploads"))))
# Encryption at rest for stored uploads: "required" (refuse writes without a key),
# "auto" (encrypt when a key is configured) or "off". Keys: MEDTWIN_STORAGE_KEY_FILE
# or MEDTWIN_STORAGE_KEYS, never in the repository (see app/services/storage_crypto.py).
STORAGE_ENCRYPTION_MODE: str = os.getenv("MEDTWIN_STORAGE_ENCRYPTION", "auto").strip().lower()
if STORAGE_ENCRYPTION_MODE not in {"required", "auto", "off"}:
    raise ValueError("MEDTWIN_STORAGE_ENCRYPTION must be one of: required, auto, off.")
MAX_UPLOAD_SIZE_BYTES: int = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(25 * 1024 * 1024))) # 25 MB (reports, ECG)
MAX_IMAGE_UPLOAD_SIZE_BYTES: int = int(os.getenv("MAX_IMAGE_UPLOAD_SIZE_BYTES", str(512 * 1024 * 1024))) # volumes

ALLOWED_EXTENSIONS: set = {
    # Medical images and volumes
    ".png", ".jpg", ".jpeg", ".bmp", ".dcm", ".nii", ".nii.gz", ".nrrd", ".mha",
    # ECG records
    ".csv", ".dat", ".hea",
    # Clinical reports (JSON includes FHIR R4 resources)
    ".txt", ".json", ".pdf", ".docx", ".md", ".xlsx"
}

ALLOWED_MIME_TYPES: set = {
    "image/png",
    "image/jpeg",
    "image/bmp",
    "image/x-ms-bmp",
    "text/plain",
    "text/csv",
    "text/markdown",
    "application/json",
    "application/fhir+json",
    "application/pdf",
    "application/dicom",
    "application/gzip",
    "application/x-gzip",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/msword",
    "application/octet-stream",
}

# Rate limits (requests per minute per client) for sensitive endpoints.
RATE_LIMIT_LOGIN_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_LOGIN_PER_MINUTE", "10"))
RATE_LIMIT_UPLOAD_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_UPLOAD_PER_MINUTE", "60"))
RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}

# Anatomy manifests produced by tools/asset-pipeline.
# Repository root holding generated evidence (docs/, public/anatomy/, benchmarks/results/).
# Container images copy those files elsewhere and set MEDTWIN_PROJECT_ROOT.
PROJECT_ROOT: Path = Path(os.getenv("MEDTWIN_PROJECT_ROOT", str(BASE_DIR.parent)))
ANATOMY_MANIFEST_PATH: Path = Path(os.getenv("ANATOMY_MANIFEST_PATH", str(PROJECT_ROOT / "public" / "anatomy" / "manifest.json")))

def _cors_origins() -> List[str]:
    configured = os.getenv("CORS_ORIGINS", "").strip()
    if configured:
        try:
            parsed = json.loads(configured)
            if isinstance(parsed, list):
                return [str(origin).rstrip("/") for origin in parsed]
        except json.JSONDecodeError:
            return [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8443",
        "http://127.0.0.1:8443",
    ]


# CORS Configuration
CORS_ORIGINS: List[str] = _cors_origins()

# Medical & Algorithmic Parameters from IEEE Manuscript
# Held-out Target Registration Error (TRE) threshold in mm for L2 Anatomy Mapping Gate
TAU_TRE_THRESHOLD_DEFAULT: float = float(os.getenv("TAU_TRE_THRESHOLD_DEFAULT", "5.0"))

# Minimum observations required for longitudinal forecasting eligibility
L_MIN_OBSERVATIONS: int = int(os.getenv("L_MIN_OBSERVATIONS", "3"))

# Research Notice mandatory label
RESEARCH_ONLY_NOTICE: str = (
    "MEDTWIN IS A RESEARCH PROTOTYPE ONLY. NOT A VALIDATED DIAGNOSTIC DEVICE. "
    "ALL OUTPUTS ARE EXPERIMENTAL AND MUST BE CONFIRMED BY A QUALIFIED CLINICIAN."
)
