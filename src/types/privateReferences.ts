export type SourceRef = { source: string; page: number };
export type ReferenceSummary = {
  id: string; title: string; summary: string; source_count: number; page_count: number; created_at: string;
  trust: { source: string; integrity: string; extraction: string; clinical_review: string; ground_truth: boolean; training_eligible: boolean };
};
export type ReferenceReport = ReferenceSummary & {
  facts: Array<{ title: string; text: string; refs: SourceRef[] }>;
  measurements: Array<{ label: string; value: string; unit: string; date: string; interval: string; flag: string; refs: SourceRef[] }>;
  timeline: Array<{ date: string; title: string; text: string; refs: SourceRef[] }>;
  insights: Array<{ title: string; text: string; refs: SourceRef[]; links?: Array<{ title: string; url: string }> }>;
  conflicts: string[]; limitations: string[];
  model_outputs: Array<{ organ: string; test: string; finding: string; model: string; status: string; reason: string }>;
  processing: { ocr_engine: string | null; renderer: string; summary_method: string; diagnostic_models_run: string[]; forecast_status: string };
  sources: Array<{ id: string; label: string; sha256: string; bytes: number; page_count: number; original_asset: string; contains_identifiers: boolean;
    pages: Array<{ page: number; asset: string; description: string; ocr: { text: string; engine: string; mean_confidence: number | null; line_count: number } }> }>;
};
