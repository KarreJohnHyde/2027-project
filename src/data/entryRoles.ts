/**
 * Roles a person can describe themselves with on the welcome page. Self-described only: no role grants access or
 * privileges (every entry-page account is a public account that sees its own cases). The backend accepts exactly
 * these values (backend/app/schemas/entry_roles.py); a test keeps the two lists identical.
 */
export type EntryRoleOption = { value: string; label: string };
export type EntryRoleGroup = { label: string; roles: EntryRoleOption[] };

const specialist = (key: string, label: string): EntryRoleOption => ({ value: `specialist_${key}`, label });
const department = (key: string, label: string): EntryRoleOption => ({ value: `department_${key}`, label });

export const ENTRY_ROLE_GROUPS: EntryRoleGroup[] = [
  {
    label: "Research and education",
    roles: [
      { value: "researcher", label: "Researcher" },
      { value: "student", label: "Student" },
      { value: "educator", label: "Educator or lecturer" },
    ],
  },
  {
    label: "Clinical roles",
    roles: [
      { value: "clinician", label: "Clinician" },
      { value: "doctor", label: "Doctor" },
      { value: "resident", label: "Resident or trainee doctor" },
      { value: "surgeon", label: "Surgeon" },
      { value: "nurse", label: "Nurse" },
      { value: "nurse_practitioner", label: "Nurse practitioner" },
      { value: "midwife", label: "Midwife" },
      { value: "clinical_staff", label: "Clinical staff" },
      { value: "physician_assistant", label: "Physician assistant" },
      { value: "pharmacist", label: "Pharmacist" },
      { value: "lab_expert", label: "Laboratory scientist or technician" },
      { value: "radiographer", label: "Radiographer or imaging technologist" },
      { value: "sonographer", label: "Sonographer" },
      { value: "physiotherapist", label: "Physiotherapist" },
      { value: "occupational_therapist", label: "Occupational therapist" },
      { value: "dietitian", label: "Dietitian or nutritionist" },
      { value: "psychologist", label: "Psychologist" },
      { value: "dentist", label: "Dentist" },
      { value: "paramedic", label: "Paramedic or emergency technician" },
      { value: "medical_physicist", label: "Medical physicist" },
      { value: "allied_health", label: "Other allied health professional" },
    ],
  },
  {
    label: "Medical specialists",
    roles: [
      specialist("anaesthesiology", "Anaesthesiology"),
      specialist("cardiology", "Cardiology"),
      specialist("cardiothoracic_surgery", "Cardiothoracic surgery"),
      specialist("clinical_pharmacology", "Clinical pharmacology"),
      specialist("critical_care", "Critical care medicine"),
      specialist("dermatology", "Dermatology"),
      specialist("emergency_medicine", "Emergency medicine"),
      specialist("endocrinology", "Endocrinology and diabetes"),
      specialist("ent", "Ear, nose and throat (ENT)"),
      specialist("family_medicine", "Family medicine or general practice"),
      specialist("forensic_medicine", "Forensic medicine"),
      specialist("gastroenterology", "Gastroenterology and hepatology"),
      specialist("general_surgery", "General surgery"),
      specialist("genetics", "Medical genetics"),
      specialist("geriatrics", "Geriatric medicine"),
      specialist("haematology", "Haematology"),
      specialist("immunology", "Immunology and allergy"),
      specialist("infectious_diseases", "Infectious diseases"),
      specialist("internal_medicine", "Internal medicine"),
      specialist("interventional_radiology", "Interventional radiology"),
      specialist("maxillofacial_surgery", "Oral and maxillofacial surgery"),
      specialist("neonatology", "Neonatology"),
      specialist("nephrology", "Nephrology"),
      specialist("neurology", "Neurology"),
      specialist("neurosurgery", "Neurosurgery"),
      specialist("nuclear_medicine", "Nuclear medicine"),
      specialist("obstetrics_gynaecology", "Obstetrics and gynaecology"),
      specialist("occupational_medicine", "Occupational medicine"),
      specialist("oncology", "Medical oncology"),
      specialist("ophthalmology", "Ophthalmology"),
      specialist("orthopaedics", "Orthopaedics"),
      specialist("paediatrics", "Paediatrics"),
      specialist("paediatric_surgery", "Paediatric surgery"),
      specialist("pain_medicine", "Pain medicine"),
      specialist("palliative_care", "Palliative care"),
      specialist("pathology", "Pathology"),
      specialist("plastic_surgery", "Plastic and reconstructive surgery"),
      specialist("psychiatry", "Psychiatry"),
      specialist("public_health", "Public health"),
      specialist("pulmonology", "Pulmonology and respiratory medicine"),
      specialist("radiation_oncology", "Radiation oncology"),
      specialist("radiology", "Radiology"),
      specialist("rehabilitation", "Physical medicine and rehabilitation"),
      specialist("rheumatology", "Rheumatology"),
      specialist("sports_medicine", "Sports medicine"),
      specialist("transplant_surgery", "Transplant surgery"),
      specialist("urology", "Urology"),
      specialist("vascular_surgery", "Vascular surgery"),
    ],
  },
  {
    label: "Healthcare departments",
    roles: [
      department("administration", "Hospital administration"),
      department("biomedical_engineering", "Biomedical engineering"),
      department("blood_bank", "Blood bank and transfusion"),
      department("emergency", "Emergency department"),
      department("health_informatics", "Health informatics and IT"),
      department("icu", "Intensive care unit"),
      department("infection_control", "Infection prevention and control"),
      department("inpatient", "Inpatient wards"),
      department("laboratory", "Laboratory and pathology"),
      department("medical_education", "Medical education"),
      department("medical_records", "Medical records"),
      department("nursing", "Nursing"),
      department("operating_theatre", "Operating theatres"),
      department("outpatient", "Outpatient department"),
      department("pharmacy", "Pharmacy"),
      department("quality_safety", "Quality and patient safety"),
      department("radiology", "Radiology and imaging"),
      department("rehabilitation", "Physiotherapy and rehabilitation"),
      department("research_ethics", "Research and ethics office"),
      department("telemedicine", "Telemedicine"),
    ],
  },
  {
    label: "Patients and families",
    roles: [
      { value: "patient", label: "Patient" },
      { value: "caregiver", label: "Caregiver or family member" },
    ],
  },
  {
    label: "Other",
    roles: [{ value: "other", label: "Other" }],
  },
];

const LABELS = new Map(ENTRY_ROLE_GROUPS.flatMap((group) => group.roles.map((role) => [role.value, role.label] as const)));

/** The readable name of a stated role; older or unknown values fall back to their own text. */
export function entryRoleLabel(value: string): string {
  return LABELS.get(value) ?? value.replace(/_/g, " ").replace(/^\w/, (letter) => letter.toUpperCase());
}
