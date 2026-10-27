import { useState } from "react";
import { FlaskConical } from "lucide-react";
import { CalibrationChart, ChartFrame, ConfusionMatrix, CurveChart } from "../components/charts";
import { Badge, Button, Card, Disclosure, ErrorBlock, Field, KeyValue, LoadingBlock, Metric, PageHeader, Segmented, SelectInput, StatusBadge, Table, TextInput, Unavailable } from "../components/ui";
import { api, type EvaluationResult, type EvaluationSplit, type EvaluationTask } from "../services/api";
import { datasetName, licenceLabel, publicText, taskName } from "../lib/displayNames";
import { Link } from "../lib/router";
import { errorMessage, formatCount, formatDate, formatNumber, humanize } from "../lib/format";
import { useAsync } from "../lib/useAsync";

/** A run identifier names its model; the UI shows only the run's UTC time. */
function runLabel(runId: unknown): string {
  const match = /(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/.exec(String(runId ?? ""));
  return match ? `${match[1]}-${match[2]}-${match[3]} ${match[4]}:${match[5]} UTC` : "registered run";
}

type Task = EvaluationTask | "segmentation" | "segmentation_batch" | "detection" | "clinical_nlp" | "ocr";

/** Input formats; the kit's column names (score, patient_id) are accepted as aliases. */
const COLUMNS: Record<Task, string> = {
  classification: "y_true (0/1), y_score or score [, group_id or patient_id]",
  multiclass: "y_true, y_pred (labels)",
  regression: "y_true, y_pred [, lower, upper, group_id]",
  survival: "time, event (0/1), risk_score [, group_id]",
  forecast: "patient_id, target, horizon, y_true, y_pred",
  lab_extraction: "patient_id, source_id, analyte_code, reference_value, predicted_value, reference_unit, predicted_unit",
  clinical_nlp: "two strict JSON artifacts: independently annotated gold spans and predicted spans",
  ocr: "two strict page JSON artifacts: independent gold transcription and OCR prediction",
  segmentation: "one binary reference mask and one predicted mask (PNG or .npy)",
  segmentation_batch: "ZIP with manifest.csv (patient_id, reference_mask, predicted_mask) and the masks",
  detection: "COCO results JSON and COCO reference annotations JSON",
};

const TASK_LABEL: Record<Task, string> = {
  classification: "Binary classification (Eq. 7–9, 12)",
  multiclass: "Multiclass classification",
  regression: "Regression",
  survival: "Survival (Harrell's C)",
  forecast: "Forecast per target and horizon (Eq. 5–6)",
  lab_extraction: "Numeric lab extraction audit",
  clinical_nlp: "Clinical NLP spans and context",
  ocr: "Scanned-page OCR CER / WER",
  segmentation: "Segmentation, one mask pair (Eq. 10)",
  segmentation_batch: "Segmentation, mask archive (Eq. 10)",
  detection: "Box detection, COCO mAP (Eq. 11)",
};

const SPLITS: Array<{ value: EvaluationSplit | ""; label: string }> = [
  { value: "", label: "Not stated" },
  { value: "test", label: "Held-out test" },
  { value: "external_test", label: "External test" },
  { value: "validation", label: "Validation (not reportable)" },
  { value: "development", label: "Development (not reportable)" },
];

const FILE_INPUT = "block w-full text-xs text-ink-2 file:mr-2 file:rounded-md file:border file:border-line-strong file:bg-surface file:px-2 file:py-1 file:text-xs file:text-ink";

function ContextBanner({ result }: { result: EvaluationResult }) {
  const context = result.evaluation_context;
  if (!context) return null;
  const eligible = context.reporting_status === "ELIGIBLE_FOR_REPORTING";
  return (
    <div className={`rounded-lg border p-3 text-xs leading-5 ${eligible ? "border-line bg-surface" : "border-warning/40 bg-warning/5"}`}>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={eligible ? "VALID" : "EXPLORATORY"} label={eligible ? "Registry-bound research evidence" : "Exploratory: not eligible for reporting"} />
        <span className="text-ink-2">{context.dataset ?? "dataset not stated"}{context.dataset_version ? ` v${context.dataset_version}` : ""} · split {context.split ? humanize(context.split) : "not stated"} · checkpoint {context.checkpoint ? <code>{context.checkpoint.slice(0, 24)}</code> : "not stated"}</span>
      </div>
      {!eligible && <p className="mt-1 text-ink-3">Unresolved: {context.reporting_blockers.map(humanize).join(", ")}. Reporting requires exact local model/checkpoint, dataset/task/split, and uploaded evaluation-byte bindings.</p>}
      {eligible && context.registry_resolution?.task_id && <p className="mt-1 text-ink-3">Resolved task {taskName(context.registry_resolution.task_id)} ·{formatCount(context.registry_resolution.split_n)} registered held-out samples · input <code>{context.registry_resolution.evaluation_input_sha256?.slice(0, 16)}…</code> verified.</p>}
      <p className="mt-1 text-ink-3">Research evidence status only. It never activates a model or establishes clinical validity.</p>
      <p className="mt-1 text-ink-3">
        Code {context.code_revision?.commit ? <code>{context.code_revision.commit.slice(0, 10)}</code> : "commit not recorded"}
        {(context.reproducibility_warnings ?? []).length > 0 && <> · <span className="text-warning-text">{(context.reproducibility_warnings ?? []).map(humanize).join(", ")}</span></>}
      </p>
    </div>
  );
}

function PerGroupTable({ headers, rows }: { headers: string[]; rows: Array<Array<string | number>> }) {
  return (
    <Table headers={headers} dense>
      {rows.map((row, index) => <tr key={index}>{row.map((cell, column) => <td key={column} className={column === 0 ? "text-ink" : "tabular text-ink-2"}>{cell}</td>)}</tr>)}
    </Table>
  );
}

function intervalText(interval: unknown): string {
  const value = interval as Interval | undefined;
  if (!value) return "—";
  return value.status === "COMPUTED" ? `${formatNumber(value.low, 3)} – ${formatNumber(value.high, 3)}` : humanize(value.status);
}

type Interval = { status: string; low?: number; high?: number };

function MetricWithInterval({ label, value, interval }: { label: string; value: number | null | undefined; interval?: Interval }) {
  return (
    <Metric
      label={label}
      value={value === null || value === undefined ? "—" : formatNumber(value, 3)}
      note={interval?.status === "COMPUTED" ? `95% CI ${formatNumber(interval.low, 3)} – ${formatNumber(interval.high, 3)}` : interval ? humanize(interval.status) : undefined}
    />
  );
}

function AccuracyObjective({ result }: { result: EvaluationResult }) {
  const target = result.accuracy_target as { objective: string; point_estimate_exceeds: boolean; ci_lower_bound_exceeds: boolean | null } | undefined;
  if (!target) return null;
  const verdict = target.ci_lower_bound_exceeds === null
    ? "not assessable without a confidence interval"
    : target.ci_lower_bound_exceeds ? "the 95% CI lower bound exceeds 0.95" : "the 95% CI lower bound does not exceed 0.95";
  return (
    <p className="text-xs leading-5 text-ink-2">
      <span className="font-medium text-ink">Accuracy objective</span> ({target.objective}): {verdict}; the point estimate {target.point_estimate_exceeds ? "exceeds" : "does not exceed"} 0.95.
    </p>
  );
}

function ResultView({ result }: { result: EvaluationResult }) {
  const intervals = (result.confidence_intervals_95 ?? {}) as Record<string, Interval>;
  const provenance = {
    source: `Uploaded predictions · SHA-256 ${result.input_sha256.slice(0, 16)}…`,
    sample_count: result.n,
    sample_count_semantics: result.n_groups ? `rows in ${result.n_groups} groups` : "rows",
    analysis_population: "As supplied in the uploaded held-out file",
    time_frame: formatDate(result.created_at, true),
    model_version: (result.model_id as string | undefined) ?? null,
    metric_definition: `${humanize(result.task_type)} metrics; bootstrap ${JSON.stringify(result.bootstrap ?? {})}`,
    limitations: (result.assumptions as string[] | undefined) ?? [],
  };
  if (result.task_type === "classification") {
    const confusion = result.confusion_matrix as Record<string, number>;
    const metrics = result.metrics;
    return (
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <MetricWithInterval label="AUROC" value={metrics.auroc} interval={intervals.auroc} />
          <MetricWithInterval label="AUPRC (average precision)" value={metrics.auprc_average_precision} interval={intervals.auprc_average_precision} />
          <MetricWithInterval label="Sensitivity" value={metrics.sensitivity_recall} interval={intervals.sensitivity_recall} />
          <MetricWithInterval label="Specificity" value={metrics.specificity} interval={intervals.specificity} />
          <MetricWithInterval label="Accuracy" value={metrics.accuracy} interval={intervals.accuracy} />
          <MetricWithInterval label="Balanced accuracy" value={metrics.balanced_accuracy} />
          <MetricWithInterval label="F1" value={metrics.f1} interval={intervals.f1} />
          <MetricWithInterval label="MCC" value={metrics.mcc} interval={intervals.mcc} />
        </div>
        {typeof (result.confidence_intervals_95 as Record<string, unknown> | undefined)?.status === "string" && (
          <Unavailable compact code={String((result.confidence_intervals_95 as Record<string, unknown>).status)} reason={String((result.confidence_intervals_95 as Record<string, unknown>).requirement ?? "")} />
        )}
        <AccuracyObjective result={result} />
        <div className="grid gap-4 xl:grid-cols-2">
          <ChartFrame title="ROC curve" status="COMPUTED" provenance={provenance} columns={["FPR", "TPR", "Threshold"]} rows={(result.curves?.roc ?? []).map((point) => [formatNumber(point.fpr, 3), formatNumber(point.tpr, 3), formatNumber(point.threshold, 3)])}>
            <CurveChart points={result.curves?.roc ?? []} x="fpr" y="tpr" xLabel="False positive rate" yLabel="True positive rate" chance="diagonal" />
          </ChartFrame>
          <ChartFrame title="Precision–recall curve" status="COMPUTED" provenance={provenance} columns={["Recall", "Precision", "Threshold"]} rows={(result.curves?.pr ?? []).map((point) => [formatNumber(point.recall, 3), formatNumber(point.precision, 3), formatNumber(point.threshold, 3)])}>
            <CurveChart points={result.curves?.pr ?? []} x="recall" y="precision" xLabel="Recall" yLabel="Precision" chance={Number(result.prevalence ?? 0)} />
          </ChartFrame>
          <Card title={`Confusion matrix at threshold ${formatNumber(result.threshold as number, 3)}`} eyebrow={humanize(String(result.threshold_source))}>
            <ConfusionMatrix labels={["0", "1"]} matrix={[[confusion.tn, confusion.fp], [confusion.fn, confusion.tp]]} />
          </Card>
          {result.calibration?.bins ? (
            <ChartFrame title="Reliability diagram" subtitle={`ECE ${formatNumber(result.calibration.expected_calibration_error, 4)} · Brier ${formatNumber(metrics.brier_score, 4)}`} status="COMPUTED" provenance={provenance} columns={["Bin", "Mean predicted", "Observed", "Rows"]} rows={result.calibration.bins.map((bin) => [`${bin.bin_low}–${bin.bin_high}`, formatNumber(bin.mean_predicted, 3), formatNumber(bin.observed_fraction, 3), formatCount(bin.count)])}>
              <CalibrationChart bins={result.calibration.bins} />
            </ChartFrame>
          ) : <Unavailable code={result.calibration?.status ?? "NOT_APPLICABLE"} reason="Calibration needs probability-scale scores in [0, 1]." />}
        </div>
      </div>
    );
  }
  if (result.task_type === "multiclass") {
    return (
      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Confusion matrix"><ConfusionMatrix labels={result.labels as string[]} matrix={result.confusion_matrix as number[][]} /></Card>
        <Card title="Per class" padded={false}>
          <Table headers={["Class", "Support", "Precision", "Recall", "F1"]} dense>
            {(result.per_class as Array<Record<string, number | string | null>>).map((row) => <tr key={String(row.label)}><td>{String(row.label)}</td><td className="tabular">{row.support}</td><td>{formatNumber(row.precision as number, 3)}</td><td>{formatNumber(row.recall as number, 3)}</td><td>{formatNumber(row.f1 as number, 3)}</td></tr>)}
          </Table>
          <p className="p-3 text-xs text-ink-2">Accuracy {formatNumber(result.metrics.accuracy, 3)} · macro F1 {formatNumber(result.metrics.macro_f1, 3)}</p>
        </Card>
      </div>
    );
  }
  if (result.task_type === "regression") {
    const intervalsBlock = result.prediction_intervals as Record<string, number | string>;
    return (
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-5">
          <MetricWithInterval label="MAE" value={result.metrics.mae} interval={intervals.mae} />
          <MetricWithInterval label="RMSE" value={result.metrics.rmse} interval={intervals.rmse} />
          <MetricWithInterval label="Median absolute error" value={result.metrics.median_absolute_error} />
          <MetricWithInterval label="Mean error (bias)" value={result.metrics.mean_error_bias} />
          <MetricWithInterval label="R²" value={result.metrics.r_squared} />
        </div>
        {intervalsBlock.status === "COMPUTED" ? (
          <KeyValue columns={3} items={[
            { label: "Interval coverage", value: formatNumber(intervalsBlock.coverage as number, 3) },
            { label: "Mean width", value: formatNumber(intervalsBlock.mean_width as number, 3) },
            { label: "Mean interval score", value: intervalsBlock.mean_interval_score === undefined ? "Supply alpha" : `${formatNumber(intervalsBlock.mean_interval_score as number, 3)} (nominal ${formatNumber(intervalsBlock.nominal_coverage as number, 2)})` },
          ]} />
        ) : <Unavailable compact code="NOT_SUPPLIED" reason="Add lower and upper columns to evaluate prediction intervals." />}
      </div>
    );
  }
  if (result.task_type === "survival") {
    return (
      <div className="grid gap-3 sm:grid-cols-3">
        <MetricWithInterval label="Harrell's C-index" value={result.metrics.harrell_c_index} interval={intervals.harrell_c_index} />
        <Metric label="Events" value={formatCount(result.events as number)} note={`of ${formatCount(result.n)} rows`} />
        <div className="text-xs leading-5 text-ink-2">{((result.assumptions as string[]) ?? []).map((item) => <p key={item}>{item}</p>)}</div>
      </div>
    );
  }
  if (result.task_type === "forecast") {
    const groups = (result.per_target_and_horizon ?? []) as Array<Record<string, unknown>>;
    return (
      <Card title="Forecast error per target and horizon" eyebrow="Never pooled across targets" padded={false}>
        <PerGroupTable
          headers={["Target", "Horizon", "n", "Patients", "MAE", "MAE 95% CI", "RMSE", "RMSE 95% CI", "Bias"]}
          rows={groups.map((group) => {
            const ci = group.confidence_intervals_95 as Record<string, unknown>;
            return [String(group.target), String(group.horizon), formatCount(group.n as number), formatCount(group.n_patients as number), formatNumber(group.mae as number, 4), intervalText(ci.mae ?? ci), formatNumber(group.rmse as number, 4), intervalText(ci.rmse ?? ci), formatNumber(group.mean_error_bias as number, 4)];
          })}
        />
        <p className="p-3 text-[11px] leading-4 text-ink-3">{((result.assumptions as string[]) ?? []).join(" ")}</p>
      </Card>
    );
  }
  if (result.task_type === "lab_extraction") {
    const perAnalyte = (result.per_analyte ?? []) as Array<{ analyte_code: string; n: number; match_rate: number }>;
    return (
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Metric label="Value and unit match rate" value={formatNumber(result.metrics.value_and_unit_exact_match_rate_at_tolerance, 3)} note={`tolerance ${formatNumber(result.tolerance_in_reference_units as number, 4)} reference units`} />
          <Metric label="Extracted numeric rate" value={formatNumber(result.metrics.extracted_numeric_rate, 3)} />
          <Metric label="Unit match rate" value={formatNumber(result.metrics.unit_match_rate, 3)} />
          <Metric label="Matched correct" value={formatCount(result.metrics.matched_correct as number)} note={`of ${formatCount(result.n)} observations`} />
        </div>
        <Card title="Per analyte" padded={false}>
          <PerGroupTable headers={["Analyte code", "n", "Match rate"]} rows={perAnalyte.map((row) => [row.analyte_code, formatCount(row.n), formatNumber(row.match_rate, 3)])} />
        </Card>
        <p className="text-[11px] leading-4 text-ink-3">{String(result.caveat ?? "")}</p>
      </div>
    );
  }
  if (result.task_type === "ocr") {
    const pages = (result.per_page ?? []) as Array<{
      document_id_sha256: string;
      page: number;
      gold_characters: number;
      predicted_characters: number;
      character_edits: number;
      character_error_rate: number | null;
      gold_words: number;
      predicted_words: number;
      word_edits: number;
      word_error_rate: number | null;
      exact: boolean;
    }>;
    const artifacts = (result.input_artifacts ?? {}) as Record<string, { sha256?: string }>;
    const provenance = (result.provenance ?? {}) as Record<string, unknown>;
    const metric = (value: number | null | undefined) => value === null || value === undefined ? "Undefined" : formatNumber(value, 4);
    return (
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <Metric label="Character error rate" value={metric(result.metrics.character_error_rate)} note={`${formatCount(result.metrics.character_edits as number)} edits / ${formatCount(result.metrics.gold_characters as number)} gold characters`} />
          <Metric label="Word error rate" value={metric(result.metrics.word_error_rate)} note={`${formatCount(result.metrics.word_edits as number)} edits / ${formatCount(result.metrics.gold_words as number)} gold words`} />
          <Metric label="Exact-page rate" value={metric(result.metrics.exact_page_rate)} note={`${formatCount(result.metrics.exact_pages as number)} / ${formatCount(result.n)} pages`} />
          <Metric label="Pages" value={formatCount(result.n)} note={`${formatCount(result.n_groups)} pseudonymous documents`} />
          <Metric label="Raw text persisted" value={provenance.raw_text_persisted === false ? "No" : "Unknown"} />
        </div>
        <Card title="Per-page transcription agreement" padded={false}>
          <PerGroupTable
            headers={["Document digest", "Page", "Gold / predicted chars", "Character edits / CER", "Gold / predicted words", "Word edits / WER", "Exact"]}
            rows={pages.map((page) => [
              page.document_id_sha256.slice(0, 16),
              page.page,
              `${formatCount(page.gold_characters)} / ${formatCount(page.predicted_characters)}`,
              `${formatCount(page.character_edits)} / ${metric(page.character_error_rate)}`,
              `${formatCount(page.gold_words)} / ${formatCount(page.predicted_words)}`,
              `${formatCount(page.word_edits)} / ${metric(page.word_error_rate)}`,
              page.exact ? "Yes" : "No",
            ])}
          />
          {result.per_page_truncated === true && <p className="p-3 text-[11px] text-ink-3">Per-page rows are truncated; aggregate metrics and the page manifest cover the complete supplied partition.</p>}
        </Card>
        <Card title="OCR evaluation provenance">
          <KeyValue columns={3} items={[
            { label: "Gold artifact SHA-256", value: artifacts.gold?.sha256 ?? "—", mono: true },
            { label: "Prediction artifact SHA-256", value: artifacts.predictions?.sha256 ?? "—", mono: true },
            { label: "Page manifest SHA-256", value: String(provenance.page_manifest_sha256 ?? "—"), mono: true },
          ]} />
        </Card>
        <p className="text-[11px] leading-4 text-ink-3">{((result.assumptions as string[]) ?? []).join(" ")}</p>
      </div>
    );
  }
  if (result.task_type === "clinical_nlp") {
    type SpanScore = { tp: number; fp: number; fn: number; precision: number | null; recall: number | null; f1: number | null };
    type PerLabel = { label: string; gold_count: number; predicted_count: number; exact_span: SpanScore; overlap: SpanScore; context_errors: Record<"exact_span" | "overlap", Record<string, number>>; concept_link_errors: Record<"exact_span" | "overlap", number> };
    type ContextSummary = { evaluated: number; correct: number; errors: number; accuracy: number | null };
    type ConceptSummary = { evaluated: number; correct: number; missing: number; wrong: number; errors: number; accuracy: number | null; confusion: Array<{ gold: string; predicted: string; count: number }> };
    const exact = result.exact_span as SpanScore;
    const overlap = result.overlap as SpanScore;
    const perLabel = (result.per_label ?? []) as PerLabel[];
    const context = (result.context_confusion ?? {}) as Record<string, Record<string, ContextSummary>>;
    const concepts = (result.concept_linking ?? {}) as Record<"exact_span" | "overlap", ConceptSummary>;
    const labelConfusion = (result.label_confusion ?? []) as Array<{ gold: string; predicted: string; count: number }>;
    const documents = (result.documents ?? []) as Array<{ document_id_sha256: string; character_count: number; gold_spans: number; predicted_spans: number; exact_span: SpanScore; overlap: SpanScore }>;
    const artifacts = (result.input_artifacts ?? {}) as Record<string, { sha256?: string }>;
    const spanMetric = (value: number | null) => value === null ? "Undefined" : formatNumber(value, 3);
    const contextRows = Object.entries(context).flatMap(([mode, fields]) =>
      Object.entries(fields).map(([field, summary]) => [humanize(mode), humanize(field), formatCount(summary.evaluated), formatCount(summary.correct), formatCount(summary.errors), spanMetric(summary.accuracy)]),
    );
    return (
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
          <Metric label="Exact precision" value={spanMetric(exact.precision)} note={`${exact.tp} TP · ${exact.fp} FP`} />
          <Metric label="Exact recall" value={spanMetric(exact.recall)} note={`${exact.fn} FN`} />
          <Metric label="Exact F1" value={spanMetric(exact.f1)} />
          <Metric label="Overlap precision" value={spanMetric(overlap.precision)} note={`${overlap.tp} TP · ${overlap.fp} FP`} />
          <Metric label="Overlap recall" value={spanMetric(overlap.recall)} note={`${overlap.fn} FN`} />
          <Metric label="Overlap F1" value={spanMetric(overlap.f1)} />
        </div>
        <Card title="Per normalized label" padded={false}>
          <Table headers={["Label", "Gold", "Predicted", "Exact P / R / F1", "Overlap P / R / F1", "Overlap context errors", "Link errors"]} dense>
            {perLabel.map((row) => (
              <tr key={row.label}>
                <td className="font-mono text-xs text-ink">{row.label}</td>
                <td className="tabular">{formatCount(row.gold_count)}</td>
                <td className="tabular">{formatCount(row.predicted_count)}</td>
                <td className="tabular">{spanMetric(row.exact_span.precision)} / {spanMetric(row.exact_span.recall)} / {spanMetric(row.exact_span.f1)}</td>
                <td className="tabular">{spanMetric(row.overlap.precision)} / {spanMetric(row.overlap.recall)} / {spanMetric(row.overlap.f1)}</td>
                <td className="text-xs">{Object.entries(row.context_errors.overlap).map(([field, count]) => `${humanize(field)} ${count}`).join(" · ")}</td>
                <td className="tabular">{formatCount(row.concept_link_errors.overlap)}</td>
              </tr>
            ))}
          </Table>
        </Card>
        <div className="grid gap-4 xl:grid-cols-2">
          <Card title="Assertion, negation and temporality errors" padded={false}>
            <PerGroupTable headers={["Match", "Field", "Evaluated", "Correct", "Errors", "Accuracy"]} rows={contextRows} />
          </Card>
          <Card title="Label confusion on geometric overlaps" padded={false}>
            <PerGroupTable headers={["Gold label", "Predicted label", "Count"]} rows={labelConfusion.map((row) => [row.gold, row.predicted, formatCount(row.count)])} />
          </Card>
        </div>
        <Card title="Normalized terminology linking" eyebrow="Scored only where the gold span supplies code_system and concept_id">
          <KeyValue columns={2} items={(["exact_span", "overlap"] as const).flatMap((mode) => {
            const link = concepts[mode];
            return [
              { label: `${humanize(mode)} accuracy`, value: link ? spanMetric(link.accuracy) : "Undefined" },
              { label: `${humanize(mode)} counts`, value: link ? `${formatCount(link.correct)} correct · ${formatCount(link.missing)} missing · ${formatCount(link.wrong)} wrong · ${formatCount(link.evaluated)} evaluated` : "No gold concept links" },
            ];
          })} />
          {(concepts.overlap?.confusion ?? []).length > 0 && (
            <div className="mt-3 overflow-x-auto">
              <PerGroupTable headers={["Gold concept", "Predicted concept", "Count"]} rows={concepts.overlap.confusion.map((row) => [row.gold, row.predicted, formatCount(row.count)])} />
            </div>
          )}
        </Card>
        <Card title="Document/sample provenance">
          <KeyValue columns={3} items={[
            { label: "Documents", value: formatCount(result.n) },
            { label: "Gold spans", value: formatCount(result.gold_span_count as number) },
            { label: "Predicted spans", value: formatCount(result.predicted_span_count as number) },
            { label: "Gold artifact SHA-256", value: artifacts.gold?.sha256 ?? "—", mono: true },
            { label: "Prediction artifact SHA-256", value: artifacts.predictions?.sha256 ?? "—", mono: true },
            { label: "Document manifest SHA-256", value: String((result.provenance as Record<string, unknown>)?.document_manifest_sha256 ?? "—"), mono: true },
          ]} />
          {documents.length > 0 && (
            <div className="mt-3 overflow-x-auto">
              <PerGroupTable
                headers={["Document ID digest", "Characters", "Gold", "Predicted", "Exact F1", "Overlap F1"]}
                rows={documents.map((document) => [document.document_id_sha256.slice(0, 16), formatCount(document.character_count), formatCount(document.gold_spans), formatCount(document.predicted_spans), spanMetric(document.exact_span.f1), spanMetric(document.overlap.f1)])}
              />
            </div>
          )}
          {result.documents_truncated === true && <p className="mt-2 text-[11px] text-ink-3">Per-document rows are truncated; the manifest digest covers the complete supplied manifest.</p>}
        </Card>
        <p className="text-[11px] leading-4 text-ink-3">{((result.assumptions as string[]) ?? []).join(" ")}</p>
      </div>
    );
  }
  if (result.task_type === "detection") {
    const categories = (result.per_category ?? []) as Array<{ category_id: number; name: string; ap_50_95: number | null; reference_boxes: number }>;
    return (
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
          {[["map_50_95", "mAP @[.50:.95]"], ["ap_50", "AP @ .50"], ["ap_75", "AP @ .75"], ["ar_1", "AR @ 1"], ["ar_10", "AR @ 10"], ["ar_100", "AR @ 100"]].map(([key, label]) => <Metric key={key} label={label} value={result.metrics[key] === null ? "Undefined" : formatNumber(result.metrics[key], 3)} />)}
        </div>
        <Card title="Per category" padded={false}>
          <PerGroupTable headers={["Category", "Reference boxes", "AP @[.50:.95]"]} rows={categories.map((row) => [row.name, formatCount(row.reference_boxes), row.ap_50_95 === null ? "Undefined" : formatNumber(row.ap_50_95, 3)])} />
        </Card>
        <p className="text-[11px] leading-4 text-ink-3">{String(result.evaluation_protocol ?? "")}{Number(result.reference_area_derived_from_bbox) > 0 ? ` Area was derived from the box for ${formatCount(result.reference_area_derived_from_bbox as number)} reference annotation(s).` : ""}</p>
      </div>
    );
  }
  if (result.task_type === "segmentation_batch") {
    const pairs = (result.per_pair ?? []) as Array<{ patient_id: string; reference_mask: string; dice: number; iou: number; reference_empty: boolean; hausdorff_95: number | null }>;
    const unit = String((result.spacing as Record<string, unknown>)?.unit ?? "");
    return (
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <MetricWithInterval label="Mean Dice" value={result.metrics.mean_dice} interval={intervals.mean_dice} />
          <MetricWithInterval label="Mean IoU" value={result.metrics.mean_iou} interval={intervals.mean_iou} />
          <Metric label="Mean Dice, non-empty references" value={formatNumber(result.metrics.mean_dice_nonempty_reference, 3)} note={`${formatCount(result.metrics.n_nonempty_reference_masks as number)} non-empty · ${formatCount(result.metrics.n_empty_reference_masks as number)} empty`} />
          <Metric label="Mean IoU, non-empty references" value={formatNumber(result.metrics.mean_iou_nonempty_reference, 3)} />
          <Metric label="Mean HD95" value={formatNumber(result.metrics.mean_hausdorff_95, 3)} note={`${unit} · ${formatCount(result.metrics.n_pairs_with_surface_distance as number)} pairs`} />
        </div>
        <p className="text-[11px] leading-4 text-ink-3">{String(result.empty_mask_convention ?? "")}</p>
        <Card title="Per mask pair" padded={false}>
          <PerGroupTable headers={["Patient", "Reference mask", "Dice", "IoU", "HD95"]} rows={pairs.map((pair) => [pair.patient_id, pair.reference_mask + (pair.reference_empty ? " (empty)" : ""), formatNumber(pair.dice, 3), formatNumber(pair.iou, 3), pair.hausdorff_95 === null ? "—" : formatNumber(pair.hausdorff_95, 3)])} />
        </Card>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
        {["dice", "iou", "volumetric_similarity", "hausdorff", "hausdorff_95", "average_symmetric_surface_distance"].map((key) => <Metric key={key} label={humanize(key)} value={formatNumber(result.metrics[key], 3)} note={key.includes("haus") || key.includes("distance") ? String((result.spacing as Record<string, unknown>)?.unit ?? "") : undefined} />)}
      </div>
      {typeof result.empty_mask_convention === "string" && <p className="text-[11px] leading-4 text-ink-3">{result.empty_mask_convention}</p>}
    </div>
  );
}

function FileField({ label, hint, accept, onFile }: { label: string; hint?: string; accept: string; onFile: (file: File | null) => void }) {
  return (
    <Field label={label} hint={hint}>
      <input type="file" accept={accept} onChange={(event) => onFile(event.target.files?.[0] ?? null)} className={FILE_INPUT} />
    </Field>
  );
}

function EvaluateTab({ onResult }: { onResult: (result: EvaluationResult) => void }) {
  const [task, setTask] = useState<Task>("classification");
  const [file, setFile] = useState<File | null>(null);
  const [second, setSecond] = useState<File | null>(null);
  const [context, setContext] = useState<{ datasetId: string; datasetVersion: string; split: EvaluationSplit | ""; checkpoint: string; modelId: string }>({ datasetId: "", datasetVersion: "", split: "", checkpoint: "", modelId: "" });
  const [threshold, setThreshold] = useState("");
  const [alpha, setAlpha] = useState("");
  const [tolerance, setTolerance] = useState("0");
  const [spacing, setSpacing] = useState({ x: "1", y: "1", unit: "px" });
  const [deidentified, setDeidentified] = useState(false);
  const [independentlyAnnotated, setIndependentlyAnnotated] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pairTask = task === "segmentation" || task === "detection" || task === "clinical_nlp" || task === "ocr";
  const spacingTask = task === "segmentation" || task === "segmentation_batch";

  function chooseTask(next: Task) {
    setTask(next);
    setFile(null);
    setSecond(null);
    setDeidentified(false);
    setIndependentlyAnnotated(false);
  }

  async function run() {
    if (!file || (pairTask && !second)) return;
    setBusy(true);
    setError(null);
    const bound = { ...context, split: context.split || undefined };
    const pixel = { x: Number(spacing.x), y: Number(spacing.y), unit: spacing.unit };
    try {
      let result: EvaluationResult;
      if (task === "segmentation") result = await api.runSegmentationEvaluation(file, second!, pixel, bound);
      else if (task === "segmentation_batch") result = await api.runSegmentationBatchEvaluation(file, pixel, bound);
      else if (task === "detection") result = await api.runDetectionEvaluation(file, second!, bound);
      else if (task === "clinical_nlp") result = await api.runClinicalNlpEvaluation(file, second!, bound, { deidentified, independentlyAnnotated });
      else if (task === "ocr") result = await api.runOcrEvaluation(file, second!, bound, { deidentified, independentlyTranscribed: independentlyAnnotated });
      else result = await api.runEvaluation(task, file, { ...bound, threshold: threshold ? Number(threshold) : undefined, alpha: alpha ? Number(alpha) : undefined, absTolerance: task === "lab_extraction" ? Number(tolerance) : undefined });
      onResult(result);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Evaluate held-out predictions" eyebrow="Metrics are computed only from files you supply">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Field label="Task">
          <SelectInput data-testid="evaluation-task" value={task} onChange={(event) => chooseTask(event.target.value as Task)}>
            {(Object.keys(COLUMNS) as Task[]).map((key) => <option key={key} value={key}>{TASK_LABEL[key]}</option>)}
          </SelectInput>
        </Field>
        {task === "segmentation" && <><FileField label="Reference mask" hint={COLUMNS[task]} accept=".png,.npy" onFile={setFile} /><FileField label="Predicted mask" accept=".png,.npy" onFile={setSecond} /></>}
        {task === "segmentation_batch" && <FileField label="Mask archive (ZIP)" hint={COLUMNS[task]} accept=".zip" onFile={setFile} />}
        {task === "detection" && <><FileField label="Detections (COCO results JSON)" hint={COLUMNS[task]} accept=".json" onFile={setFile} /><FileField label="Reference (COCO annotations JSON)" accept=".json" onFile={setSecond} /></>}
        {task === "clinical_nlp" && <><FileField label="Gold entity spans (JSON)" hint={COLUMNS[task]} accept=".json,application/json" onFile={setFile} /><FileField label="Predicted entity spans (JSON)" accept=".json,application/json" onFile={setSecond} /></>}
        {task === "ocr" && <><FileField label="Independent page transcriptions (JSON)" hint={COLUMNS[task]} accept=".json,application/json" onFile={setFile} /><FileField label="OCR page predictions (JSON)" accept=".json,application/json" onFile={setSecond} /></>}
        {!spacingTask && task !== "detection" && task !== "clinical_nlp" && task !== "ocr" && <FileField key={task} label="Predictions (CSV)" hint={COLUMNS[task]} accept=".csv" onFile={setFile} />}
        {spacingTask && (
          <Field label="Pixel spacing (x, y, unit)">
            <div className="flex gap-1.5"><TextInput aria-label="Spacing x" value={spacing.x} onChange={(event) => setSpacing({ ...spacing, x: event.target.value })} /><TextInput aria-label="Spacing y" value={spacing.y} onChange={(event) => setSpacing({ ...spacing, y: event.target.value })} /><TextInput aria-label="Spacing unit" value={spacing.unit} onChange={(event) => setSpacing({ ...spacing, unit: event.target.value })} /></div>
          </Field>
        )}
        {task === "classification" && <Field label="Decision threshold" hint="Prespecified; defaults to 0.5 for probabilities"><TextInput value={threshold} onChange={(event) => setThreshold(event.target.value)} inputMode="decimal" /></Field>}
        {task === "regression" && <Field label="Interval alpha" hint="e.g. 0.1 for 90% intervals"><TextInput value={alpha} onChange={(event) => setAlpha(event.target.value)} inputMode="decimal" /></Field>}
        {task === "lab_extraction" && <Field label="Absolute tolerance" hint="In reference units, after verified unit normalisation"><TextInput value={tolerance} onChange={(event) => setTolerance(event.target.value)} inputMode="decimal" /></Field>}
      </div>

      {(task === "clinical_nlp" || task === "ocr") && (
        <div className="mt-4 grid gap-2 rounded-lg border border-line bg-surface-2 p-3 text-xs leading-5 text-ink-2 md:grid-cols-2">
          <label className="flex items-start gap-2">
            <input type="checkbox" checked={deidentified} onChange={(event) => setDeidentified(event.target.checked)} className="mt-1 accent-[var(--mt-accent)]" data-testid="nlp-deidentified-attestation" />
            <span><b className="font-medium text-ink">These artifacts contain de-identified research {task === "ocr" ? "transcriptions" : "annotations"} only.</b> Raw text and uploaded document identifiers are never copied into persisted results.</span>
          </label>
          <label className="flex items-start gap-2">
            <input type="checkbox" checked={independentlyAnnotated} onChange={(event) => setIndependentlyAnnotated(event.target.checked)} className="mt-1 accent-[var(--mt-accent)]" data-testid="nlp-independent-gold-attestation" />
            <span><b className="font-medium text-ink">The gold {task === "ocr" ? "text was independently transcribed from the rendered page" : "spans were independently annotated"}.</b> Model-generated pseudo-labels are not valid gold; this control scores supplied artifacts and does not run or train an extractor.</span>
          </label>
        </div>
      )}

      <div className="mt-4 grid gap-3 border-t border-line pt-4 md:grid-cols-2 xl:grid-cols-5">
        <Field label="Dataset ID"><TextInput value={context.datasetId} onChange={(event) => setContext({ ...context, datasetId: event.target.value })} placeholder="e.g. gi-endoscopy-8class" /></Field>
        <Field label="Dataset version" hint="Exact version from the local task audit"><TextInput value={context.datasetVersion} onChange={(event) => setContext({ ...context, datasetVersion: event.target.value })} placeholder="Full registered version" /></Field>
        <Field label="Split">
          <SelectInput value={context.split} onChange={(event) => setContext({ ...context, split: event.target.value as EvaluationSplit | "" })}>
            {SPLITS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </SelectInput>
        </Field>
        <Field label="Frozen checkpoint" hint="Exact sha256:&lt;64 lowercase hex&gt; registered for the model"><TextInput value={context.checkpoint} onChange={(event) => setContext({ ...context, checkpoint: event.target.value })} /></Field>
        <Field label="Model ID"><TextInput value={context.modelId} onChange={(event) => setContext({ ...context, modelId: event.target.value })} placeholder="Exact local registry ID" /></Field>
      </div>

      {error && <div className="mt-3"><ErrorBlock message={error} /></div>}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-xs leading-5 text-ink-3">Runs remain exploratory unless model ID, immutable checkpoint SHA-256, dataset ID/version, held-out split, and the uploaded evaluation bytes resolve exactly through the local model bundle, evaluation report, and dataset-task audit. Eligibility is research reporting provenance only, never clinical activation. Bootstrap intervals use 1,000 percentile resamples with a recorded seed, resampling patients when a patient or group column is present, and are withheld below 20 rows or 5 per class. File formats match MedTwin_2_Validation_Kit.</p>
        <Button variant="primary" icon={FlaskConical} loading={busy} disabled={!file || (pairTask && !second) || ((task === "clinical_nlp" || task === "ocr") && (!deidentified || !independentlyAnnotated))} onClick={() => void run()}>Compute metrics</Button>
      </div>
    </Card>
  );
}

function RunsTab({ onOpen }: { onOpen: (result: EvaluationResult) => void }) {
  const runs = useAsync(() => api.getEvaluationRuns(), []);
  if (!runs.data) return runs.error ? <ErrorBlock message={runs.error} /> : <LoadingBlock />;
  if (runs.data.length === 0) return <Unavailable code="NOT_AVAILABLE" reason="No evaluation has been run. No model in this workspace has held-out predictions yet." />;
  return (
    <Card title="Persisted evaluation runs" padded={false}>
      <Table headers={["Run", "Task", "Dataset", "Model", "Reporting", "n", "Input", "Created", ""]} dense>
        {runs.data.map((run) => (
          <tr key={run.run_id}>
            <td>#{run.run_id}</td><td>{humanize(run.task_type)}</td><td className="text-xs">{run.dataset_label ?? "—"}</td><td className="text-xs">{run.model_id ?? "—"}</td>
            <td><StatusBadge status={run.reporting_status === "ELIGIBLE_FOR_REPORTING" ? "VALID" : "EXPLORATORY"} label={run.reporting_status === "ELIGIBLE_FOR_REPORTING" ? "Reportable" : "Exploratory"} /></td>
            <td className="tabular">{formatCount(run.n_samples)}</td>
            <td className="max-w-[12rem] truncate text-xs" title={run.input_sha256}>{run.input_filename}</td><td className="text-xs">{formatDate(run.created_at, true)}</td>
            <td><Button size="sm" onClick={() => void api.getEvaluationRun(run.run_id).then(onOpen)}>Open</Button></td>
          </tr>
        ))}
      </Table>
    </Card>
  );
}

type EarlierEquation = { equation_id: string; title: string; implementation_module: string | null; status: string; measured_metric: { status: string; reason?: string } };

/** The earlier manuscript's Eq. 1–16 code map, kept for continuity with docs/integration/IEEE_TRACEABILITY.md. */
function EarlierEquationMap() {
  const map = useAsync(() => api.getIeeeValidationMetrics() as unknown as Promise<{ manuscript?: string; equations: EarlierEquation[] }>, []);
  if (map.error) return <ErrorBlock message={map.error} onRetry={map.reload} />;
  if (!map.data) return <LoadingBlock />;
  return (
    <Table headers={["Equation", "Title", "Module", "Status", "Measured"]} dense>
      {map.data.equations.map((equation) => (
        <tr key={equation.equation_id}>
          <td className="whitespace-nowrap font-mono text-[11px]">{equation.equation_id}</td><td className="text-xs text-ink">{equation.title}</td>
          <td className="max-w-[14rem] text-xs text-ink-2">{equation.implementation_module ?? "—"}</td><td><StatusBadge status={equation.status} /></td>
          <td className="max-w-sm text-[11px] text-ink-3">{humanize(equation.measured_metric.status)}{equation.measured_metric.reason ? `: ${equation.measured_metric.reason}` : ""}</td>
        </tr>
      ))}
    </Table>
  );
}

function TraceabilityTab() {
  const trace = useAsync(() => api.getTraceability(), []);
  const [status, setStatus] = useState("ALL");
  if (!trace.data) return trace.error ? <ErrorBlock message={trace.error} /> : <LoadingBlock />;
  if (trace.data.status === "NOT_AVAILABLE") return <Unavailable code="NOT_AVAILABLE" reason="docs/research/traceability.json has not been generated." />;
  const claims = trace.data.claims.filter((claim) => status === "ALL" || claim.status === status);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1.5">
        {["ALL", ...Object.keys(trace.data.status_counts ?? {})].map((value) => (
          <button key={value} type="button" onClick={() => setStatus(value)} aria-pressed={status === value}><Badge tone={status === value ? "accent" : "neutral"} icon={false}>{value === "ALL" ? `All (${trace.data!.claims.length})` : `${humanize(value)} (${trace.data!.status_counts?.[value]})`}</Badge></button>
        ))}
      </div>
      <Card title="Implementation-to-manuscript traceability" eyebrow={trace.data.manuscript} padded={false}>
        <Table headers={["ID", "Section", "Claim", "Module", "Status", "Evidence", "Gap"]} dense>
          {claims.map((claim) => (
            <tr key={claim.id}>
              <td className="font-mono text-[11px]">{claim.id}</td><td className="text-xs text-ink-2">{claim.section}</td><td className="max-w-sm text-xs text-ink">{claim.claim}</td>
              <td className="max-w-[12rem] text-xs text-ink-2">{claim.module}</td><td><StatusBadge status={claim.status} /></td>
              <td className="max-w-[14rem] text-[11px] text-ink-3">{claim.evidence.join("; ")}</td><td className="max-w-[14rem] text-[11px] text-ink-3">{claim.gap ?? "—"}</td>
            </tr>
          ))}
        </Table>
      </Card>
      <Disclosure summary="Earlier manuscript (MedTwin_IEEE_Manuscript_Final.docx, Eq. 1–16) equation map">
        <p className="mb-2 text-xs leading-5 text-ink-2">Equation numbering in the earlier manuscript differs from the revised draft above (Eq. 1–12). Kept for continuity with docs/integration/IEEE_TRACEABILITY.md.</p>
        <EarlierEquationMap />
      </Disclosure>
    </div>
  );
}

type Report = Record<string, unknown>;

function ciText(interval: unknown): string {
  const ci = interval as { status?: string; low?: number; high?: number } | undefined;
  return ci?.status === "COMPUTED" ? `95% CI ${formatNumber(ci.low, 3)}–${formatNumber(ci.high, 3)}` : "CI not computed";
}

function numbers(source: unknown, keys: string[]): Array<{ label: string; value: string }> {
  const record = (source ?? {}) as Record<string, unknown>;
  return keys.filter((key) => typeof record[key] === "number").map((key) => ({ label: humanize(key), value: formatNumber(record[key] as number, 3) }));
}

function MultilabelReport({ report }: { report: Report }) {
  const metrics = (report.metrics ?? {}) as Record<string, number>;
  const intervals = (report.confidence_intervals_95 ?? {}) as Record<string, unknown>;
  const perClass = (report.per_class ?? []) as Array<Record<string, unknown>>;
  const integrity = (report.integrity ?? {}) as Record<string, unknown>;
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-3">
        <Metric label="Macro AUROC" value={formatNumber(metrics.macro_auroc, 3)} note={`${ciText(intervals.macro_auroc)} · n ${formatCount(report.test_n as number)}`} />
        <Metric label="Macro AUPRC" value={formatNumber(metrics.macro_auprc, 3)} note="Mean over classes; prevalence-dependent" />
        <Metric label="Macro F1 at validation thresholds" value={formatNumber(metrics.macro_f1_at_validation_thresholds, 3)} note={ciText(intervals.macro_f1_at_validation_thresholds)} />
      </div>
      <Card title="Per class (test)" eyebrow="Thresholds chosen on the validation fold" padded={false}>
        <Table headers={["Class", "Positives", "Prevalence", "AUROC", "AUPRC", "Threshold", "Sensitivity", "Specificity", "PPV", "F1", "ECE raw → Platt"]} dense>
          {perClass.map((row) => (
            <tr key={String(row.class)}>
              <td className="text-ink">{String(row.class)}</td>
              <td className="tabular">{formatCount(row.positives as number)}</td>
              <td className="tabular">{formatNumber(row.prevalence as number, 3)}</td>
              <td className="tabular">{formatNumber(row.auroc as number, 3)}<span className="block text-[11px] text-ink-3">{ciText(row.auroc_95ci)}</span></td>
              <td className="tabular">{formatNumber(row.auprc as number, 3)}</td>
              <td className="tabular">{formatNumber(row.threshold_from_validation as number, 3)}</td>
              <td className="tabular">{formatNumber(row.sensitivity as number, 3)}</td>
              <td className="tabular">{formatNumber(row.specificity as number, 3)}</td>
              <td className="tabular">{formatNumber(row.ppv as number, 3)}</td>
              <td className="tabular">{formatNumber(row.f1 as number, 3)}</td>
              <td className="tabular">{formatNumber(row.ece_raw as number, 3)} → {formatNumber(row.ece_platt as number, 3)}</td>
            </tr>
          ))}
        </Table>
      </Card>
      {typeof integrity.files_verified === "number" && (
        <p className="text-[11px] leading-4 text-ink-3">Integrity: {formatCount(integrity.files_verified as number)} files verified against {String(integrity.against)}; {formatCount((integrity.leads_checksum_and_first_sample_verified as number) ?? 0)} leads checked against their header checksum and first sample.</p>
      )}
      {typeof report.benchmark_context === "string" && <p className="text-[11px] leading-4 text-ink-3">{publicText(report.benchmark_context)}</p>}
    </>
  );
}

function SurvivalReport({ report }: { report: Report }) {
  const metrics = (report.metrics ?? {}) as Record<string, unknown>;
  const intervals = (report.confidence_intervals_95 ?? {}) as Record<string, unknown>;
  const brier = (metrics.brier ?? {}) as Record<string, { model: number; kaplan_meier_reference: number }>;
  const calibration = (report.calibration ?? {}) as Record<string, Array<Record<string, number>>>;
  const ratios = (report.hazard_ratios ?? {}) as Record<string, { hr_per_sd: number; sd: number }>;
  const events = (report.events ?? {}) as Record<string, number>;
  const skill = metrics.integrated_brier_skill as number | null;
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-3">
        <Metric label="Harrell's C" value={formatNumber(metrics.harrell_c as number, 3)} note={`${ciText(intervals.harrell_c)} · n ${formatCount(report.test_n as number)} (${formatCount(events.test ?? 0)} deaths)`} />
        <Metric label="Integrated Brier score" value={formatNumber(metrics.integrated_brier_model as number, 3)} note={`Kaplan-Meier reference ${formatNumber(metrics.integrated_brier_kaplan_meier as number, 3)}; lower is better`} />
        <Metric label="Brier skill vs Kaplan-Meier" value={formatNumber(skill, 3)} note={skill !== null && skill > 0 ? "Better than the population average" : "No skill: absolute risks are no better than the population average"} />
      </div>
      <Card title="Brier score by horizon (held out, IPCW)" padded={false}>
        <Table headers={["Horizon (days)", "Model", "Kaplan-Meier reference"]} dense>
          {Object.entries(brier).map(([horizon, row]) => <tr key={horizon}><td className="tabular">{horizon}</td><td className="tabular">{formatNumber(row.model, 3)}</td><td className="tabular">{formatNumber(row.kaplan_meier_reference, 3)}</td></tr>)}
        </Table>
      </Card>
      <Card title="Calibration by predicted-risk tertile (held out)" padded={false}>
        <Table headers={["Horizon (days)", "Group", "n", "Deaths", "Mean predicted risk", "Observed risk (Kaplan-Meier)"]} dense>
          {Object.entries(calibration).flatMap(([horizon, rows]) => rows.map((row) => (
            <tr key={`${horizon}-${row.group}`}><td className="tabular">{horizon}</td><td className="tabular">{row.group}</td><td className="tabular">{row.n}</td><td className="tabular">{row.events}</td><td className="tabular">{formatNumber(row.mean_predicted_risk, 3)}</td><td className="tabular">{formatNumber(row.observed_risk_kaplan_meier, 3)}</td></tr>
          )))}
        </Table>
      </Card>
      <Card title="Hazard ratios (per standard deviation, development cohort)" padded={false}>
        <Table headers={["Covariate", "HR per SD", "SD"]} dense>
          {Object.entries(ratios).map(([name, row]) => <tr key={name}><td className="text-ink">{humanize(name)}</td><td className="tabular">{formatNumber(row.hr_per_sd, 3)}</td><td className="tabular">{formatNumber(row.sd, 3)}</td></tr>)}
        </Table>
      </Card>
    </>
  );
}

const CARDIAC_INDICES: Array<[string, string, string]> = [
  ["lv_edv_ml", "LV end-diastolic volume", "mL"], ["lv_esv_ml", "LV end-systolic volume", "mL"], ["lv_ef_percent", "LV ejection fraction", "%"],
  ["rv_edv_ml", "RV end-diastolic volume", "mL"], ["rv_esv_ml", "RV end-systolic volume", "mL"], ["rv_ef_percent", "RV ejection fraction", "%"],
  ["lv_myocardial_mass_g", "LV myocardial mass", "g"],
];

function VolumetricReport({ report }: { report: Report }) {
  const metrics = (report.metrics ?? {}) as Record<string, unknown>;
  const structures = (metrics.per_structure ?? {}) as Record<string, Record<string, number | null | Record<string, unknown>>>;
  const indices = (report.clinical_indices ?? {}) as Record<string, Record<string, unknown>>;
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-3">
        <Metric label="Mean case macro Dice" value={formatNumber(metrics.mean_case_macro_dice as number, 3)} note={`${ciText(metrics.mean_case_macro_dice_95ci)} · ${formatCount(report.test_patients as number)} patients, ${formatCount(report.test_n as number)} volumes`} />
        <Metric label="LV ejection fraction, mean absolute error" value={`${formatNumber(indices.lv_ef_percent?.mean_absolute_error as number, 1)} points`} note={ciText(indices.lv_ef_percent?.mean_absolute_error_95ci)} />
        <Metric label="LV ejection fraction, bias" value={`${formatNumber(indices.lv_ef_percent?.bias as number, 1)} points`} note="Predicted minus reference-mask value" />
      </div>
      <Card title="Structures (test volumes, end-diastole and end-systole)" padded={false}>
        <Table headers={["Structure", "Dice", "Dice ED", "Dice ES", "HD95 (mm)", "ASSD (mm)"]} dense>
          {Object.entries(structures).map(([name, row]) => (
            <tr key={name}>
              <td className="text-ink">{humanize(name)}</td>
              <td className="tabular">{formatNumber(row.mean_dice as number, 3)}<span className="block text-[11px] text-ink-3">{ciText(row.mean_dice_95ci)}</span></td>
              <td className="tabular">{formatNumber(row.mean_dice_ed as number, 3)}</td>
              <td className="tabular">{formatNumber(row.mean_dice_es as number, 3)}</td>
              <td className="tabular">{formatNumber(row.mean_hd95_mm as number, 1)}</td>
              <td className="tabular">{formatNumber(row.mean_assd_mm as number, 2)}</td>
            </tr>
          ))}
        </Table>
      </Card>
      <Card title="Cardiac indices from the segmentations (test patients)" eyebrow="Compared with the same indices from the reference masks" padded={false}>
        <Table headers={["Index", "Reference mean", "Predicted mean", "Bias", "95% limits of agreement", "Mean absolute error", "Pearson r"]} dense>
          {CARDIAC_INDICES.filter(([key]) => indices[key]).map(([key, label, unit]) => {
            const row = indices[key];
            const limits = (row.limits_of_agreement ?? []) as number[];
            return (
              <tr key={key}>
                <td className="text-ink">{label} ({unit})</td>
                <td className="tabular">{formatNumber(row.reference_mean as number, 1)}</td>
                <td className="tabular">{formatNumber(row.predicted_mean as number, 1)}</td>
                <td className="tabular">{formatNumber(row.bias as number, 1)}</td>
                <td className="tabular">{limits.length === 2 ? `${formatNumber(limits[0], 1)} to ${formatNumber(limits[1], 1)}` : "—"}</td>
                <td className="tabular">{formatNumber(row.mean_absolute_error as number, 1)}<span className="block text-[11px] text-ink-3">{ciText(row.mean_absolute_error_95ci)}</span></td>
                <td className="tabular">{formatNumber(row.pearson_r as number, 3)}</td>
              </tr>
            );
          })}
        </Table>
      </Card>
      {typeof report.spacing_note === "string" && <p className="text-[11px] leading-4 text-ink-3">{report.spacing_note}</p>}
    </>
  );
}

function TrainedModelReport({ modelId }: { modelId: string }) {
  const evaluation = useAsync(() => api.getResearchModelEvaluation(modelId), [modelId]);
  if (!evaluation.data) return evaluation.error ? <ErrorBlock message={evaluation.error} /> : <LoadingBlock label="Reading evaluation report" />;
  const report = evaluation.data.report;
  const license = (report.dataset_license ?? {}) as Record<string, unknown>;
  const checkpoint = (report.checkpoint ?? {}) as Record<string, unknown>;
  const test = (report.test ?? {}) as Report;
  const clean = (report.test_without_cross_split_duplicates ?? {}) as Report;
  const intervals = (report.confidence_intervals_95 ?? test.confidence_intervals_95 ?? {}) as Record<string, unknown>;
  const perClass = (report.per_class ?? []) as Array<Record<string, number | string>>;
  const operating = (report.operating_point ?? {}) as Record<string, Report>;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="warning">Research only · internal held-out evaluation</Badge>
        <StatusBadge status={evaluation.data.gate.allowed ? "RESEARCH_ONLY_UNVALIDATED" : "BLOCKED"} label={evaluation.data.gate.allowed ? "Research gate passed" : "Research gate blocked"} />
        <span className="text-xs text-ink-3">Run {runLabel(report.run_id)} · evaluated once on the frozen test split</span>
      </div>
      <Card title="Provenance">
        <KeyValue columns={2} items={[
          { label: "Dataset", value: `${datasetName(String(report.dataset_id ?? ""))} (version ${String(report.dataset_version).slice(0, 16)}…)` },
          { label: "Licence", value: <>{licenceLabel(license)} · <Link to="/attribution" className="text-accent-text hover:underline">Data sources and licences</Link></> },
          { label: "Split", value: publicText(String(report.split_method)) },
          { label: "Split counts", value: Object.entries((report.split_counts ?? {}) as Record<string, number>).map(([split, count]) => `${split} ${formatCount(count)}`).join(" · ") },
          { label: "Checkpoint SHA-256", value: String(checkpoint.sha256 ?? "—"), mono: true },
          { label: "Training time", value: typeof report.training_seconds === "number" ? `${formatNumber((report.training_seconds as number) / 60, 1)} min` : "—" },
        ]} />
      </Card>
      {report.task_type === "multilabel_classification" && <MultilabelReport report={report} />}
      {report.task_type === "survival" && <SurvivalReport report={report} />}
      {report.task_type === "volumetric_segmentation" && <VolumetricReport report={report} />}
      {report.metrics !== undefined && report.task_type !== "multilabel_classification" && report.task_type !== "survival" && report.task_type !== "volumetric_segmentation" && (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            {(["accuracy", "macro_f1", "balanced_accuracy"] as const).map((key) => (
              <Metric key={key} label={humanize(key)} value={formatNumber((report.metrics as Record<string, number>)[key], 3)} note={`${ciText(intervals[key])} · n ${formatCount(report.test_n as number)}`} />
            ))}
          </div>
          <Card title="Calibration and discrimination"><KeyValue columns={3} items={numbers(report.metrics, ["macro_auroc_one_vs_rest", "ece_uncalibrated", "ece_temperature_scaled", "brier_multiclass"])} /></Card>
          {Array.isArray(report.confusion_matrix) && <Card title="Confusion matrix (test)"><ConfusionMatrix labels={report.classes as string[]} matrix={report.confusion_matrix as number[][]} /></Card>}
          {perClass.length > 0 && (
            <Card title="Per class (test)" padded={false}>
              <Table headers={["Class", "Support", "Precision", "Recall", "F1", "AUROC (OvR)"]} dense>
                {perClass.map((row) => <tr key={String(row.class)}><td className="text-ink">{humanize(String(row.class))}</td><td className="tabular">{row.support}</td><td className="tabular">{formatNumber(row.precision as number, 3)}</td><td className="tabular">{formatNumber(row.recall as number, 3)}</td><td className="tabular">{formatNumber(row.f1 as number, 3)}</td><td className="tabular">{formatNumber(row.auroc_one_vs_rest as number, 3)}</td></tr>)}
              </Table>
            </Card>
          )}
        </>
      )}
      {test.metrics !== undefined && (
        <Card title={`Detection on the test split (n ${formatCount(test.n_images as number)} images, ${formatCount(test.reference_boxes as number)} reference boxes)`}>
          <KeyValue columns={3} items={[...numbers(test.metrics, ["map_50_95", "ap_50", "ap_75", "ar_100"]), ...numbers(operating.test, ["threshold", "precision", "recall", "f1"]).map((item) => ({ ...item, label: `Operating point: ${item.label}` }))]} />
          {clean.metrics !== undefined && <p className="mt-2 text-[11px] text-ink-3">Without test images that have a near-duplicate in another split (n {formatCount(clean.n_images as number)}): {numbers(clean.metrics, ["map_50_95", "ap_50"]).map((item) => `${item.label} ${item.value}`).join(" · ")}.</p>}
        </Card>
      )}
      {test.mean_foreground_dice_per_image !== undefined && (
        <Card title={`Segmentation on the test split (n ${formatCount(test.n_images as number)} images)`}>
          <KeyValue columns={3} items={[
            { label: "Mean foreground Dice per image", value: `${formatNumber(test.mean_foreground_dice_per_image as number, 3)} (${ciText(intervals.mean_foreground_dice_per_image)})` },
            { label: `Whole-${String(report.foreground_label ?? "vessel")} Dice`, value: `${formatNumber(test.vessel_dice as number, 3)} (${ciText(intervals.vessel_dice)})` },
            ...numbers(test, ["macro_segment_dice", "vessel_iou", "vessel_hd95_px_at_model_resolution"]),
          ]} />
          {clean.mean_foreground_dice_per_image !== undefined && <p className="mt-2 text-[11px] text-ink-3">Without near-duplicate test images (n {formatCount(clean.n_images as number)}): mean Dice {formatNumber(clean.mean_foreground_dice_per_image as number, 3)}.</p>}
        </Card>
      )}
      {Array.isArray(report.limitations) && <ul className="list-disc space-y-0.5 pl-4 text-xs leading-5 text-ink-2">{(report.limitations as string[]).map((item) => <li key={item}>{publicText(item)}</li>)}</ul>}
    </div>
  );
}

function TrainedModelsTab() {
  const listing = useAsync(() => api.getResearchModels(), []);
  const [modelId, setModelId] = useState("");
  if (!listing.data) return listing.error ? <ErrorBlock message={listing.error} /> : <LoadingBlock />;
  const models = listing.data.models;
  if (models.length === 0) return <Unavailable code="NO_TRAINED_MODEL" reason="No model trained in this workspace is registered." />;
  const active = models.find((model) => model.model_id === modelId) ?? models[0];
  return (
    <div className="space-y-3">
      <p className="text-sm text-ink-2">{listing.data.notice}</p>
      <div className="flex flex-wrap items-center gap-2">
        <div className="w-96"><SelectInput aria-label="Trained model" value={active.model_id} onChange={(event) => setModelId(event.target.value)}>{models.map((model) => <option key={model.model_id} value={model.model_id}>{model.display_name}{model.run_scope === "EXPLORATORY_ONLY" ? " (exploratory only)" : ""}</option>)}</SelectInput></div>
        {active.run_scope === "EXPLORATORY_ONLY" && <Badge tone="warning">Exploratory only: held-out evidence does not support use</Badge>}
        {active.inference_input === "tabular_survival" && <Badge tone="neutral">Evaluation evidence only: no upload inference path</Badge>}
        {active.inference_input === "ecg_12lead" && <Badge tone="neutral">Upload inference: digital WFDB/CSV records, from Multimodal</Badge>}
        {active.inference_input === "volume_nifti" && <Badge tone="neutral">Upload inference: single NIfTI frames inside the spacing envelope, from Medical Imaging</Badge>}
      </div>
      <TrainedModelReport key={active.model_id} modelId={active.model_id} />
    </div>
  );
}

function TestEvidenceTab() {
  const analytics = useAsync(() => api.getResearchAnalytics(), []);
  const evidence = analytics.data?.test_evidence as Record<string, unknown> | undefined;
  if (!analytics.data) return analytics.error ? <ErrorBlock message={analytics.error} /> : <LoadingBlock />;
  if (!evidence || evidence.status === "NOT_AVAILABLE") return <Unavailable code="NOT_AVAILABLE" reason={String(evidence?.reason ?? "")} />;
  const suites = (evidence.suites ?? []) as Array<Record<string, unknown>>;
  return (
    <Card title="Recorded test evidence" eyebrow={`Recorded ${formatDate(String(evidence.recorded_at), true)} · commit ${String(evidence.git_commit ?? "—").slice(0, 10)}`} padded={false}>
      <Table headers={["Suite", "Command", "Result", "Passed", "Failed", "Skipped", "Duration"]} dense>
        {suites.map((suite) => (
          <tr key={String(suite.name)}><td className="font-medium text-ink">{String(suite.name)}</td><td className="max-w-xs font-mono text-[11px] text-ink-2">{String(suite.command)}</td><td><StatusBadge status={String(suite.result)} /></td><td className="tabular">{String(suite.passed ?? "—")}</td><td className="tabular">{String(suite.failed ?? "—")}</td><td className="tabular">{String(suite.skipped ?? "—")}</td><td className="tabular">{suite.duration_seconds ? `${formatNumber(suite.duration_seconds as number, 1)} s` : "—"}</td></tr>
        ))}
      </Table>
    </Card>
  );
}

export default function ValidationCenterPage() {
  const [tab, setTab] = useState<"evaluate" | "runs" | "trained" | "traceability" | "tests">("evaluate");
  const [result, setResult] = useState<EvaluationResult | null>(null);
  return (
    <>
      <PageHeader
        eyebrow="Validation Center"
        title="Model evaluation, traceability and test evidence"
        description="Only task-appropriate metrics are computed, on held-out predictions you upload. A metric describes those predictions; it validates a model only when the data are genuinely held out and patient-level partitioned."
        actions={<Segmented label="Validation view" value={tab} onChange={setTab} options={[{ value: "evaluate", label: "Evaluate" }, { value: "runs", label: "Runs" }, { value: "trained", label: "Trained models" }, { value: "traceability", label: "Traceability" }, { value: "tests", label: "Test evidence" }]} />}
      />
      {tab === "evaluate" && <EvaluateTab onResult={setResult} />}
      {tab === "runs" && <RunsTab onOpen={(next) => { setResult(next); setTab("evaluate"); }} />}
      {tab === "trained" && <TrainedModelsTab />}
      {tab === "traceability" && <TraceabilityTab />}
      {tab === "tests" && <TestEvidenceTab />}
      {result && tab === "evaluate" && (
        <section className="mt-4 space-y-3">
          <p className="text-sm text-ink-2">Run #{result.run_id} · {humanize(result.task_type)} · n {formatCount(result.n)} · input SHA-256 <code className="text-xs">{result.input_sha256.slice(0, 16)}…</code></p>
          <ContextBanner result={result} />
          <ResultView result={result} />
        </section>
      )}
    </>
  );
}
