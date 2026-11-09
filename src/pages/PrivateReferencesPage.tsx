import { useEffect, useState } from "react";
import { Download, LockKeyhole } from "lucide-react";
import { Button, Card, LoadingBlock, PageHeader, StatusBadge, Table } from "../components/ui";
import { useAsync } from "../lib/useAsync";
import { api } from "../services/api";
import { Link } from "../lib/router";
import { useWorkspace } from "../state/workspace";
import type { ReferenceReport, SourceRef } from "../types/privateReferences";

function Preview({ study, asset, label }: { study: string; asset: string; label: string }) {
  const [url, setUrl] = useState<string>();
  const [error, setError] = useState<string>();
  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | undefined;
    void api.requestBlob(`/private-references/${encodeURIComponent(study)}/assets/${encodeURIComponent(asset)}`).then(({ blob }) => {
      if (cancelled) return;
      objectUrl = URL.createObjectURL(blob);
      setUrl(objectUrl);
    }).catch(() => { if (!cancelled) setError("This private source could not be opened. Try selecting the page again."); });
    return () => { cancelled = true; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [study, asset]);
  if (error) return <p role="alert" className="text-sm text-critical-text">{error}</p>;
  if (!url) return <LoadingBlock label="Opening private source" />;
  return <img src={url} alt={label} className="w-full rounded-lg border border-line" />;
}

function Report({ report }: { report: ReferenceReport }) {
  const [position, setPosition] = useState<SourceRef>({ source: report.sources[0].id, page: 1 });
  const source = report.sources.find((item) => item.id === position.source) ?? report.sources[0];
  const page = source.pages.find((item) => item.page === position.page) ?? source.pages[0];
  const [downloadError, setDownloadError] = useState<string>();
  const refs = (items: SourceRef[]) => <div className="mt-2 flex flex-wrap gap-1.5">{items.map((ref) => <button key={`${ref.source}-${ref.page}`} type="button" className="rounded border border-line px-2 py-1 text-xs text-accent-text hover:bg-accent-soft" onClick={() => setPosition(ref)} aria-label={`Show ${ref.source} page ${ref.page}`}>{ref.source} · p{ref.page}</button>)}</div>;
  const download = async () => {
    try {
      const fresh = await api.getPrivateReference(report.id);
      const url = URL.createObjectURL(new Blob([JSON.stringify(fresh, null, 2)], { type: "application/json" }));
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = `private-reference-${report.id}.json`; anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setDownloadError("The private report could not be downloaded."); }
  };
  return <>
    <Card title={report.title} eyebrow="Saved case report">
      <p className="text-sm leading-6 text-ink-2">{report.summary}</p>
      <div className="mt-3 flex flex-wrap gap-2"><StatusBadge status="SHA256_VERIFIED" /><StatusBadge status="PENDING_HUMAN_REVIEW" /><StatusBadge status="NOT_CLINICALLY_VALIDATED" /></div>
      <p className="mt-3 text-xs leading-5 text-ink-3">Original bytes verified · User-supplied records · No verified ground-truth labels · Excluded from training. These saved outputs describe the supplied records and do not establish current health or predict an individual outcome.</p>
      <Button className="mt-3" onClick={() => void download()}><Download size={14} /> Export private report</Button>
      {downloadError && <p role="alert">{downloadError}</p>}
    </Card>
    {report.conflicts.length > 0 && <Card title="Check before interpreting" eyebrow="Unresolved source differences"><ul className="list-disc space-y-2 pl-5 text-sm leading-6 text-ink-2">{report.conflicts.map((text) => <li key={text}>{text}</li>)}</ul></Card>}
    <div className="grid items-start gap-4 xl:grid-cols-[1fr_1fr]">
      <div className="space-y-4">
        <Card title="What the records report" eyebrow="Source-linked findings"><div className="space-y-5">{report.facts.map((fact) => <article key={fact.title}><h3 className="text-sm font-semibold text-ink">{fact.title}</h3><p className="mt-1 text-sm leading-6 text-ink-2">{fact.text}</p>{refs(fact.refs)}</article>)}</div></Card>
        <Card title="Timeline" eyebrow="Dates printed in the records"><ol className="space-y-5">{report.timeline.map((event, index) => <li key={index}><p className="text-xs font-medium text-accent-text">{event.date}</p><h3 className="mt-1 text-sm font-semibold text-ink">{event.title}</h3><p className="text-sm leading-6 text-ink-2">{event.text}</p>{refs(event.refs)}</li>)}</ol></Card>
      </div>
      <Card title="Source evidence" eyebrow="Private page viewer">
        <label htmlFor="reference-document" className="block text-xs text-ink-2">Document</label><select id="reference-document" className="mt-1 w-full rounded-lg border border-line bg-surface p-2 text-sm text-ink" value={source.id} onChange={(event) => setPosition({ source: event.target.value, page: 1 })}>{report.sources.map((item) => <option key={item.id} value={item.id}>{item.label} · {item.page_count} page(s)</option>)}</select>
        <div className="my-3 flex flex-wrap gap-1.5">{source.pages.map((item) => <button key={item.page} type="button" aria-pressed={item.page === page.page} className={`rounded border px-2.5 py-1 text-xs ${item.page === page.page ? "border-accent-text bg-accent-soft text-accent-text" : "border-line text-ink-2"}`} onClick={() => setPosition({ source: source.id, page: item.page })}>Page {item.page}</button>)}</div>
        <p className="mb-3 text-xs leading-5 text-ink-2">{page.description}</p>
        <Preview key={`${report.id}-${page.asset}`} study={report.id} asset={page.asset} label={`${source.label}, page ${page.page}`} />
        <details className="mt-3 text-xs text-ink-2"><summary className="cursor-pointer">Machine-read text · requires review</summary><p className="my-2">{page.ocr.engine} · {page.ocr.line_count} lines. OCR confidence is text recognition confidence, not diagnostic confidence.</p><pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded border border-line bg-surface-2 p-3">{page.ocr.text || "No readable text detected."}</pre></details>
        <details className="mt-3 text-xs text-ink-3"><summary className="cursor-pointer">Source integrity</summary><p className="mt-2 break-all">SHA-256: {source.sha256}</p><p className="mt-1">{source.bytes.toLocaleString()} bytes. Original and page previews contain identifiers and remain private.</p></details>
      </Card>
    </div>
    {report.measurements.length > 0 && <Card title="Reported measurements" eyebrow="Transcribed values · not model predictions" padded={false}><Table headers={["Measurement", "Result", "Date", "Printed interval / context", "Source"]}>{report.measurements.map((item, index) => <tr key={index}><td>{item.label}</td><td className="font-medium tabular">{item.value} {item.unit}</td><td>{item.date}</td><td>{item.interval}<span className="mt-1 block text-xs text-ink-3">{item.flag}</span></td><td>{refs(item.refs)}</td></tr>)}</Table></Card>}
    <Card title="Understanding and future comparison" eyebrow="Questions these records can help frame"><div className="grid gap-5 md:grid-cols-2">{report.insights.map((item) => <article key={item.title}><h3 className="text-sm font-semibold text-ink">{item.title}</h3><p className="mt-1 text-sm leading-6 text-ink-2">{item.text}</p>{refs(item.refs)}{item.links?.map((link) => <a key={link.url} href={link.url} target="_blank" rel="noreferrer" className="mt-2 block text-xs text-accent-text underline">{link.title}</a>)}</article>)}</div></Card>
    <Card title="Model and forecast availability" eyebrow="Organ + input + finding + model/version" padded={false}><Table headers={["Organ / test", "Target", "Model/version", "Result", "Reason"]}>{report.model_outputs.map((item, index) => <tr key={index}><td>{item.organ}<span className="block text-xs text-ink-3">{item.test}</span></td><td>{item.finding}</td><td>{item.model}</td><td><StatusBadge status={item.status} /></td><td className="max-w-sm text-xs leading-5">{item.reason}</td></tr>)}</Table></Card>
    <Card title="Limits and processing record"><ul className="list-disc space-y-2 pl-5 text-sm text-ink-2">{report.limitations.map((item) => <li key={item}>{item}</li>)}</ul><p className="mt-3 text-xs leading-5 text-ink-3">OCR: {report.processing.ocr_engine ?? "Unavailable"}. Renderer: {report.processing.renderer}. {report.processing.summary_method} Diagnostic models run: {report.processing.diagnostic_models_run.length}. Forecast: {report.processing.forecast_status}.</p></Card>
  </>;
}

function ReferenceLibrary({ owner }: { owner: number | undefined }) {
  const list = useAsync(() => api.getPrivateReferences(), [owner]);
  const [selected, setSelected] = useState<string>();
  const current = list.data?.find((item) => item.id === selected)?.id ?? list.data?.[0]?.id;
  const detail = useAsync(() => current ? api.getPrivateReference(current) : null, [owner, current]);
  return <div className="space-y-4">
    <PageHeader eyebrow="Private reference cases" title="Your saved case reports" description="Review the supplied records, source pages and prepared explanations together. These reports belong only to this account and are separate from shared cases and public demonstrations."><p className="mt-2 inline-flex items-center gap-2 text-xs text-ink-3"><LockKeyhole size={14} /> Encrypted local storage · Clinical review pending</p></PageHeader>
    <p className="text-sm text-ink-2">For sharing, open the <Link to="/examples" className="text-accent-text underline">public teaching examples</Link>. They use fictional names, records and values.</p>
    {list.loading && <LoadingBlock label="Loading private references" />}
    {list.error && <Card title="Private cases unavailable"><p role="alert" className="text-sm text-ink-2">{list.error}</p><Button onClick={list.reload}>Try again</Button></Card>}
    {list.data?.length === 0 && <Card title="No private reference cases for this account"><p className="text-sm text-ink-2">Sign in to the account that owns the imported references. Public demonstrations contain fictional records only.</p></Card>}
    <div className="grid gap-3 md:grid-cols-3">{list.data?.map((item) => <button key={item.id} type="button" onClick={() => setSelected(item.id)} aria-pressed={item.id === current} className={`rounded-xl border p-4 text-left ${item.id === current ? "border-accent-text bg-accent-soft" : "border-line bg-surface hover:bg-surface-2"}`}><p className="text-sm font-semibold text-ink">{item.title}</p><p className="mt-2 text-xs leading-5 text-ink-2">{item.summary}</p><p className="mt-3 text-xs text-ink-3">{item.source_count} source(s) · {item.page_count} page(s) · Review pending</p></button>)}</div>
    {detail.loading && <LoadingBlock label="Opening saved case report" />}
    {detail.error && <p role="alert" className="text-sm text-critical-text">{detail.error}</p>}
    {!detail.loading && detail.data && detail.data.id === current && <Report key={`${owner}-${current}`} report={detail.data} />}
  </div>;
}

export default function PrivateReferencesPage() {
  const owner = useWorkspace((state) => state.user?.id);
  // Changing accounts disposes source URLs and all report state immediately.
  return <ReferenceLibrary key={owner} owner={owner} />;
}
