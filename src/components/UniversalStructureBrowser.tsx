import { useEffect, useRef, useState } from "react";
import { ChevronRight, ArrowLeft } from "lucide-react";
import { Badge, Button, Card, EmptyState, ErrorBlock, LoadingBlock, SelectInput, StatusBadge, TextInput } from "./ui";
import { universalJson } from "../services/universal";
import { useAsync } from "../lib/useAsync";

type Node = { id: string; label: string; kind: string; parent_id: string | null; parent_relation: string; system_ids: string[]; laterality: string | null; child_count: number; source_id: string; source: string; review_state: string; model_ids: string[] };
type Family = { id: string; label: string; structure_count: number };
type Detail = { node: Node; notice: string; supported_evidence_types: string[]; investigations: { id: string; label: string }[];
  concepts: { id: string; label: string }[]; assets: { id: string; label: string; local_available: boolean; commercial_use_declared: boolean }[];
  capabilities: { model_id: string; capability_state: string; research_gate: { blockers: string[] }; commercial_context_blocker: string | null }[];
  case_associations?: { items: { id: string; source_file_id: number | null }[]; level: string; diagnosis_inferred: false }; icd11: { state: string; blockers: string[]; crosswalk_blocker: string; sources: string[] } };

export default function UniversalStructureBrowser({ caseId = null, systemId = null, onSelect }: {
  caseId?: number | null; systemId?: string | null; onSelect?: (node: Node) => void;
}) {
  const [system, setSystem] = useState(systemId ?? "");
  const [parents, setParents] = useState<{ id: string; label: string }[]>([]);
  const [query, setQuery] = useState(""); const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const selectedParent = useRef<string | null>(null);
  useEffect(() => { setSystem(systemId ?? ""); setParents([]); setQuery(""); setOffset(0); if (selectedParent.current !== systemId) setSelected(null); selectedParent.current = null; }, [systemId]);
  useEffect(() => setSelected(null), [caseId]);
  const families = useAsync(() => universalJson<{ systems: Family[]; sources: Record<string, unknown>; icd11: Detail["icd11"] }>("/universal/structures/systems"), []);
  const parent = parents.at(-1);
  const rows = useAsync(() => {
    const params = new URLSearchParams({ q: query, limit: "40", offset: String(offset) });
    if (system && !parent) params.set("system", system);
    if (parent) params.set("parent_id", parent.id);
    return universalJson<{ items: Node[]; total: number; notice: string }>("/universal/structures?" + params);
  }, [system, parent?.id, query, offset]);
  const detail = useAsync(() => selected ? universalJson<Detail>(`/universal/structures/${encodeURIComponent(selected)}/detail${caseId ? `?case_id=${caseId}` : ""}`) : null, [selected, caseId]);
  const activeDetail = !detail.loading && detail.data?.node.id === selected ? detail.data : null;
  return <Card title="Whole-body structures & capability hierarchy" eyebrow="Source ancestry · L1 reference · no automatic diagnosis">
    <div className="grid gap-3 md:grid-cols-2"><label className="text-xs">System context<SelectInput aria-label="Structure hierarchy system" value={system} onChange={(e) => { setSystem(e.target.value); setParents([]); setOffset(0); setQuery(""); setSelected(null); }}><option value="">All25 systems</option>{families.data?.systems.map((item) => <option key={item.id} value={item.id}>{item.label} ({item.structure_count})</option>)}</SelectInput></label><label className="text-xs">Source labels<TextInput aria-label="Search structure hierarchy" maxLength={200} value={query} placeholder="Source name, Latin name or exact label" onChange={(e) => { setQuery(e.target.value); setOffset(0); }} /></label></div>
    <p className="mt-2 text-xs text-ink-3">System membership is navigation context. Source anatomical parents, asset components and registered model output classes remain distinct. Laterality appears only when the source records it.</p>
    {families.error && <ErrorBlock message={families.error} />}{rows.error && <ErrorBlock message={rows.error} onRetry={rows.reload} />}
    {parent && <div className="mt-3 flex flex-wrap items-center gap-2"><Button size="sm" onClick={() => { setParents((items) => items.slice(0, -1)); setOffset(0); setSelected(null); }}><ArrowLeft size={12} /> Back</Button><span className="break-all text-xs">{parents.map((item) => item.label).join(" / ")}</span></div>}
    <div className="mt-3 grid gap-4 lg:grid-cols-2"><div className="min-w-0">
      {rows.loading ? <LoadingBlock label="Reading source hierarchy" /> : <div className="max-h-80 space-y-1 overflow-auto">{rows.data?.items.map((node) => <div key={node.id} className="flex items-center gap-1 rounded-lg border border-line p-2"><button className="min-w-0 flex-1 text-left" onClick={() => { if (node.kind === "system") { setSystem(node.source_id); setParents([]); setOffset(0); } else { selectedParent.current = node.system_ids[0] ?? null; setSelected(node.id); onSelect?.(node); } }}><span className="block break-words text-xs font-medium">{node.label}{node.laterality ? ` (${node.laterality})` : ""}</span><span className="block text-[10px] text-ink-3">{node.kind} · {node.parent_relation}</span></button>{node.child_count > 0 && <Button size="sm" aria-label={`Browse children of ${node.label}`} onClick={() => { setParents((items) => [...items, { id: node.id, label: node.label }]); setOffset(0); setQuery(""); }}><ChevronRight size={12} /></Button>}</div>)}</div>}
      {!rows.loading && !rows.data?.items.length && <EmptyState title="No source-recorded entries in this context" detail="No missing anatomy, asset or diagnostic capability is fabricated." />}
      <div className="mt-2 flex items-center justify-between gap-2"><Button size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 40))}>Previous</Button><span className="text-xs text-ink-3">{rows.data?.total ?? 0} entries</span><Button size="sm" disabled={offset + 40 >= (rows.data?.total ?? 0)} onClick={() => setOffset(offset + 40)}>Next</Button></div>
    </div><div className="min-w-0 space-y-2 text-xs">{detail.error && <ErrorBlock message={detail.error} />}{detail.loading && <LoadingBlock label="Resolving source capability" />}{activeDetail ? <>
      <strong className="block text-sm">{activeDetail.node.label}</strong><Badge>{activeDetail.node.kind}</Badge><p className="break-all text-ink-3">Source: {activeDetail.node.source} · {activeDetail.node.source_id}</p><p>Parent relation: {activeDetail.node.parent_relation}. Laterality: {activeDetail.node.laterality ?? "not separately recorded"}.</p>
      <p>Evidence types: {activeDetail.supported_evidence_types.join(", ") || "No scoped source definition"}.</p>
      {activeDetail.assets.map((asset) => <p key={asset.id}>{asset.label}: {asset.local_available ? "local reference geometry present" : "local geometry unavailable"}; commercial permission {asset.commercial_use_declared ? "declared in existing manifest" : "requires source-specific review"}.</p>)}
      {activeDetail.capabilities.map((model) => <div key={model.model_id} className="rounded border border-line p-2"><p>{model.model_id}</p><StatusBadge status={model.capability_state} /><p className="break-words">{[...model.research_gate.blockers, model.commercial_context_blocker].filter(Boolean).join(" · ")}</p></div>)}
      {!activeDetail.capabilities.length && <p>No explicit model association is recorded for this source structure. Reference anatomy remains navigable.</p>}
      <details><summary className="cursor-pointer text-accent-text">System-context concepts and investigations</summary><p className="mt-1">{activeDetail.investigations.map((i) => i.label).join(", ") || "No specific investigation concept recorded"}</p><p className="mt-1">{activeDetail.concepts.map((c) => c.label).join(", ")}</p><p className="mt-1 text-ink-3">Contextual examples, not conditions detected at this structure.</p></details>
      {activeDetail.case_associations && <p>{activeDetail.case_associations.items.length} recorded source associations · {activeDetail.case_associations.level}. No exact structure diagnosis or registration inferred.</p>}
    </> : !detail.loading && <p className="text-ink-3">Select a source structure to inspect actual assets, registered classes, source concepts and current rights/model gates.</p>}</div></div>
    <details className="mt-4 text-xs"><summary className="cursor-pointer text-accent-text">ICD-11 source and mapping status</summary><p className="mt-2">{families.data?.icd11.state ?? "Loading source status"}</p><p className="mt-1">{families.data?.icd11.blockers.join(" · ")}</p><p className="mt-1">{families.data?.icd11.crosswalk_blocker}</p><p className="mt-1 text-ink-3">Official ICD-10-CM content remains separately labelled; no ICD-11 crosswalk is inferred.</p><a href="https://icd.who.int/docs/icd-api/license/" target="_blank" rel="noreferrer" className="mt-1 inline-block text-accent-text">WHO source licence and API requirements</a></details>
  </Card>;
}
