export type Finding = {
  label: string;
  system: "Respiratory" | "Cardiac" | "Musculoskeletal" | "Neurological" | "General";
  region: string;
  status: "present" | "negated";
  severity: "mild" | "moderate" | "severe" | "unspecified";
  source: string;
};

export type ClinicalMetric = {
  label: string;
  value: number;
  unit: string;
  raw: string;
};

export type ReportAnalysis = {
  findings: Finding[];
  metrics: ClinicalMetric[];
  sentenceCount: number;
  completeness: number;
  extractionConfidence: number;
  reviewPriority: "Routine" | "Review" | "Priority review";
  systems: string[];
};

export type Comparison = {
  added: Finding[];
  resolved: Finding[];
  persistent: Finding[];
  metricDeltas: Array<ClinicalMetric & {
    previous: number;
    delta: number;
    percentChange: number | null;
    ratePerDay: number;
    direction: "up" | "down" | "same";
  }>;
  similarity: number;
  summary: string;
};

const concepts: Array<{ label: string; terms: string[]; system: Finding["system"]; region: string }> = [
  { label: "Pulmonary opacity", terms: ["opacity", "opacification", "infiltrate"], system: "Respiratory", region: "Lungs" },
  { label: "Pleural effusion", terms: ["pleural effusion", "pleural fluid"], system: "Respiratory", region: "Pleura" },
  { label: "Pneumothorax", terms: ["pneumothorax"], system: "Respiratory", region: "Pleura" },
  { label: "Consolidation", terms: ["consolidation"], system: "Respiratory", region: "Lungs" },
  { label: "Cardiomegaly", terms: ["cardiomegaly", "enlarged heart", "cardiac enlargement"], system: "Cardiac", region: "Heart" },
  { label: "Arrhythmia", terms: ["arrhythmia", "atrial fibrillation", "irregular rhythm"], system: "Cardiac", region: "Heart" },
  { label: "Fracture", terms: ["fracture", "osseous injury"], system: "Musculoskeletal", region: "Skeleton" },
  { label: "Edema", terms: ["edema", "oedema"], system: "General", region: "Soft tissue" },
  { label: "Lesion", terms: ["lesion", "mass", "nodule"], system: "General", region: "Unspecified" },
  { label: "Hemorrhage", terms: ["hemorrhage", "haemorrhage", "bleeding"], system: "Neurological", region: "Brain" },
];

const metricPatterns: Array<{ label: string; unit: string; expression: RegExp }> = [
  { label: "Heart rate", unit: "bpm", expression: /(?:heart rate|hr)[:\s]*(\d{2,3})\s*(?:bpm)?/i },
  { label: "SpO₂", unit: "%", expression: /(?:spo2|oxygen saturation)[:\s]*(\d{2,3})\s*%?/i },
  { label: "Ejection fraction", unit: "%", expression: /(?:ejection fraction|ef)[:\s]*(\d{1,3})\s*%?/i },
  { label: "Glucose", unit: "mg/dL", expression: /(?:glucose)[:\s]*(\d{2,3}(?:\.\d+)?)\s*(?:mg\/dl)?/i },
  { label: "Temperature", unit: "°C", expression: /(?:temperature|temp)[:\s]*(\d{2}(?:\.\d+)?)\s*(?:°?c)?/i },
  { label: "Respiratory rate", unit: "/min", expression: /(?:respiratory rate|rr)[:\s]*(\d{1,2})/i },
  { label: "Systolic BP", unit: "mmHg", expression: /(?:blood pressure|bp)[:\s]*(\d{2,3})\s*\/\s*\d{2,3}/i },
  { label: "Diastolic BP", unit: "mmHg", expression: /(?:blood pressure|bp)[:\s]*\d{2,3}\s*\/\s*(\d{2,3})/i },
];

function sentenceList(text: string) {
  return text.split(/(?<=[.!?])\s+|\n+/).map((sentence) => sentence.trim()).filter(Boolean);
}

function isNegated(sentence: string, termIndex: number) {
  const prefix = sentence.slice(Math.max(0, termIndex - 48), termIndex).toLowerCase();
  return /\b(no|not|without|absent|negative for|free of|resolved)\b/.test(prefix);
}

export function analyzeReport(text: string): ReportAnalysis {
  const sentences = sentenceList(text);
  const findings: Finding[] = [];

  for (const sentence of sentences) {
    const lower = sentence.toLowerCase();
    for (const concept of concepts) {
      const term = concept.terms.find((candidate) => lower.includes(candidate));
      if (!term) continue;
      const termIndex = lower.indexOf(term);
      const severity = /\bsevere|marked|extensive\b/.test(lower)
        ? "severe"
        : /\bmoderate\b/.test(lower)
          ? "moderate"
          : /\bmild|small|minimal|subtle\b/.test(lower)
            ? "mild"
            : "unspecified";
      const finding: Finding = {
        label: concept.label,
        system: concept.system,
        region: concept.region,
        status: isNegated(sentence, termIndex) ? "negated" : "present",
        severity,
        source: sentence,
      };
      if (!findings.some((item) => item.label === finding.label && item.status === finding.status)) findings.push(finding);
    }
  }

  const metrics = metricPatterns.flatMap((pattern) => {
    const match = text.match(pattern.expression);
    if (!match) return [];
    return [{ label: pattern.label, value: Number(match[1]), unit: pattern.unit, raw: match[0] }];
  });
  const severe = findings.filter((finding) => finding.status === "present" && finding.severity === "severe").length;
  const present = findings.filter((finding) => finding.status === "present").length;
  const completeness = Math.min(100, 35 + Math.min(sentences.length, 8) * 5 + Math.min(metrics.length, 4) * 5 + (findings.length ? 15 : 0));
  const extractionConfidence = Math.min(96, 62 + Math.min(findings.length * 5, 20) + Math.min(metrics.length * 3, 12));

  return {
    findings,
    metrics,
    sentenceCount: sentences.length,
    completeness,
    extractionConfidence,
    reviewPriority: severe > 0 ? "Priority review" : present > 1 ? "Review" : "Routine",
    systems: [...new Set(findings.map((finding) => finding.system))],
  };
}

export function compareReports(previousText: string, currentText: string, daysBetween = 1): Comparison {
  const previous = analyzeReport(previousText);
  const current = analyzeReport(currentText);
  const key = (finding: Finding) => `${finding.label}:${finding.status}`;
  const oldKeys = new Set(previous.findings.map(key));
  const newKeys = new Set(current.findings.map(key));
  const added = current.findings.filter((finding) => finding.status === "present" && !oldKeys.has(key(finding)));
  const resolved = previous.findings.filter((finding) => finding.status === "present" && !newKeys.has(key(finding)));
  const persistent = current.findings.filter((finding) => finding.status === "present" && oldKeys.has(key(finding)));
  const metricDeltas = current.metrics.flatMap((metric) => {
    const old = previous.metrics.find((candidate) => candidate.label === metric.label);
    if (!old) return [];
    const delta = Number((metric.value - old.value).toFixed(2));
    const percentChange = old.value === 0 ? null : Number(((delta / Math.abs(old.value)) * 100).toFixed(2));
    const ratePerDay = Number((delta / Math.max(1, daysBetween)).toFixed(3));
    return [{ ...metric, previous: old.value, delta, percentChange, ratePerDay, direction: delta > 0 ? "up" as const : delta < 0 ? "down" as const : "same" as const }];
  });
  const union = new Set([...oldKeys, ...newKeys]).size;
  const intersection = [...newKeys].filter((item) => oldKeys.has(item)).length;
  const similarity = union ? Math.round((intersection / union) * 100) : 100;
  const changes = [
    added.length ? `${added.length} new finding${added.length === 1 ? "" : "s"}` : "",
    resolved.length ? `${resolved.length} no longer stated` : "",
    metricDeltas.length ? `${metricDeltas.length} comparable metric${metricDeltas.length === 1 ? "" : "s"}` : "",
  ].filter(Boolean);

  return {
    added,
    resolved,
    persistent,
    metricDeltas,
    similarity,
    summary: changes.length ? changes.join(", ") : "No structured differences were extracted.",
  };
}
