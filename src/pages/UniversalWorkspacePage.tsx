import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { ArrowUpRight, Bot, FileSearch, Network, Search, ShieldCheck } from "lucide-react";
import { Badge, Button, Card, EmptyState, ErrorBlock, LoadingBlock, PageHeader, SelectInput, StatusBadge, TextInput } from "../components/ui";
import { api, type ReportPageImage, type UploadedFile } from "../services/api";
import { universalJson } from "../services/universal";
import { useAsync } from "../lib/useAsync";
import { Link, navigate } from "../lib/router";
import { humanize, errorMessage } from "../lib/format";
import { useWorkspace } from "../state/workspace";
import { useUniversalSelection } from "../state/universalSelection";

const Imaging = lazy(() => import("../components/UniversalImagingWorkbench"));
const SourceResearch = lazy(() => import("../components/SelectedResearchSource"));
const AnatomyContext = lazy(() => import("../components/UniversalAnatomyContext"));
const CompletionResearch = lazy(() => import("../components/CompletionResearchPanel"));
const WordReview = lazy(() => import("../components/UprightWordReview"));
const TrustEvidence = lazy(() => import("../components/TrustEvidencePanel"));
const StructureBrowser = lazy(() => import("../components/UniversalStructureBrowser"));
type System = { id: string; label: string; synonyms: string[]; organs: string[]; atlas_system: string | null; condition_count: number };
type Concept = { id: string; label: string; kind: string; synonyms: string[]; evidence_types: string[]; capability_state: string; model_ids: string[] };
type Capability = { model_id: string; label: string; task: string; capability_state: string; research_gate: { allowed: boolean; blockers: string[] }; limitations: string[] };
type Node = { id: string; kind: string; label: string; source_file_id?: number | null; finding_id?: number | null; examination_id?: number | null; source_span?: string | null; source_page?: number | null; source_start?: number | null; source_end?: number | null; source_bbox?: number[] | null; assertion?: string | null; review_status?: string | null; timestamp?: string | null; details: Record<string, unknown> };
type Graph = { case_id: number; data_version: string; nodes: Node[]; edges: { id: string; source: string; target: string; relation: string }[]; conflicts: Record<string, unknown>[]; missing_modalities: string[]; truncated: boolean; notice: string };
type Answer = { status: string; answer: string; reason: string | null; mode: string; citations: { node_id: string; upload_id?: number | null; page?: number | null; span?: string | null }[]; actions: { type: "NAVIGATE"; path: string }[] };
const tools = ["search_case", "get_source", "get_examination", "get_model_provenance", "get_anatomy", "get_biomarker_history", "get_evaluation", "navigate_view", "draft_report"];
const destinations = new Set(["/universal", "/documents/verify", "/anatomy-studio", "/history", "/imaging", "/models", "/validation"]);

function SourcePreview({ upload, node }: { upload: UploadedFile | undefined; node: Node | undefined }) {
  const [preview, setPreview] = useState<ReportPageImage | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const page = node?.source_page ?? 1;
  useEffect(() => {
    let alive = true;
    let url: string | null = null;
    setPreview(null); setFailure(null);
    if (upload?.modality === "REPORT") void api.getReportPageImage(upload.id, page).then((result) => {
      url = result.url;
      if (alive) setPreview(result); else URL.revokeObjectURL(result.url);
    }).catch((error: unknown) => { if (alive) setFailure(errorMessage(error)); });
    return () => { alive = false; if (url) URL.revokeObjectURL(url); };
  }, [upload?.id, upload?.modality, page]);
  if (!upload) return <EmptyState icon={FileSearch} title="Select a source-linked observation" detail="Its exact source and review status will appear here." />;
  return <div className="space-y-3">
    <div className="flex flex-wrap items-center justify-between gap-2"><strong className="break-all text-sm">{upload.filename}</strong><Badge>Upload #{upload.id}</Badge></div>
    {node?.source_span && <blockquote className="whitespace-pre-wrap rounded-lg border-l-2 border-accent bg-accent-soft p-3 text-sm leading-6 text-ink">{node.source_span}</blockquote>}
    <div className="flex flex-wrap gap-2"><StatusBadge status={node?.assertion} /><StatusBadge status={node?.review_status} />{node?.details.active_evidence === false && <StatusBadge status="NOT_CURRENT_EVIDENCE" />}</div>
    {node?.source_start != null && <p className="text-xs text-ink-3">Source characters {node.source_start}–{node.source_end} · page {page}{node.source_bbox ? ` · source box ${node.source_bbox.join(", ")}` : " · no spatial box recorded"}</p>}
    {preview && <figure><Suspense fallback={<LoadingBlock label="Loading source word review" />}><WordReview key={`${upload.id}:${page}`} uploadId={upload.id} sha256={upload.file_hash} image={preview} /></Suspense><figcaption className="mt-1 text-xs text-ink-3">Original page {page}; use source verification to inspect boxes and submit a human correction.</figcaption></figure>}
    {upload.modality === "IMAGE" && /\.(png|jpe?g|bmp)$/i.test(upload.filename) && <Suspense fallback={<LoadingBlock label="Loading selected image evidence" />}><SourceResearch uploadId={upload.id} findingId={node?.finding_id ?? null} /></Suspense>}
    {failure && <ErrorBlock message={failure} />}
    <Link to={upload.modality === "REPORT" ? `/documents/verify?upload=${upload.id}` : "/imaging"} className="inline-flex items-center gap-1 text-sm text-accent-text hover:underline">Open source and reviewer controls <ArrowUpRight size={14} /></Link>
  </div>;
}

function EvidenceNetwork({ graph, selected, choose }: { graph: Graph; selected: string | null; choose: (node: Node) => void }) {
  const nodes = graph.nodes.slice(0, 48);
  const positions = new Map(nodes.map((node, index) => [node.id, { x: 75 + (index % 6) * 130, y: 32 + Math.floor(index / 6) * 48 }]));
  return <div className="space-y-2">
    <svg viewBox={`0 0 800 ${Math.max(130, Math.ceil(nodes.length / 6) * 48 + 22)}`} className="w-full rounded-lg border border-line bg-surface-2" aria-hidden="true" focusable="false">
      {graph.edges.map((edge) => { const a = positions.get(edge.source); const b = positions.get(edge.target); return a && b ? <line key={edge.id} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="currentColor" className="text-line-strong" strokeWidth={1}><title>{humanize(edge.relation)}</title></line> : null; })}
      {nodes.map((node) => { const p = positions.get(node.id)!; return <g key={node.id} onClick={() => choose(node)} className="cursor-pointer text-ink">
        <rect x={p.x - 59} y={p.y - 17} width={118} height={34} rx={7} fill={selected === node.id ? "var(--mt-accent-soft)" : "var(--mt-surface)"} stroke={selected === node.id ? "var(--mt-accent)" : "var(--mt-line-strong)"} strokeWidth={selected === node.id ? 2 : 1} />
        <text id={`graph-kind-${node.id}`} x={p.x} y={p.y - 2} textAnchor="middle" fill="currentColor" fontSize={8}>{humanize(node.kind)}</text><text id={`graph-label-${node.id}`} x={p.x} y={p.y + 10} textAnchor="middle" fill="currentColor" fontSize={9}>{node.label.slice(0, 21)}</text><desc id={`graph-desc-${node.id}`}>{node.label}</desc><title>{node.label}</title>
      </g>; })}
    </svg>
    <p className="text-xs text-ink-3">Source associations, not a causal disease model. Select a diagram item or use the full-text observation buttons below with a keyboard. {nodes.length} of {graph.nodes.length} nodes drawn; all nodes remain available in the evidence list. {graph.truncated && "Server limit reached; narrow the source review."}</p>
  </div>;
}

function CaseControlRoom({ caseId, system }: { caseId: number; system: System | undefined }) {
  const evidenceVersion = useWorkspace((state) => state.evidenceVersion);
  const uploads = useWorkspace((state) => state.evidence.uploads);
  const selection = useUniversalSelection();
  const [view, setView] = useState("twin");
  const [tool, setTool] = useState("search_case");
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [anatomyOpen, setAnatomyOpen] = useState(false);
  const requestTicket = useRef(0);
  useEffect(() => { requestTicket.current += 1; setAnswer(null); setFailure(null); setBusy(false); }, [tool, query, selection.sourceId, selection.findingId, selection.examId, selection.modelId, system?.id]);
  const graphState = useAsync(() => universalJson<Graph>(`/cases/${caseId}/evidence-graph`), [caseId, evidenceVersion]);
  const graph = graphState.data?.case_id === caseId && !graphState.loading ? graphState.data : null;
  const examsState = useAsync(() => api.getExaminations(caseId), [caseId, evidenceVersion]);
  const selected = graph?.nodes.find((node) => node.id === selection.nodeId);
  const selectedFinding = selected?.kind === "finding" ? selected : graph?.nodes.find((node) => node.kind === "finding" && node.finding_id === selected?.finding_id);
  const producedBy = graph?.edges.find((edge) => edge.target === selectedFinding?.id && edge.relation === "PRODUCED")?.source;
  const selectedRun = graph?.nodes.find((node) => node.id === producedBy);
  const anatomyIds = new Set(graph?.edges.filter((edge) => edge.source === selected?.id && edge.relation === "LEXICALLY_ASSOCIATED_WITH").map((edge) => edge.target) ?? []);
  const sourceAnatomy = graph?.nodes.filter((node) => anatomyIds.has(node.id)) ?? [];
  const biomarkers = [...new Map((graph?.nodes ?? []).filter((node) => node.kind === "measurement" && typeof node.details.name === "string" && typeof node.details.unit === "string").map((node) => [`${node.details.name}|${node.details.unit}`, { name: String(node.details.name), unit: String(node.details.unit) }])).values()];
  const filtered = graph?.nodes.filter((node) => selection.examId == null || node.examination_id === selection.examId || (node.kind === "examination" && node.id === `examination:${selection.examId}`)) ?? [];
  const source = uploads.find((upload) => upload.id === selection.sourceId && upload.case_id === caseId);
  const choose = (node: Node) => {
    const linked = graph?.edges.find((edge) => edge.source === node.id && edge.relation === "LEXICALLY_ASSOCIATED_WITH");
    const anatomy = graph?.nodes.find((item) => item.id === linked?.target);
    const parentFinding = node.kind === "finding" ? node : graph?.nodes.find((item) => item.kind === "finding" && item.finding_id === node.finding_id);
    const provenance = parentFinding?.details.model_provenance && typeof parentFinding.details.model_provenance === "object" ? parentFinding.details.model_provenance as Record<string, unknown> : {};
    const documentedDate = typeof node.details.documented_date === "string" ? node.details.documented_date : null;
    const examDate = examsState.data?.find((exam) => exam.id === node.examination_id)?.exam_date ?? null;
    selection.select({ nodeId: node.id, sourceId: node.source_file_id ?? parentFinding?.source_file_id ?? (node.kind === "upload" ? Number(node.id.split(":").at(-1)) : null), findingId: node.finding_id ?? null, examId: node.examination_id ?? null, timepoint: examDate ?? documentedDate, structureId: typeof anatomy?.details.system_id === "string" ? anatomy.details.system_id : typeof node.details.system_id === "string" ? node.details.system_id : typeof provenance.anatomy_system_of_model === "string" ? provenance.anatomy_system_of_model : null, modelId: typeof provenance.model_id === "string" ? provenance.model_id : typeof node.details.model_id === "string" ? node.details.model_id : null, seriesId: null, sliceIndex: null, overlayIds: [] });
    setAnswer(null);
  };
  const pinSource = (id: number) => { const node = graph?.nodes.find((item) => item.id === `upload:${id}`); if (node) choose(node); else selection.select({ sourceId: id, nodeId: `upload:${id}`, findingId: null, examId: null, timepoint: null, modelId: null, structureId: null, sliceIndex: null, overlayIds: [] }); };
  async function ask() {
    const ticket = ++requestTicket.current;
    setBusy(true); setFailure(null); setAnswer(null);
    try { const response = await universalJson<Answer>(`/cases/${caseId}/copilot/query`, { method: "POST", body: JSON.stringify({ tool, query, ...(selection.sourceId ? { source_id: selection.sourceId } : {}), ...(selection.findingId ? { finding_id: selection.findingId } : {}), ...(selection.examId ? { exam_id: selection.examId } : {}), ...(selection.modelId ? { model_id: selection.modelId } : {}), ...((selection.structureId || system?.atlas_system) ? { system_id: selection.structureId || system?.atlas_system } : {}) }) }); if (ticket === requestTicket.current) setAnswer(response); }
    catch (error) { if (ticket === requestTicket.current) setFailure(errorMessage(error)); } finally { if (ticket === requestTicket.current) setBusy(false); }
  }
  async function exportSnapshot() {
    if (!graph) return;
    const content = JSON.stringify({ kind: "RESEARCH_EVIDENCE_SNAPSHOT_NOT_APPROVED_REPORT", exported_at: new Date().toISOString(), graph, selection, assistant_draft: answer, clinical_activation: false }, null, 2);
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(content)))).map((v) => v.toString(16).padStart(2, "0")).join("");
    const url = URL.createObjectURL(new Blob([content], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `medtwin-case-${caseId}-${digest.slice(0, 12)}.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <div className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-surface p-3">
      <div className="flex flex-wrap gap-1" role="tablist" aria-label="Case workspace panels">{[["twin", "Twin Control Room"], ["evidence", "Evidence & sources"], ["spatial", "Spatial imaging"], ["history", "Time & comparison"]].map(([id, label], index, tabs) => <button key={id} role="tab" id={`workspace-tab-${id}`} aria-controls={`workspace-panel-${id}`} aria-selected={view === id} tabIndex={view === id ? 0 : -1} onClick={() => setView(id)} onKeyDown={(event) => { const direction = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0; if (direction || event.key === "Home" || event.key === "End") { event.preventDefault(); const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + direction + tabs.length) % tabs.length; setView(tabs[next][0]); document.getElementById(`workspace-tab-${tabs[next][0]}`)?.focus(); } }} className={`rounded-lg px-3 py-2 text-sm font-medium ${view === id ? "bg-accent-soft text-accent-text" : "text-ink-2 hover:bg-surface-2"}`}>{label}</button>)}</div>
      <Button size="sm" onClick={() => void exportSnapshot()} disabled={!graph}>Export evidence snapshot</Button>
    </div>
    {view !== "twin" && <div id="workspace-panel-twin" hidden />}{view !== "spatial" && <div id="workspace-panel-spatial" hidden />}{view !== "history" && <div id="workspace-panel-history" hidden />}{(view !== "evidence" || !graph) && <div id="workspace-panel-evidence" hidden />}
    {view === "twin" && <div role="tabpanel" id="workspace-panel-twin" aria-labelledby="workspace-tab-twin" className="space-y-4">
      <Card title="One case, synchronized evidence" eyebrow="Source scan · exact finding · anatomy context · observed history"><p className="text-sm text-ink-2">Select an observation below to pin its original source, recorded model and review state. A volumetric finding opens the source-coordinate 2D/3D workstation here. Generic anatomy remains in its independent frame.</p><div aria-live="polite" className="mt-3 rounded-lg border border-line bg-surface-2 p-3 text-xs"><strong>{selected?.label ?? "No observation selected"}</strong><p className="mt-1">{source ? `${source.filename} · upload #${source.id}` : "Select a source-linked finding"}{selection.examId ? ` · examination #${selection.examId}` : " · examination not linked"}{selection.timepoint ? ` · ${selection.timepoint}` : ""}</p></div></Card>
      {source?.modality === "IMAGE" && !/\.(png|jpe?g|bmp)$/i.test(source.filename) && <Suspense fallback={<LoadingBlock label="Loading patient-source 3D workspace" />}><Imaging key={`${caseId}:${source.id}`} caseId={caseId} uploadId={source.id} findingId={selection.findingId} onSelectUpload={pinSource} /></Suspense>}
      <div className="flex flex-wrap gap-2" aria-label="Synchronized examination timeline"><Button size="sm" onClick={() => selection.select({ examId: null, nodeId: null, sourceId: null, findingId: null, timepoint: null, modelId: null })}>All examination evidence</Button>{examsState.data?.map((exam) => <button key={exam.id} aria-pressed={selection.examId === exam.id} onClick={() => selection.select({ examId: exam.id, timepoint: exam.exam_date, sourceId: null, findingId: null, nodeId: null, modelId: null })} className="rounded-lg border border-line px-3 py-2 text-left text-xs">{exam.exam_date || "Date not recorded"} · #{exam.id}</button>)}</div>
      <Suspense fallback={<LoadingBlock label="Loading selected evidence trust context" />}><TrustEvidence key={`${caseId}:${selected?.id}`} selected={selected} finding={selectedFinding} run={selectedRun} /></Suspense>
    </div>}
    {view === "spatial" && <div role="tabpanel" id="workspace-panel-spatial" aria-labelledby="workspace-tab-spatial"><Suspense fallback={<LoadingBlock label="Loading spatial workstation" />}><Imaging caseId={caseId} uploadId={selection.sourceId} onSelectUpload={pinSource} /></Suspense></div>}
    {view === "history" && <div role="tabpanel" id="workspace-panel-history" aria-labelledby="workspace-tab-history"><Card title="Select a dated examination" eyebrow="Observed evidence">
      <div className="mb-3 flex flex-wrap gap-2"><Button size="sm" onClick={() => selection.select({ examId: null, nodeId: null, sourceId: null, findingId: null, timepoint: null })}>All timepoints</Button>{examsState.data?.map((exam) => <button key={exam.id} onClick={() => selection.select({ examId: exam.id, timepoint: exam.exam_date, sourceId: null, findingId: null, nodeId: null })} className={`rounded-lg border px-3 py-2 text-left text-xs ${selection.examId === exam.id ? "border-accent bg-accent-soft" : "border-line"}`}>{exam.exam_date || "Date not recorded"}<br />{exam.modality} · examination #{exam.id}</button>)}</div>
      {examsState.error && <ErrorBlock message={examsState.error} />}<p className="text-sm text-ink-2">Selecting a timepoint filters the source evidence below. Historical changes require compatible measurements and explicit comparison checks.</p>
      <div className="mt-3 flex flex-wrap gap-4 text-sm text-accent-text"><Link to="/history">Compare two examinations</Link><Link to="/biomarkers">Unit-aware biomarker trends</Link><Link to="/prognosis-studio">Forecast eligibility and research baselines</Link></div>
      <p className="mt-3 text-xs text-ink-3">Image difference overlays: REGISTRATION_UNAVAILABLE until the studies have a verified transform. Missing evidence is not a normal finding.</p>
    </Card><div className="mt-4"><Suspense fallback={<LoadingBlock label="Loading matched evidence research" />}><CompletionResearch key={`${caseId}:${selection.examId}`} caseId={caseId} examId={selection.examId} biomarkers={biomarkers} /></Suspense></div></div>}
    {graphState.error && <ErrorBlock message={graphState.error} onRetry={graphState.reload} />}
    {graphState.loading && <LoadingBlock label="Resolving case evidence" />}
    {graph && <div role={view === "evidence" ? "tabpanel" : undefined} id={view === "evidence" ? "workspace-panel-evidence" : undefined} aria-labelledby={view === "evidence" ? "workspace-tab-evidence" : undefined} className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <Card title="Evidence-to-source navigation" eyebrow={`${graph.nodes.length} nodes · ${graph.edges.length} recorded links`} actions={<Button size="sm" onClick={graphState.reload}>Refresh</Button>}>
          {view !== "spatial" && <EvidenceNetwork graph={graph} selected={selection.nodeId} choose={choose} />}
          <div className="mt-3 max-h-80 space-y-1 overflow-y-auto" aria-label="Case evidence observations">
            {filtered.map((node) => <button key={node.id} onClick={() => choose(node)} aria-pressed={selection.nodeId === node.id} className={`flex w-full flex-wrap items-start justify-between gap-2 rounded-lg border p-2 text-left ${selection.nodeId === node.id ? "border-accent bg-accent-soft" : "border-transparent hover:bg-surface-2"}`}><span className="min-w-0 flex-1"><span className="block text-[10px] uppercase tracking-wide text-ink-3">{humanize(node.kind)} · {node.id}</span><span className="block break-words text-xs text-ink">{node.label}</span></span>{node.review_status && <StatusBadge status={node.review_status} />}</button>)}
          </div>
          {!filtered.length && <EmptyState title="No evidence at this timepoint" />}
        </Card>
        <Card title="Selected source & review trail" eyebrow={selection.findingId ? `Finding #${selection.findingId}` : "Original evidence"}><SourcePreview key={`${caseId}:${selection.sourceId}:${selected?.id}`} upload={source} node={selected} />
          {typeof selected?.details.model_id === "string" && <div className="mt-3 rounded-lg bg-surface-2 p-3 text-xs"><p>Recorded model: {selected.details.model_id}</p><p className="mt-1 break-words">{JSON.stringify(selected.details)}</p><Link to="/arena" className="text-accent-text">Inspect checkpoint evaluation</Link></div>}
          <div className="mt-4 border-t border-line pt-3 text-xs text-ink-2"><p>Selected source association: {sourceAnatomy.length ? sourceAnatomy.map((node) => node.label).join(", ") : "not recorded"}</p><p className="mt-1">Browsing catalogue: {system?.label ?? "whole body"}. The evidence list covers the selected case.</p><Link to={`/anatomy-studio${selection.structureId || system?.atlas_system ? `?system=${encodeURIComponent(selection.structureId || system?.atlas_system || "")}` : ""}`} className="mt-1 inline-flex items-center gap-1 text-accent-text">Explore reference anatomy <ArrowUpRight size={12} /></Link><p className="mt-1">L1 generic reference; atlas coordinates do not establish patient-specific localization.</p></div>
          <div className="mt-3"><Button size="sm" aria-expanded={anatomyOpen} onClick={() => setAnatomyOpen(!anatomyOpen)}>{anatomyOpen ? "Hide" : "Show"} linked reference anatomy</Button>{anatomyOpen && <Suspense fallback={<LoadingBlock label="Loading linked anatomy" />}><AnatomyContext key={selection.structureId || system?.atlas_system} systemId={selection.structureId || system?.atlas_system || null} /></Suspense>}</div>
        </Card>
      </div>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,0.7fr)_minmax(0,1.3fr)]">
        <Card title="Uncertainty & reconciliation" eyebrow="No automatic diagnosis">
          <p className="text-sm text-ink-2">{graph.conflicts.length} recorded conflicts · {graph.missing_modalities.length ? `Missing: ${graph.missing_modalities.join(", ")}` : "All tracked modality classes represented"}</p>
          {graph.conflicts.map((conflict, i) => <div key={i} className="mt-2 rounded-lg border border-warning p-2 text-xs text-ink-2">{JSON.stringify(conflict)}</div>)}
          <p className="mt-3 text-xs leading-5 text-ink-3">{graph.notice}</p><p className="mt-2 break-all font-mono text-[10px] text-ink-3">Snapshot {graph.data_version}</p>
        </Card>
        <Card title={<span className="inline-flex items-center gap-2"><Bot size={16} /> Evidence copilot</span>} eyebrow="Local · deterministic · read only">
          <div className="grid gap-2 sm:grid-cols-[12rem_1fr]"><SelectInput aria-label="Copilot tool" value={tool} onChange={(e) => { setTool(e.target.value); setAnswer(null); }}>{tools.map((id) => <option key={id} value={id}>{humanize(id)}</option>)}</SelectInput><TextInput aria-label="Search case evidence" maxLength={1000} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search recorded evidence or request a cited draft" /></div>
          <div className="mt-2 flex flex-wrap items-center gap-3"><Button size="sm" variant="primary" loading={busy} onClick={() => void ask()}>Retrieve evidence</Button><span className="text-xs text-ink-3">Uses the selected source/finding. Corrections require the reviewer controls.</span></div>
          {failure && <div className="mt-2"><ErrorBlock message={failure} /></div>}{answer && <div className="mt-3 space-y-2 rounded-lg border border-line bg-surface-2 p-3"><StatusBadge status={answer.status} /><p className="whitespace-pre-wrap text-sm leading-6 text-ink">{answer.answer}</p>{answer.reason && <p className="text-xs text-ink-3">{answer.reason}</p>}<div className="flex flex-wrap gap-2">{answer.citations.map((citation, i) => <button key={i} className="rounded border border-line px-2 py-1 text-xs text-accent-text" onClick={() => { const node = graph.nodes.find((n) => n.id === citation.node_id); if (node) choose(node); }}>Source {citation.node_id}{citation.page ? ` · p${citation.page}` : ""}</button>)}</div>{answer.actions.filter((action) => { try { const url = new URL(action.path, "https://medtwin.invalid"); return action.path.startsWith("/") && !action.path.startsWith("//") && url.origin === "https://medtwin.invalid" && destinations.has(url.pathname); } catch { return false; } }).map((action, i) => <Button key={i} size="sm" onClick={() => navigate(action.path)}>Open cited workspace</Button>)}</div>}
        </Card>
      </div>
    </div>}
    {view === "twin" && <Suspense fallback={<LoadingBlock label="Loading synchronized history research" />}><CompletionResearch key={`${caseId}:${selection.examId}`} caseId={caseId} examId={selection.examId} biomarkers={biomarkers} /></Suspense>}
  </div>;
}

export default function UniversalWorkspacePage() {
  const caseId = useWorkspace((state) => state.caseId);
  const userId = useWorkspace((state) => state.user?.id);
  const [systemId, setSystemId] = useState("neurological");
  const [search, setSearch] = useState("");
  const [term, setTerm] = useState("");
  const [concept, setConcept] = useState<Concept | null>(null);
  const [structuresOpen, setStructuresOpen] = useState(false);
  const reset = useUniversalSelection((state) => state.reset);
  useEffect(() => { reset(caseId); return () => reset(); }, [caseId, userId, reset]);
  useEffect(() => { const timer = setTimeout(() => setTerm(search), 200); return () => clearTimeout(timer); }, [search]);
  const systems = useAsync(() => universalJson<{ systems: System[] }>("/universal/systems"), []);
  const terminology = useAsync(() => universalJson<{ available: boolean; state: string; entry_count: number; version: string; notice: string }>("/universal/terminology/status"), []);
  const catalogue = useAsync(() => universalJson<{ items: Concept[]; total: number; notice: string }>(`/universal/catalogue?system=${encodeURIComponent(systemId)}&q=${encodeURIComponent(term)}&limit=30`), [systemId, term]);
  const capabilities = useAsync(() => universalJson<{ items: Capability[] }>(`/universal/capabilities?system=${encodeURIComponent(systemId)}`), [systemId]);
  const system = useMemo(() => systems.data?.systems.find((item) => item.id === systemId), [systems.data, systemId]);
  return <>
    <PageHeader eyebrow="MedTwin Universal · research workspace" title="Case Command Center" description="Connect original evidence, anatomy, history and model provenance. Explore every body system; run only supported research workflows." actions={<Link to="/upload" className="inline-flex items-center gap-1 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white">Add case evidence <ArrowUpRight size={14} /></Link>} />
    <div className="mb-4 flex flex-wrap gap-2"><Badge tone="accent"><Network size={12} /> Evidence linked</Badge><Badge><ShieldCheck size={12} /> Clinical activation disabled</Badge><Badge>Catalogue ≠ diagnosis</Badge><Link to="/arena" className="ml-auto text-xs text-accent-text">Open Model Arena →</Link></div>
    {terminology.data && <div className="mb-4 rounded-xl border border-line bg-surface p-3 text-xs text-ink-2"><strong>Official classification reference: ICD-10-CM {terminology.data.version}</strong><span className="ml-2">{terminology.data.available ? `${terminology.data.entry_count.toLocaleString()} source entries indexed` : terminology.data.state}</span><p className="mt-1 leading-5 text-ink-3">{terminology.data.notice}</p></div>}
    <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[15rem_minmax(0,1fr)]">
      <aside className="min-w-0 space-y-3">
        <Card title="Whole-body systems" eyebrow="25 evidence workspaces"><label className="mb-2 flex items-center gap-2 text-xs text-ink-2"><Search size={14} /> Search selected system</label><TextInput aria-label="Search conditions and anatomy" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Condition, structure or synonym" />
          {systems.error && <ErrorBlock message={systems.error} onRetry={systems.reload} />}<div className="mt-3 flex max-h-[27rem] gap-1 overflow-auto xl:flex-col" role="group" aria-label="Body systems">{systems.data?.systems.map((item) => <button key={item.id} aria-pressed={systemId === item.id} onClick={() => { setSystemId(item.id); setConcept(null); setSearch(""); }} className={`min-w-40 rounded-lg px-3 py-2 text-left text-xs ${systemId === item.id ? "bg-accent-soft font-semibold text-accent-text" : "text-ink-2 hover:bg-surface-2"}`}>{item.label}<span className="ml-1 text-[10px]">{item.condition_count}</span></button>)}</div>
        </Card>
        <Card title={system?.label ?? "System catalogue"} eyebrow="Discoverable concepts">
          {catalogue.error && <ErrorBlock message={catalogue.error} onRetry={catalogue.reload} />}{catalogue.loading ? <LoadingBlock label="Searching catalogue" /> : <div className="max-h-64 space-y-1 overflow-auto">{catalogue.data?.items.map((item) => <button key={item.id} onClick={() => setConcept(item)} aria-pressed={concept?.id === item.id} className="block w-full rounded-lg p-2 text-left hover:bg-surface-2"><span className="block text-xs font-medium text-ink">{item.label}</span><span className="text-[10px] text-ink-3">{humanize(item.kind)}</span></button>)}</div>}<p className="mt-2 text-xs text-ink-3">{catalogue.data?.total ?? 0} matching entries. Progressive curated coverage; licensed terminology imports are versioned.</p>
          {concept && <div className="mt-3 space-y-2 border-t border-line pt-3"><strong className="text-sm">{concept.label}</strong><StatusBadge status={concept.capability_state} /><p className="text-xs text-ink-2">Evidence types: {concept.evidence_types?.join(", ") || "Not specified"}</p><p className="text-xs text-ink-3">Catalogue association supplies context; it does not authorize inference.</p></div>}
        </Card>
      </aside>
      <div className="min-w-0 space-y-4">
        <div><Button size="sm" aria-expanded={structuresOpen} onClick={() => setStructuresOpen(!structuresOpen)}>{structuresOpen ? "Hide" : "Browse"} source anatomy hierarchy</Button>{structuresOpen && <div className="mt-3"><Suspense fallback={<LoadingBlock label="Loading anatomy hierarchy" />}><StructureBrowser caseId={caseId} systemId={systemId} /></Suspense></div>}</div>
        <Card title={`${system?.label ?? "Selected system"} · capability status`} eyebrow="Bound to actual model registry">
          {capabilities.error && <ErrorBlock message={capabilities.error} onRetry={capabilities.reload} />}<div className="grid gap-2 md:grid-cols-2">{!capabilities.loading && !capabilities.data?.items.length && <EmptyState title="No registered research model for this system" detail="Catalogue, documents, history and anatomy remain available. No prediction is inferred from the absence of a model." />}{!capabilities.loading && capabilities.data?.items.map((model) => <div key={model.model_id} className="rounded-lg border border-line p-3"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-xs font-semibold">{model.label}</p><StatusBadge status={model.capability_state} /></div><p className="mt-1 text-xs text-ink-3">{humanize(model.task)}</p>{model.research_gate.blockers.length > 0 && <p className="mt-1 break-words text-[11px] text-ink-2">{model.research_gate.blockers.join(" · ")}</p>}<Link to="/imaging" className="mt-1 inline-block text-xs text-accent-text">Inspect input contract</Link></div>)}</div>
        </Card>
        {caseId ? <CaseControlRoom key={`${userId}:${caseId}`} caseId={caseId} system={system} /> : <EmptyState title="Select or create a research case" detail="Catalogue browsing is available now. A case binds private sources, graph, imaging and copilot to one authorized record." action={<Link to="/cases" className="text-accent-text">Open cases</Link>} />}
      </div>
    </div>
  </>;
}
