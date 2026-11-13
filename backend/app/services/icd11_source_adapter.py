"""Native WHO reference adapter; no crosswalks or local-code relabelling.

Missing credentials, explicit release and operator terms acceptance fail closed.
Only reference IDs are sent to WHO; no case/query/report text is transmitted.
"""
from __future__ import annotations
import base64
import json
import os
import re
import urllib.request

AUTH = "https://icd.who.int/docs/icd-api/API-Authentication/"
TERMS = "https://icd.who.int/en/docs/icd11-license.pdf"


def status() -> dict:
    credentials = bool(os.getenv("WHO_ICD_CLIENT_ID") and os.getenv("WHO_ICD_CLIENT_SECRET"))
    release = os.getenv("WHO_ICD_RELEASE", "")
    pinned = bool(re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])", release))
    accepted = os.getenv("MEDTWIN_WHO_ICD_TERMS_ACCEPTED", "").lower() == "true"
    blockers = ([] if credentials else ["WHO_CLIENT_CREDENTIALS_MISSING"]) + ([] if pinned else ["WHO_RELEASE_NOT_PINNED"]) + ([] if accepted else ["WHO_TERMS_ACCEPTANCE_NOT_RECORDED"])
    return {"terminology": "ICD-11 MMS", "available": not blockers, "state": "NATIVE_REFERENCE_ADAPTER_CONFIGURED_NOT_CONNECTIVITY_VERIFIED" if not blockers else "NATIVE_REFERENCE_ADAPTER_UNCONFIGURED",
            "blockers": blockers, "release": release if pinned else None, "credential_values_exposed": False,
            "licence": "CC BY-ND 3.0 IGO; unchanged code/title/URI with attribution; commercial incorporation permitted subject to WHO terms",
            "crosswalk_mapping_available": False, "crosswalk_blocker": "WHO_SEPARATE_WRITTEN_AGREEMENT_REQUIRED_BY_SECTION_1_2_4_AND_NO_REVIEWED_CROSSWALK_SUPPLIED",
            "local_icd10cm_is_icd11": False, "sources": [AUTH, TERMS, "https://icd.who.int/docs/icd-api/APIDoc-Version2/", "https://www.who.int/about/policies/publishing/copyright"],
            "notice": "No WHO endorsement or clinical coding approval. Native WHO references are separate from ICD-10-CM and MedTwin concepts; no mapping is inferred."}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None


def _json(request) -> dict:
    if not request.full_url.startswith(("https://id.who.int/", "https://icdaccessmanagement.who.int/")): raise ValueError("WHO endpoint required")
    with urllib.request.build_opener(_NoRedirect()).open(request, timeout=10) as response:
        body = response.read(2_000_001)
        if len(body) > 2_000_000: raise ValueError("WHO response exceeds bound")
        result = json.loads(body)
        if not isinstance(result, dict): raise ValueError("WHO object response required")
        return result


def lookup(entity_id: str) -> dict:
    current = status()
    if not re.fullmatch(r"[0-9]{1,20}", entity_id): raise ValueError("A numeric WHO entity identifier is required")
    if not current["available"]: return {"status": "UNAVAILABLE", "source_status": current, "entity": None}
    # Authentication follows the primary WHO OAuth2 client-credentials contract.
    authorization = base64.b64encode((os.environ["WHO_ICD_CLIENT_ID"] + ":" + os.environ["WHO_ICD_CLIENT_SECRET"]).encode()).decode()
    try:
        token = _json(urllib.request.Request("https://icdaccessmanagement.who.int/connect/token", data=b"grant_type=client_credentials&scope=icdapi_access",
                      headers={"Authorization": "Basic " + authorization, "Content-Type": "application/x-www-form-urlencoded"}))
        bearer = token["access_token"]
        if not isinstance(bearer, str) or not bearer or any(c in bearer for c in "\r\n"): raise ValueError("Invalid token")
        url = f"https://id.who.int/icd/release/11/{current['release']}/mms/{entity_id}"
        entity = _json(urllib.request.Request(url, headers={"Authorization": "Bearer " + bearer, "API-Version": "v2", "Accept": "application/json", "Accept-Language": "en"}))
        title = entity.get("title", {})
        title = title.get("@value") if isinstance(title, dict) else title
        uri, code = entity.get("@id"), entity.get("code")
        if not (isinstance(title, str) and title and isinstance(code, str) and code and isinstance(uri, str) and uri.replace("http://", "https://", 1) == url):
            raise ValueError("MMS code, original title and WHO URI are all required")
        return {"status": "AVAILABLE_NATIVE_WHO_REFERENCE", "source_status": current,
                "entity": {"code": code, "title": title, "uri": uri, "release": current["release"], "classification": "ICD-11 MMS"},
                "attribution": "International Classification of Diseases, Eleventh Revision (ICD-11), World Health Organization; CC BY-ND 3.0 IGO",
                "local_crosswalk": None, "case_data_transmitted": False}
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "UNAVAILABLE", "source_status": current, "entity": None,
                "reason": "WHO_AUTHENTICATION_OR_REFERENCE_RESPONSE_UNAVAILABLE", "credential_values_exposed": False}
