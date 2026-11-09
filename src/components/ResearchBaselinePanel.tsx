import { useState } from "react";
import { api, type BaselineForecast } from "../services/api";
import { errorMessage, formatDate, formatNumber, humanize } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import { useWorkspace } from "../state/workspace";
import { Button, Card, ErrorBlock, Field, KeyValue, SelectInput, StatusBadge, Table, TextInput } from "./ui";

export default function ResearchBaselinePanel({ caseId }: { caseId: number }) {
  const history = useAsync(() => api.getForecastHistory(caseId), [caseId]);
  const measurements = useWorkspace((state) => state.evidence.measurements);
  const choices = [...new Map(measurements.map((m) => [`${m.name}|${m.unit}`, { name: m.name, label: m.display_name, unit: m.unit }])).values()];
  const [target, setTarget] = useState("");
  const [method, setMethod] = useState<"persistence" | "linear">("persistence");
  const [horizon, setHorizon] = useState(30);
  const [confirmed, setConfirmed] = useState(false);
  const [result, setResult] = useState<BaselineForecast | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const choice = choices.find((item) => `${item.name}|${item.unit}` === target);
  async function run() {
    if (!choice || !confirmed) return;
    setBusy(true); setError(null); setResult(null);
    try { setResult(await api.evaluateBaseline(caseId, choice.name, choice.unit, horizon, method)); history.reload(); }
    catch (err) { setError(errorMessage(err)); } finally { setBusy(false); }
  }
  return <Card title="Longitudinal research baselines" eyebrow="Reviewed measurements · chronological backtesting" className="mt-4">
    <p className="mb-4 text-sm text-ink-2">Persistence and linear trend use actual dated measurements after source review. A single CT study cannot support an individualized resolution forecast. Disease direction remains indeterminate without defined clinical criteria.</p>
    <div className="grid gap-3 md:grid-cols-[1.5fr_1fr_8rem_auto] md:items-end">
      <Field label="Observed variable"><SelectInput value={target} onChange={(event) => { setTarget(event.target.value); setResult(null); }}><option value="">Select a source-linked variable</option>{choices.map((item) => <option key={`${item.name}|${item.unit}`} value={`${item.name}|${item.unit}`}>{item.label} ({item.unit})</option>)}</SelectInput></Field>
      <Field label="Baseline"><SelectInput value={method} onChange={(event) => { setMethod(event.target.value as "persistence" | "linear"); setResult(null); }}><option value="persistence">Persistence (3+ reviewed dates)</option><option value="linear">Linear trend (5+ reviewed dates)</option></SelectInput></Field>
      <Field label="Horizon (days)"><TextInput type="number" min={1} max={3650} value={horizon} onChange={(event) => { setHorizon(Number(event.target.value)); setResult(null); }} /></Field>
      <Button loading={busy} disabled={!choice || !confirmed || horizon < 1 || horizon > 3650} onClick={() => void run()}>Evaluate baseline</Button>
    </div>
    <label className="mt-3 flex items-center gap-2 text-xs text-ink-2"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />I confirm that these historical observations belong to the same patient.</label>
    {!choices.length && <p className="mt-3 text-xs text-warning-text">Insufficient longitudinal evidence: no extracted numeric variables. Qualitative report findings cannot be turned into a numeric trajectory.</p>}
    {error && <div className="mt-3"><ErrorBlock message={error} /></div>}
    {history.error && <div className="mt-3"><ErrorBlock message={history.error} /></div>}
    {(history.data ?? []).length > 0 && <details className="mt-4 text-xs text-ink-2"><summary>Saved forecast evaluations ({history.data!.length})</summary><div className="mt-2"><Table headers={["Run", "Variable / horizon", "Status", "Research estimate"]} dense>{history.data!.map((row) => <tr key={row.id}><td>#{row.id}</td><td>{row.target_metric} · {row.horizon_days} d</td><td>{humanize(row.baseline_analysis?.status ?? row.eligibility_status)}</td><td>{row.predicted_value === null ? "Unavailable" : `${formatNumber(row.predicted_value)} ${row.unit}`}</td></tr>)}</Table></div></details>}
    {result && <div className="mt-4 space-y-3">
      <StatusBadge status={result.baseline_analysis.status} />
      <p className="text-sm text-ink-2">{result.notice}</p>
      {result.ineligibility_reason && <p className="text-sm text-warning-text">{result.ineligibility_reason}</p>}
      <KeyValue items={[
        { label: "Reviewed dated values", value: String(result.observations_count) },
        { label: "Research estimate", value: result.predicted_value === null ? "Unavailable" : `${formatNumber(result.predicted_value)} ${result.unit}` },
        { label: "Forecast date", value: result.baseline_analysis.forecast_date ? formatDate(result.baseline_analysis.forecast_date) : "Unavailable" },
        { label: "Validation", value: humanize(result.baseline_analysis.validation_status) },
        { label: "Version", value: result.baseline_analysis.version },
        { label: "Prediction interval", value: result.baseline_analysis.interval_reason },
        ...(result.baseline_analysis.backtest ? [
          { label: "Rolling-origin folds", value: String(result.baseline_analysis.backtest.folds.length) },
          { label: "Backtest MAE / RMSE", value: `${formatNumber(result.baseline_analysis.backtest.mae)} / ${formatNumber(result.baseline_analysis.backtest.rmse)} ${result.unit}` },
        ] : []),
      ]} />
      <Table headers={["Observed date", "Value", "Source"]} dense>{result.chronological_series.map((point) => <tr key={point.date}><td>{formatDate(point.date)}</td><td>{formatNumber(point.value)} {result.unit}</td><td className="max-w-lg text-xs text-ink-2">Upload #{point.upload_id} · “{point.source_span}”</td></tr>)}</Table>
    </div>}
  </Card>;
}
