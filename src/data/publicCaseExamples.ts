/** Fictional teaching adaptations. Never populate this module from private
 * exports, OCR, source hashes, identifying images or account-owned records.
 * Names, clinical details, measurements and relative timelines are invented.
 */
export type TeachingCase = {
  id: string;
  name: string;
  title: string;
  theme: string;
  summary: string;
  sources: Array<{ id: string; label: string; type: string; when: string; text: string }>;
  findings: Array<{ title: string; explanation: string; source: string; certainty: string }>;
  measurements: Array<{ label: string; value: string; unit: string; when: string; context: string; source: string }>;
  timeline: Array<{ when: string; event: string }>;
  differences: string[];
  insights: Array<{ title: string; detail: string }>;
  capabilities: Array<{ organ: string; test: string; target: string; output: string; model: string }>;
  references: Array<{ title: string; url: string }>;
};

export const PUBLIC_EXAMPLE_NOTICE = "Fictional teaching adaptations: names, clinical details, measurements and timelines are invented. These examples illustrate report handling and evidence limits. They are not patient records, model predictions or validated clinical cases.";

export const PUBLIC_CASE_EXAMPLES: TeachingCase[] = [
  {
    id: "alex-brain-report", name: "Alex", title: "An injury report and a photographed film", theme: "Brain · CT report · source quality",
    summary: "Learn how a reported brain finding differs from a new image-model result, and why repeated photographs do not create a follow-up study.",
    sources: [
      { id: "A1", label: "Fictional CT report", type: "Authored text fixture", when: "Visit 1", text: "FICTIONAL TEACHING REPORT\nNon-contrast CT brain. Small left frontal haemorrhagic contusion with mild surrounding oedema. No midline shift reported. Correlate with the clinical examination. This text is an invented software illustration." },
      { id: "A2", label: "Fictional input inventory", type: "Authored text fixture", when: "Visit 1", text: "FICTIONAL INPUT INVENTORY\nA photograph of a printed CT film and two photographs of the same report are described. No DICOM series, physical slice spacing or later examination is available. No actual film photograph is included in this public example." },
    ],
    findings: [
      { title: "Contusion described in a report", explanation: "The fictional report describes a left frontal contusion and surrounding oedema. The overview attributes this statement to the report; it does not claim that an AI detected it on an image.", source: "A1", certainty: "Reported finding in an invented record" },
      { title: "A negative statement has a date and scope", explanation: "The fictional report states no midline shift at Visit 1. That statement cannot establish what a later examination would show.", source: "A1", certainty: "Reported absence at one visit" },
      { title: "Film photographs have input limits", explanation: "The input inventory lacks native slices and calibrated geometry. A CT-volume model, lesion-volume measurement and image registration have no eligible input in this example.", source: "A2", certainty: "Input limitation" },
    ],
    measurements: [],
    timeline: [{ when: "Visit 1", event: "One fictional CT examination and its report are described." }, { when: "Later follow-up", event: "No follow-up examination is supplied. Recovery and interval change are unavailable." }],
    differences: ["Two views of the same report count as one examination.", "An upload timestamp and an examination date describe different events."],
    insights: [
      { title: "What a later comparison would need", detail: "A new dated report, an appropriate native image series and reviewed clinical context would provide a basis for comparison. This example contains no recovery estimate." },
      { title: "What the overview can explain", detail: "Which source states the finding, which statements are negated, and why the supplied input cannot support a new CT-model prediction." },
    ],
    capabilities: [
      { organ: "Brain", test: "CT report text", target: "Reported contusion and negated midline shift", output: "Authored source-linked explanation", model: "Static teaching text; no diagnostic model" },
      { organ: "Brain", test: "Photographed CT film", target: "Fresh haemorrhage detection or segmentation", output: "ABSTAIN · native CT data missing", model: "No validated model/version used" },
      { organ: "Brain", test: "Single historical examination", target: "Recovery or future neurological outcome", output: "UNAVAILABLE · follow-up missing", model: "No individual forecasting model" },
    ], references: [],
  },
  {
    id: "maya-mixed-reports", name: "Maya", title: "Making sense of reports from different tests", theme: "Chest · ultrasound · laboratory context",
    summary: "Explore differing report explanations, uncertain demographics and a single laboratory panel without turning them into a definitive diagnosis or forecast.",
    sources: [
      { id: "B1", label: "Fictional laboratory panel", type: "Authored text fixture", when: "Visit 1", text: "FICTIONAL LABORATORY PANEL\nHbA1c: 8.1 %. Creatinine: 1.18 mg/dL. Reported eGFR: 49 mL/min/1.73 m². Adult age field differs from the imaging record. These numbers are invented and must not be used for a real person's care." },
      { id: "B2", label: "Fictional ultrasound summary", type: "Authored text fixture", when: "Visit 2", text: "FICTIONAL ULTRASOUND SUMMARY\nIncreased liver echogenicity is described. A raised left hemidiaphragm is noted; a possible diaphragmatic hernia is raised as a question for further assessment. No native ultrasound images are supplied." },
      { id: "B3", label: "Fictional chest CT summary", type: "Authored text fixture", when: "Visit 2", text: "FICTIONAL CHEST CT SUMMARY\nReticular interstitial changes are described. Thyroid enlargement is noted, with ultrasound correlation suggested in the fictional report. The left hemidiaphragm is elevated without a described focal defect; a functional cause is suggested, not confirmed. No native CT volume is supplied." },
    ],
    findings: [
      { title: "Different reports can ask different questions", explanation: "The ultrasound raises a possible hernia. The fictional CT summary does not describe a focal defect and suggests a functional explanation. Keep both attributions and their uncertainty visible.", source: "B2, B3", certainty: "Possible explanations; unresolved" },
      { title: "A thyroid finding is not a cancer result", explanation: "The fictional CT summary describes enlargement and recommends further correlation. No cytology or pathology result is present in this teaching packet.", source: "B3", certainty: "Reported finding; further assessment missing" },
      { title: "One panel is a snapshot", explanation: "The invented HbA1c, creatinine and reported eGFR can be shown with their source. Demographics are unresolved, so the example does not recompute an age-dependent estimate or assign an individual risk score.", source: "B1", certainty: "Illustrative measurements" },
    ],
    measurements: [
      { label: "HbA1c", value: "8.1", unit: "%", when: "Visit 1", context: "Invented value. An individual treatment target has not been supplied.", source: "B1" },
      { label: "Creatinine", value: "1.18", unit: "mg/dL", when: "Visit 1", context: "Invented value. No source-specific reference interval is supplied.", source: "B1" },
      { label: "Reported eGFR", value: "49", unit: "mL/min/1.73 m²", when: "Visit 1", context: "Invented reported estimate; not recomputed. Chronicity is unestablished.", source: "B1" },
    ],
    timeline: [{ when: "Visit 1", event: "One fictional laboratory panel is available." }, { when: "Visit 2", event: "Ultrasound and chest CT summaries describe complementary observations." }, { when: "Longitudinal assessment", event: "Repeat laboratory results, functional testing and any thyroid follow-up are absent." }],
    differences: ["The fictional records contain inconsistent adult age fields; identity and demographics need reconciliation.", "The ultrasound and CT offer different possible explanations for the raised hemidiaphragm.", "A source recommendation for further testing is not the result of that test."],
    insights: [
      { title: "Kidney context needs persistence", detail: "A single reduced eGFR does not, by itself, establish chronic kidney disease. CKD criteria include persistence beyond three months. This example assigns no CKD stage or kidney-failure probability." },
      { title: "HbA1c describes a period, not a forecast", detail: "HbA1c generally reflects average glucose over about three months. It does not predict a particular person's next glucose value or complication." },
      { title: "A useful future record", detail: "A dated follow-up report can answer an earlier report's question. The example keeps that evidence missing rather than inventing a completed test or a reassuring result." },
    ],
    capabilities: [
      { organ: "Chest / diaphragm", test: "Two report summaries", target: "Different attributed explanations", output: "Side-by-side source comparison", model: "Static teaching text; no diagnostic model" },
      { organ: "Thyroid", test: "CT report summary", target: "Enlargement and requested correlation", output: "Reported question; pathology unavailable", model: "No cancer detector or pathology model used" },
      { organ: "Kidneys / metabolic", test: "One illustrative blood panel", target: "Measurement context and future risk", output: "Values shown; individual forecast unavailable", model: "No validated forecasting model/version used" },
    ],
    references: [{ title: "NIDDK · What the A1C test measures", url: "https://www.niddk.nih.gov/health-information/diagnostic-tests/a1c-test" }, { title: "National Kidney Foundation · CKD criteria", url: "https://www.kidney.org/what-criteria-ckd" }],
  },
  {
    id: "sam-neuro-cardiac", name: "Sam", title: "Reading a multidisciplinary review together", theme: "MRI reports · echocardiography · clinical notes",
    summary: "See how a detailed report can add qualifications to a brief clinical summary, while prescriptions, orders and waveform photographs keep their own evidence roles.",
    sources: [
      { id: "C1", label: "Fictional MRI summaries", type: "Authored text fixture", when: "Visit 1", text: "FICTIONAL MRI SUMMARIES\nBrain: chronic white-matter changes are described; no new image-model assessment is available. Cervical spine: mild degenerative changes with a small C6-C7 disc bulge are described. Native MRI sequences are absent." },
      { id: "C2", label: "Fictional formal echo report", type: "Authored text fixture", when: "Visit 1", text: "FICTIONAL ECHO REPORT\nReported LVEF approximately 61 %. LV systolic function is described as preserved. Grade I diastolic dysfunction is also reported. This is an invented text report, not an echocardiography video or an AI-estimated EF." },
      { id: "C3", label: "Fictional clinic notes and inventory", type: "Authored text fixture", when: "Visits 1 and 2", text: "FICTIONAL CLINIC NOTES\nA brief note summarises the echo as normal. Blood pressure entries are 148/86 at Visit 1 and 144/90 at Visit 2. A historical prescription, an investigation request and a paper ECG photograph are listed. No actual prescription, ECG image, patient identifiers or digital waveform is included here." },
    ],
    findings: [
      { title: "Read the formal echo details", explanation: "The invented EF is 61%, while the formal text separately records a diastolic finding. A short note saying normal must not erase the qualifications in the formal report.", source: "C2, C3", certainty: "Difference between fictional source summaries" },
      { title: "MRI report statements retain provenance", explanation: "The overview attributes white-matter and cervical changes to the authored MRI summaries. It offers no new scan interpretation, lesion mask or registered 3-D location.", source: "C1", certainty: "Reported observations in an invented record" },
      { title: "Orders and prescriptions have distinct roles", explanation: "An investigation request is evidence that a test was requested. A historical prescription is a historical document. Neither is automatically a completed result or current treatment advice.", source: "C3", certainty: "Document role classification" },
    ],
    measurements: [
      { label: "LVEF (reported)", value: "≈61", unit: "%", when: "Visit 1", context: "Invented report value, not a video-model estimate. The diastolic finding remains separately visible.", source: "C2" },
      { label: "Blood pressure", value: "148/86", unit: "mmHg", when: "Visit 1", context: "Invented clinic observation; no trend is inferred.", source: "C3" },
      { label: "Blood pressure", value: "144/90", unit: "mmHg", when: "Visit 2", context: "Invented clinic observation; no treatment effect is inferred.", source: "C3" },
    ],
    timeline: [{ when: "Visit 1", event: "Fictional MRI and echo text reports are available." }, { when: "Visit 2", event: "A brief clinic note summarises the reports and records another blood-pressure observation." }, { when: "Later outcome", event: "No independent later examination or long-term outcome is supplied." }],
    differences: ["The brief clinic summary says normal echo; the detailed fictional echo text includes diastolic dysfunction.", "Two blood-pressure observations do not establish sustained control or treatment benefit.", "A paper ECG photograph is not a sampled digital signal."],
    insights: [
      { title: "Keep the different observations together", detail: "A useful overview preserves the formal report, the brief note and their different wording. It does not force them into an unqualified normal or abnormal label." },
      { title: "What future comparison could use", detail: "A new dated clinical assessment and complete repeat reports could be compared with the earlier observations. No individual stroke, cardiac or functional-outcome probability is generated here." },
    ],
    capabilities: [
      { organ: "Brain / cervical spine", test: "MRI report summaries", target: "Attributed report findings", output: "Authored evidence overview", model: "Static teaching text; no MRI model used" },
      { organ: "Heart", test: "Echo report text", target: "Reported EF and diastolic qualification", output: "Report comparison; no video inference", model: "No echo-video model/version used" },
      { organ: "Heart", test: "Paper ECG photograph", target: "Rhythm and interval analysis", output: "ABSTAIN · digital waveform missing", model: "No digital ECG model used" },
    ], references: [],
  },
];
