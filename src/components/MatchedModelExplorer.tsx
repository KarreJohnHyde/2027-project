import { useEffect, useRef, useState } from "react";
import { Badge, Button, Card, EmptyState, ErrorBlock, LoadingBlock, SelectInput, StatusBadge, TextInput } from "./ui";
import { useAsync } from "../lib/useAsync";
import { humanize } from "../lib/format";
import { universalJson } from "../services/universal";
import { Link } from "../lib/router";

type Decision = { probability: number; predicted_label: number; error_type: string };
type RecordRow = { record_pseudonym: string; reference_label: number; left: Decision; right: Decision; decision_disagreement: boolean; absolute_probability_gap: number; missingness: { age_missing: boolean; sex_missing: boolean }; input_provenance: { status: string; header_sha256: string; waveform_sha256: string } };
type Model = { model_id: string; arm: string; threshold: number; threshold_source: string; probability_prefix: string; prediction_sha256: string; checkpoint_sha256: string | null; checkpoint_binding_status: string; associated_run_checkpoint_sha256: string; evaluation_url: string };
type Result = { status: string; reason: string | null; mode: string; label: string; snapshot_id: string | null; total: number; total_filtered: number; offset: number; limit: number; cohort: { records: number; patients: number; tuple_sha256: string; dataset_version: string; metadata_sha256: string }; models: { left?: Model; right?: Model }; rows: RecordRow[]; notice: string };
const labels = ["NORM", "MI", "STTC", "CD", "HYP"];

export default function MatchedModelExplorer() {
  const [mode, setMode] = useState("global");
  const [label, setLabel] = useState("NORM");
  const [order, setOrder] = useState("disagreement");
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [term, setTerm] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const pins = useRef(new Map<string, string>());
  const [revision, setRevision] = useState(0);
  const context = `${mode}:${label}`;
  const requestKey = JSON.stringify([mode, label, order, errorsOnly, term, offset, revision]);
  useEffect(() => { const timer = setTimeout(() => { setTerm(search); setOffset(0); }, 250); return () => clearTimeout(timer); }, [search]);
  const data = useAsync(() => universalJson<Result>("/universal/research/matched-records/query", { method: "POST", body: JSON.stringify({ mode, label, order, errors_only: errorsOnly, search: term, offset, limit: 10, ...(pins.current.get(context) ? { expected_snapshot_id: pins.current.get(context) } : {}) }) }).then((value) => ({ ...value, requestKey })), [mode, label, order, errorsOnly, term, offset, revision]);
  useEffect(() => { if (!data.loading && data.data?.requestKey === requestKey && data.data.status === "MATCHED_RECORDS_AVAILABLE" && data.data.snapshot_id) pins.current.set(context, data.data.snapshot_id); }, [data.data, data.loading, requestKey, context]);
  const result = !data.loading && search === term && data.data?.requestKey === requestKey ? data.data : null;
  const record = result?.rows.find((row) => row.record_pseudonym === selected);
  const left = result?.models.left;
  const right = result?.models.right;
  const reset = () => { setOffset(0); setSelected(null); };
  return <Card title="Same-input disagreement explorer" eyebrow="Matched public records · frozen decisions · read only">
    <p className="mb-3 text-xs leading-5 text-ink-2">Inspect two saved outputs for the same public ECG record and annotated label. Patient identifiers are withheld. Source bytes and matched reference tuples are checked before a page is shown. A model disagreement is a review question.</p>
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <label className="text-xs text-ink-2">Recorded comparison<SelectInput aria-label="Matched record comparison" value={mode} onChange={(event) => { setMode(event.target.value); reset(); }}><option value="global">Global ECG baseline versus fusion</option><option value="same_run">Same-run ECG-only versus fusion</option></SelectInput></label>
      <label className="text-xs text-ink-2">Annotated label<SelectInput aria-label="Matched record label" value={label} onChange={(event) => { setLabel(event.target.value); reset(); }}>{labels.map((value) => <option key={value}>{value}</option>)}</SelectInput></label>
      <label className="text-xs text-ink-2">Order<SelectInput aria-label="Matched record ordering" value={order} onChange={(event) => { setOrder(event.target.value); reset(); }}><option value="disagreement">Decision disagreements first</option><option value="errors">Reference errors first</option><option value="probability_gap">Largest score gap first</option></SelectInput></label>
      <label className="text-xs text-ink-2">Record pseudonym<TextInput aria-label="Search matched record pseudonyms" maxLength={64} value={search} onChange={(event) => { setSearch(event.target.value.replace(/[^a-zA-Z0-9_-]/g, "")); reset(); }} placeholder="ptb-…" /></label>
    </div>
    <label className="mt-3 flex items-center gap-2 text-xs text-ink-2"><input type="checkbox" checked={errorsOnly} onChange={(event) => { setErrorsOnly(event.target.checked); reset(); }} />Only records with a reference error in either output</label>
    {(data.loading || search !== term) && <LoadingBlock label="Verifying matched input records and source bytes" />}{data.error && <ErrorBlock message={data.error} onRetry={data.reload} />}
    {result && <div className="mt-4 space-y-3"><StatusBadge status={result.status} />{result.reason && <p className="text-xs text-ink-2">{humanize(result.reason)}</p>}
      {result.status === "SNAPSHOT_CHANGED" && <Button size="sm" onClick={() => { pins.current.delete(context); reset(); setRevision((value) => value + 1); }}>Refresh source snapshot</Button>}
      {result.status === "MATCHED_RECORDS_AVAILABLE" && <><div className="flex flex-wrap gap-2"><Badge>{result.cohort.records} matching records · {result.cohort.patients} patients</Badge><Badge>{result.total_filtered} records in this filter</Badge><Badge>Reference annotation ≠ diagnosis</Badge></div>
        <p className="text-xs text-ink-2">Baseline threshold {left?.threshold.toFixed(6)} · candidate threshold {right?.threshold.toFixed(6)}. Each decision uses score ≥ its own frozen validation threshold; scores are not clinical certainty.</p>
        <div className="overflow-x-auto"><table className="w-full text-left text-xs"><caption className="mb-2 text-left">Actual {label} reference and saved decisions, records {result.total_filtered ? result.offset + 1 : 0}–{Math.min(result.offset + result.rows.length, result.total_filtered)}</caption><thead><tr className="border-b border-line"><th scope="col" className="py-2 pr-3">Public record</th><th scope="col" className="pr-3">Reference label</th><th scope="col" className="pr-3">Baseline score / decision</th><th scope="col" className="pr-3">Candidate score / decision</th><th scope="col">Score gap</th></tr></thead><tbody>{result.rows.map((row) => <tr key={row.record_pseudonym} className="border-b border-line"><th scope="row" className="py-3 pr-3 font-normal"><button aria-label={`Inspect record ${row.record_pseudonym}`} className="font-mono text-[11px] text-accent-text underline" onClick={() => setSelected(row.record_pseudonym)}>{row.record_pseudonym}</button>{row.decision_disagreement && <span className="mt-1 block text-warning-text">Decision disagreement</span>}</th><td className="pr-3">{row.reference_label}</td>{[row.left, row.right].map((decision, index) => <td key={index} className="pr-3"><span className="font-mono">{decision.probability.toFixed(6)} / {decision.predicted_label}</span><span className="mt-1 block text-ink-3">{humanize(decision.error_type)}</span></td>)}<td className="font-mono">{row.absolute_probability_gap.toFixed(6)}</td></tr>)}</tbody></table></div>
        {!result.rows.length && <EmptyState title="No matching records" detail="Change the pseudonym search or error filter. No missing record is interpreted as a normal finding." />}
        <div className="flex items-center justify-between gap-2"><Button size="sm" disabled={offset === 0} onClick={() => { setOffset(Math.max(0, offset - 10)); setSelected(null); }}>Previous records</Button><Button size="sm" disabled={offset + result.rows.length >= result.total_filtered} onClick={() => { setOffset(offset + 10); setSelected(null); }}>Next records</Button></div>
        {record && <section aria-label="Selected matched record provenance" className="space-y-2 rounded-lg border border-line bg-surface-2 p-3 text-xs"><h3 className="font-semibold">{record.record_pseudonym} · source evidence</h3><p>Reference {label}: {record.reference_label}. Baseline {humanize(record.left.error_type)}; candidate {humanize(record.right.error_type)}.</p><p>Source metadata: age {record.missingness.age_missing ? "missing" : "present"}; sex {record.missingness.sex_missing ? "missing" : "present"}. Values and patient identifiers are withheld.</p><StatusBadge status={record.input_provenance.status} /><p className="break-all font-mono text-[10px]">Header SHA-256 {record.input_provenance.header_sha256}<br />Waveform SHA-256 {record.input_provenance.waveform_sha256}</p><p>Historical forward passes have not been replayed. The same-run ECG-only control checkpoint was not archived; its saved predictions and validation threshold remain inspectable.</p></section>}
        <details className="text-xs"><summary className="cursor-pointer text-accent-text">Inspect source artifact provenance</summary><div className="mt-2 space-y-3">{(["left", "right"] as const).map((side) => { const model = result.models[side]; return model ? <div key={side} className="space-y-1 rounded border border-line p-2"><strong>{side === "left" ? "Baseline" : "Candidate"} · {model.model_id} · {model.arm}</strong><p className="break-all font-mono text-[10px]">Prediction SHA-256 {model.prediction_sha256}<br />Checkpoint SHA-256 {model.checkpoint_sha256 ?? model.checkpoint_binding_status}</p><p>{humanize(model.threshold_source)}; stored columns {model.probability_prefix}.</p><Link to={model.evaluation_url} className="text-accent-text underline">Open recorded evaluation artifact</Link></div> : null; })}<p className="break-all font-mono text-[10px]">Tuple cohort SHA-256 {result.cohort.tuple_sha256}<br />Metadata SHA-256 {result.cohort.metadata_sha256}<br />Snapshot {result.snapshot_id}</p></div></details>
      </>}
      <p className="text-xs leading-5 text-ink-3">{result.notice}</p>
    </div>}
  </Card>;
}
