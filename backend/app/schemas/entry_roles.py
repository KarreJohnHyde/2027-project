"""Roles a person can describe themselves with on the welcome page.

Self-described only: no value grants access or privileges (every entry-page account is a public account that sees its
own cases). The list is the same as the frontend's src/data/entryRoles.ts; tests/test_entry_roles.py keeps them equal.
"""

GENERAL_ROLES = (
    "researcher", "student", "educator",
    "clinician", "doctor", "resident", "surgeon", "nurse", "nurse_practitioner", "midwife", "clinical_staff",
    "physician_assistant", "pharmacist", "lab_expert", "radiographer", "sonographer", "physiotherapist",
    "occupational_therapist", "dietitian", "psychologist", "dentist", "paramedic", "medical_physicist", "allied_health",
    "patient", "caregiver", "other",
)

SPECIALTIES = (
    "anaesthesiology", "cardiology", "cardiothoracic_surgery", "clinical_pharmacology", "critical_care", "dermatology",
    "emergency_medicine", "endocrinology", "ent", "family_medicine", "forensic_medicine", "gastroenterology",
    "general_surgery", "genetics", "geriatrics", "haematology", "immunology", "infectious_diseases", "internal_medicine",
    "interventional_radiology", "maxillofacial_surgery", "neonatology", "nephrology", "neurology", "neurosurgery",
    "nuclear_medicine", "obstetrics_gynaecology", "occupational_medicine", "oncology", "ophthalmology", "orthopaedics",
    "paediatrics", "paediatric_surgery", "pain_medicine", "palliative_care", "pathology", "plastic_surgery", "psychiatry",
    "public_health", "pulmonology", "radiation_oncology", "radiology", "rehabilitation", "rheumatology",
    "sports_medicine", "transplant_surgery", "urology", "vascular_surgery",
)

DEPARTMENTS = (
    "administration", "biomedical_engineering", "blood_bank", "emergency", "health_informatics", "icu",
    "infection_control", "inpatient", "laboratory", "medical_education", "medical_records", "nursing",
    "operating_theatre", "outpatient", "pharmacy", "quality_safety", "radiology", "rehabilitation", "research_ethics",
    "telemedicine",
)

ENTRY_ROLES = frozenset(
    GENERAL_ROLES
    + tuple(f"specialist_{key}" for key in SPECIALTIES)
    + tuple(f"department_{key}" for key in DEPARTMENTS)
)

# Values earlier versions of the page sent; still accepted so an older client keeps working.
LEGACY_ENTRY_ROLES = frozenset({"radiologist"})
