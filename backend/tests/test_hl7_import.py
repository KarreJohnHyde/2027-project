"""HL7 v2 observation-result import. The message below is synthetic: it carries no real
person, facility or identifier, and its patient segment exists only to prove it is not read."""

from app.services.hl7_import import is_hl7, render_hl7_text
from tests.conftest import get_auth_headers

MESSAGE = "\r".join([
    "MSH|^~\\&|SYNTH_LAB|SYNTH_SITE|MEDTWIN|MEDTWIN|20260203091500||ORU^R01|MSG0001|P|2.5.1",
    "PID|1||SYNTHETIC-PID-MARKER^^^SYNTH||SYNTHETICFAMILY^SYNTHETICGIVEN||19700101|U",
    "PV1|1|O|SYNTHETIC-WARD-MARKER",
    "ORC|RE||||||||||SYNTHETIC-ORDERER-MARKER",
    "OBR|1|||24323-8^Comprehensive metabolic panel^LN|||20260203080000",
    "OBX|1|NM|2160-0^Creatinine^LN||1.42|mg/dL^^UCUM|0.70-1.30|H|||F|||20260203080000",
    "OBX|2|NM|2823-3^Potassium^LN||4.1|mmol/L|3.5-5.1|N|||F",
    "OBX|3|SN|1988-5^C reactive protein^LN||<^0.5|mg/L|<5||||F",
    "OBX|4|NM|718-7^Hemoglobin^LN||9.9|g/dL|13.0-17.0|L|||X",
    "OBX|5|NM|99999-9^Local assay^LN||12|U/L|||||C",
    "OBX|6|SN|5767-9^Urine appearance ratio^LN||^1^:^4||||||F",
    "OBX|7|ST|11529-5^Pathology comment^LN||Biopsy reviewed.\\.br\\No evidence of malignancy.||||||F",
    "NTE|1||Specimen received intact \\T\\ labelled.",
])


def test_only_result_segments_are_rendered():
    assert is_hl7(MESSAGE.encode()) and not is_hl7(b"Creatinine 1.4 mg/dL")
    text = render_hl7_text(MESSAGE.encode())
    assert text.startswith("HL7 v2 ORU^R01 import")
    for marker in ("SYNTHETIC-PID-MARKER", "SYNTHETICFAMILY", "SYNTHETICGIVEN", "19700101", "SYNTHETIC-WARD-MARKER",
                   "SYNTHETIC-ORDERER-MARKER", "SYNTH_LAB", "SYNTH_SITE", "MSG0001"):
        assert marker not in text, marker
    assert "Observation Creatinine [2160-0]: 1.42 mg/dL (reference 0.70-1.30) effective 2026-02-03 interpretation H" in text
    assert "Observation Hemoglobin [718-7]: 9.9 g/dL (reference 13.0-17.0) effective 2026-02-03 interpretation L status cannot be obtained" in text
    assert "Biopsy reviewed.\nNo evidence of malignancy." in text
    assert "Comment: Specimen received intact & labelled." in text


def test_oru_upload_imports_coded_results_and_reads_comments(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": "CASE-HL7"}, headers=headers).json()["id"]
    upload = client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": ("results.hl7", MESSAGE.encode(), "application/hl7-v2")},
                         data={"deidentified": "true"}, headers=headers)
    assert upload.status_code == 201, upload.text
    assert upload.json()["modality"] == "REPORT"
    assert client.post(f"/api/v1/uploads/{upload.json()['id']}/analysis-jobs", headers=headers).status_code == 201
    measurements = {item["name"]: item for item in client.get(f"/api/v1/cases/{case_id}/measurements", headers=headers).json()}
    creatinine = measurements["creatinine"]
    assert (creatinine["value"], creatinine["unit"], creatinine["canonical_code"]) == (1.42, "mg/dL", "2160-0")
    assert (creatinine["reference_low"], creatinine["reference_high"], creatinine["documented_flag"]) == (0.7, 1.3, "HIGH")
    assert creatinine["documented_date"] == "2026-02-03" and creatinine["extraction_method"] == "HL7_V2_OBX_IMPORT"
    assert measurements["potassium"]["documented_flag"] is None
    crp = measurements["hl7_1988_5"]  # no MedTwin analyte carries this code; the documented code is kept
    assert (crp["result_operator"], crp["value"], crp["reference_high"], crp["canonical_code"]) == ("<", 0.5, 5.0, "1988-5")
    assert "hemoglobin" not in measurements  # OBX-11 "X": the result could not be obtained
    assert measurements["hl7_99999_9"]["value"] == 12  # a code with no MedTwin analyte keeps its documented code
    assert not any(name.startswith("hl7_5767") for name in measurements)  # a ratio is not a number
    text = client.get(f"/api/v1/uploads/{upload.json()['id']}/text", headers=headers).json()["text"]
    assert text[creatinine["source_span_start"]:creatinine["source_span_end"]] == creatinine["source_span"]
    assert "SYNTHETICFAMILY" not in text and "SYNTHETIC-PID-MARKER" not in text


def test_hl7_upload_must_be_an_hl7_message(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": "CASE-HL7-BAD"}, headers=headers).json()["id"]
    refused = client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": ("results.hl7", b"Creatinine 1.4 mg/dL", "text/plain")},
                          data={"deidentified": "true"}, headers=headers)
    assert refused.status_code == 415
