import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { universalJson } from "../services/universal";
import { useAsync } from "../lib/useAsync";
import { ErrorBlock, LoadingBlock, SelectInput, StatusBadge } from "./ui";

type Point = Record<string, number | null>;
type Label = { label: string; n: number; positives: number; curves: { status: string; roc: Point[]; pr: Point[]; auroc: number | null; average_precision: number | null }; reliability: { ece: number; brier: number; bins: { count: number; mean_probability: number | null; observed_frequency: number | null }[] }; binary_confusion: { tp: number; tn: number; fp: number; fn: number; threshold: number; threshold_source: string } };
type Diagnostic = { status: string; reason?: string; notice: string; n?: number; patient_count?: number; prediction_sha256?: string; per_class: Label[]; paired_arms?: { status: string; right_minus_left?: number; ci95?: [number, number]; conclusion?: string; patient_count?: number; record_count?: number } };

function Curve({ title, data, x, y }: { title: string; data: Point[]; x: string; y: string }) {
  return <figure className="min-w-0"><figcaption className="mb-1 text-xs font-medium">{title}</figcaption><div className="h-40" role="img" aria-label={`${title} from actual saved predictions`}><ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{ left: -20, right: 8, top: 8, bottom: 2 }}><CartesianGrid strokeDasharray="3 3" /><XAxis type="number" dataKey={x} domain={[0, 1]} tick={{ fontSize: 10 }} /><YAxis type="number" domain={[0, 1]} tick={{ fontSize: 10 }} /><Tooltip /><Line dataKey={y} type="linear" dot={false} stroke="var(--mt-accent)" strokeWidth={2} isAnimationActive={false} /></LineChart></ResponsiveContainer></div></figure>;
}

export default function ArenaDiagnostics({ modelId }: { modelId: string }) {
  const [selected, setSelected] = useState("");
  const data = useAsync(() => universalJson<Diagnostic>(`/universal/arena/models/${encodeURIComponent(modelId)}/diagnostics`), [modelId]);
  if (data.loading) return <LoadingBlock label="Computing source-bound research diagnostics" />;
  if (data.error) return <ErrorBlock message={data.error} />;
  const result = data.data;
  if (!result) return null;
  const item = result.per_class.find((label) => label.label === selected) ?? result.per_class[0];
  return <div className="mt-4 space-y-3 border-t border-line pt-3">
    <StatusBadge status={result.status} />{result.reason && <p className="break-words text-xs text-ink-2">{result.reason}</p>}
    {item && <><SelectInput aria-label={`Diagnostic class for ${modelId}`} value={item.label} onChange={(e) => setSelected(e.target.value)}>{result.per_class.map((label) => <option key={label.label} value={label.label}>{label.label} · {label.positives}/{label.n} positive references</option>)}</SelectInput>
      <div className="grid gap-3 sm:grid-cols-2"><Curve title="ROC · false-positive vs true-positive rate" data={item.curves.roc} x="fpr" y="tpr" /><Curve title="Precision–recall · recall vs precision" data={item.curves.pr} x="recall" y="precision" /></div>
      <p className="text-xs text-ink-2">AUROC {item.curves.auroc?.toFixed(5) ?? "unavailable"} · average precision {item.curves.average_precision?.toFixed(5) ?? "unavailable"} · ECE {item.reliability.ece.toFixed(5)} · Brier {item.reliability.brier.toFixed(5)}</p>
      <Curve title="Reliability · mean score vs observed frequency" data={item.reliability.bins.filter((bin) => bin.count > 0).map((bin) => ({ mean_probability: bin.mean_probability, observed_frequency: bin.observed_frequency }))} x="mean_probability" y="observed_frequency" />
      <table className="w-full text-left text-xs"><caption className="mb-2 text-left">Binary label counts at threshold {item.binary_confusion.threshold.toFixed(4)} · {item.binary_confusion.threshold_source}</caption><thead><tr><th scope="col" className="py-1">Reference / predicted</th><th scope="col">Positive</th><th scope="col">Negative</th></tr></thead><tbody><tr><th scope="row" className="py-1 font-normal">Positive reference</th><td>{item.binary_confusion.tp}</td><td>{item.binary_confusion.fn}</td></tr><tr><th scope="row" className="py-1 font-normal">Negative reference</th><td>{item.binary_confusion.fp}</td><td>{item.binary_confusion.tn}</td></tr></tbody></table>
      {result.paired_arms && <div className="rounded-lg border border-line bg-surface-2 p-3 text-xs"><strong>Same-run ECG-only versus fusion</strong><p className="mt-1">Patient-cluster delta {result.paired_arms.right_minus_left?.toFixed(6) ?? "unavailable"}; 95% interval {result.paired_arms.ci95?.map((n) => n.toFixed(6)).join(" to ") ?? "unavailable"}.</p><StatusBadge status={result.paired_arms.conclusion ?? result.paired_arms.status} /></div>}
      <p className="break-all font-mono text-[10px] text-ink-3">Prediction bytes SHA-256 {result.prediction_sha256}</p></>}
    <p className="text-xs leading-5 text-ink-3">{result.notice} Commercial source/computation gates apply separately from clinical validation. Curves are bounded for display; headline metrics use all rows.</p>
  </div>;
}
