import { useMemo, useState, type ReactNode } from "react";
import { anatomyEvidenceGroupKey, groupInOrder } from "../lib/findingGroups";
import {
  Activity,
  Box,
  Camera,
  Crosshair,
  Eye,
  EyeOff,
  Gauge,
  Layers,
  Maximize2,
  RotateCcw,
  Scan,
  Tag,
} from "lucide-react";
import type { AnatomyEvidenceItem, AnatomySystemEvidence, BiomarkerSeries, MappingState, ModelRegistryRecord, UploadedFile, Case, ReportStatement } from "../services/api";
import { BiomarkerTrendChart } from "../components/charts";
import { Badge, EmptyState, IconButton, KeyValue, Segmented, StatusBadge, TextInput, Unavailable } from "../components/ui";
import { Link } from "../lib/router";
import { formatBytes, formatCount, formatDate, formatNumber, humanize } from "../lib/format";
import type { ViewMode } from "./geometry";
import type { AnatomyManifest, AnatomySystem, AnatomyVariant, AtlasStructure, StructureEntry, TierName } from "./types";
import type { SectionState, TargetSummary } from "./AnatomyViewport";
import { useViewportStats } from "./viewportStats";

export const MAPPING_STYLE: Record<MappingState, { label: string; swatch: string; description: string }> = {
  SPATIALLY_REGISTERED: { label: "Spatially registered", swatch: "bg-map-spatial", description: "Validated image registration. None exists, so nothing is shown in this category." },
  REGION_VERIFIED: { label: "Region verified", swatch: "bg-map-verified", description: "Clinician-confirmed source statement naming a labelled atlas structure." },
  SCHEMATIC_ORGAN_ONLY: { label: "Schematic organ only", swatch: "bg-map-schematic", description: "Organ-level association only; carries no location." },
  NOT_MAPPABLE: { label: "Not mappable", swatch: "bg-map-unsupported", description: "No verified anatomical association is available." },
};

export function MappingLegend({ counts }: { counts?: Record<string, number> }) {
  return (
    <ul className="space-y-1.5">
      {Object.entries(MAPPING_STYLE).map(([code, style]) => (
        <li key={code} className="flex items-start gap-2 text-xs">
          <span aria-hidden className={`mt-0.5 h-3 w-3 shrink-0 rounded-sm ${style.swatch} ${code === "SCHEMATIC_ORGAN_ONLY" ? "ring-1 ring-dashed ring-[var(--mt-map-verified)]" : ""}`} />
          <span className="min-w-0">
            <span className="font-medium text-ink">{style.label}</span>
            {counts && <span className="ml-1 tabular text-ink-3">({counts[code] ?? 0})</span>}
            <span className="block text-[11px] leading-4 text-ink-3">{style.description}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

export function SystemList({ manifest, systemId, evidence, onSelect }: { manifest: AnatomyManifest; systemId: string; evidence?: Record<string, AnatomySystemEvidence>; onSelect: (id: string) => void }) {
  return (
    <ol className="space-y-0.5" aria-label="Anatomical systems">
      {manifest.systems.map((system) => {
        const count = evidence?.[system.id]?.items.length ?? 0;
        const active = system.id === systemId;
        return (
          <li key={system.id}>
            <button
              type="button"
              aria-current={active ? "true" : undefined}
              onClick={() => onSelect(system.id)}
              className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[13px] transition ${active ? "bg-surface font-medium text-ink shadow-card" : "text-ink-2 hover:bg-surface-2 hover:text-ink"}`}
            >
              <span className="w-5 shrink-0 text-[11px] tabular text-ink-3">{String(system.order).padStart(2, "0")}</span>
              <span className="min-w-0 flex-1 truncate">{system.label}</span>
              {count > 0 && <span className="rounded bg-surface-3 px-1.5 text-[11px] tabular text-ink-2" title="Case evidence items associated with this system">{count}</span>}
            </button>
          </li>
        );
      })}
    </ol>
  );
}

export function VariantList({ manifest, system, variantId, onSelect }: { manifest: AnatomyManifest; system: AnatomySystem; variantId: string; onSelect: (id: string) => void }) {
  return (
    <div className="space-y-1.5">
      {system.variants.map((id) => {
        const variant = manifest.variants[id];
        const active = id === variantId;
        const bytes = variant.tiers?.[variant.default_tier]?.bytes;
        return (
          <button
            type="button"
            key={id}
            onClick={() => onSelect(id)}
            aria-pressed={active}
            className={`block w-full rounded-lg border p-2.5 text-left transition ${active ? "border-[color-mix(in_srgb,var(--mt-accent)_50%,transparent)] bg-accent-soft" : "border-line bg-surface hover:bg-surface-2"}`}
          >
            <p className="text-xs font-medium leading-4 text-ink">{variant.label}</p>
            <div className="mt-1.5 flex flex-wrap gap-1">
              <Badge tone="neutral" icon={false}>{humanize(variant.role)}</Badge>
              <StatusBadge status={variant.license.class} label={variant.license.id} />
              {variant.kind === "ATLAS_REFERENCE" ? <Badge tone="info" icon={false}>{formatCount(variant.atlas?.structure_count)} named structures</Badge> : bytes ? <Badge tone="neutral" icon={false}>{formatBytes(bytes)}</Badge> : null}
            </div>
          </button>
        );
      })}
    </div>
  );
}

export function AssetStatus({ variant, tier, onTier }: { variant: AnatomyVariant; tier: TierName; onTier: (tier: TierName) => void }) {
  const tierInfo = variant.tiers?.[tier];
  const hasPreview = Boolean(variant.tiers?.preview);
  const stats = variant.statistics as Record<string, number | string | null>;
  return (
    <div className="space-y-3 text-xs">
      {variant.kind === "STANDALONE_ASSET" && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-ink-2">Detail tier</span>
          <Segmented size="sm" label="Detail tier" value={tier} onChange={onTier} options={[{ value: "standard", label: "Standard" }, { value: "preview", label: "Preview", disabled: !hasPreview, title: hasPreview ? undefined : "No reduced-detail tier for this asset" }]} />
        </div>
      )}
      {tierInfo?.geometry_changed && (
        <p className="rounded-md border border-[color-mix(in_srgb,var(--mt-warning)_45%,transparent)] bg-[color-mix(in_srgb,var(--mt-warning)_10%,transparent)] p-2 text-[11px] leading-4 text-warning-text">
          Reduced-detail preview: {formatNumber((tierInfo.triangle_ratio_vs_source ?? 0) * 100, 0)}% of source triangles (bounded simplification). Use Standard for inspection.
        </p>
      )}
      <KeyValue
        columns={1}
        items={[
          // Source titles, authors and file names are credited on the attribution page.
          { label: "Licence", value: variant.license.id },
          { label: "Attribution", value: <Link to="/attribution" className="text-accent-text hover:underline">Data sources and licences</Link> },
          ...(variant.kind === "STANDALONE_ASSET"
            ? [
                { label: "Source file size", value: formatBytes(variant.source.bytes) },
                { label: "Loaded tier", value: tierInfo ? `${formatBytes(tierInfo.bytes)} · ${formatCount(tierInfo.triangles || tierInfo.points)} ${tierInfo.points ? "points" : "triangles"}` : "—" },
                { label: "Structures", value: `${(variant.structures ?? []).length} (${variant.labelled_structures} labelled)` },
                { label: "Closed surfaces measured", value: String(stats.closed_primitives_measured ?? "—") },
              ]
            : [{ label: "Release", value: "Reference anatomical atlas 1.2.0 (preview channel)" }]),
          { label: "Registration", value: <StatusBadge status={variant.registration.status} /> },
        ]}
      />

      {variant.license.class !== "ATTRIBUTION" && variant.license.class !== "SHARE_ALIKE" && (
        <p className="text-[11px] leading-4 text-ink-3">Licence restriction: {humanize(variant.license.redistribution)}.</p>
      )}
      {[...(variant.repairs ?? []), ...variant.notes].map((note) => <p key={note} className="text-[11px] leading-4 text-ink-2">{note}</p>)}
    </div>
  );
}

type HierarchyEntry = { key: string; label: string; detail?: string; group: string };

export function HierarchyList({ entries, hidden, selectedKey, onToggle, onSelect, onShowAll }: { entries: HierarchyEntry[]; hidden: Set<string>; selectedKey: string | null; onToggle: (key: string) => void; onSelect: (key: string) => void; onShowAll: () => void }) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return needle ? entries.filter((entry) => entry.label.toLowerCase().includes(needle) || entry.group.toLowerCase().includes(needle)) : entries;
  }, [entries, query]);
  const groups = useMemo(() => {
    const map = new Map<string, HierarchyEntry[]>();
    for (const entry of filtered.slice(0, 400)) map.set(entry.group, [...(map.get(entry.group) ?? []), entry]);
    return [...map.entries()];
  }, [filtered]);
  if (entries.length === 0) return <p className="text-xs text-ink-3">Structures appear once the model loads.</p>;
  return (
    <div className="space-y-2">
      <div className="flex gap-1.5">
        <TextInput aria-label="Filter structures" placeholder={`Filter ${formatCount(entries.length)} structures`} value={query} onChange={(event) => setQuery(event.target.value)} className="h-8 text-xs" />
        {hidden.size > 0 && <IconButton label="Show all structures" icon={Eye} onClick={onShowAll} />}
      </div>
      <div className="max-h-[38vh] space-y-2 overflow-y-auto pr-1">
        {groups.map(([group, items]) => (
          <div key={group}>
            {groups.length > 1 && <p className="px-1 pb-0.5 text-[11px] font-medium text-ink-3">{group}</p>}
            <ul>
              {items.map((entry) => {
                const isHidden = hidden.has(entry.key);
                return (
                  <li key={entry.key} className={`group flex items-center gap-1 rounded-md ${entry.key === selectedKey ? "bg-accent-soft" : "hover:bg-surface-2"}`}>
                    <button type="button" aria-label={isHidden ? `Show ${entry.label}` : `Hide ${entry.label}`} onClick={() => onToggle(entry.key)} className="rounded p-1 text-ink-3 hover:text-ink">
                      {isHidden ? <EyeOff size={13} /> : <Eye size={13} />}
                    </button>
                    <button type="button" onClick={() => onSelect(entry.key)} className={`min-w-0 flex-1 truncate py-1 pr-1 text-left text-xs ${isHidden ? "text-ink-3 line-through" : "text-ink"}`} title={entry.detail ?? entry.label}>
                      {entry.label}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
        {filtered.length > 400 && <p className="px-1 text-[11px] text-ink-3">Showing 400 of {formatCount(filtered.length)}; refine the filter.</p>}
      </div>
    </div>
  );
}

export type ToolbarState = {
  viewMode: ViewMode;
  opacity: number;
  section: SectionState;
  isolate: boolean;
  labels: boolean;
  projection: "perspective" | "orthographic";
  showEvidence: boolean;
  showPerformance: boolean;
};

export function ViewerToolbar({ state, viewTypes, anatomicalAxes, interiorLabel, hasSelection, onChange, onReset, onScreenshot, onFullscreen }: {
  state: ToolbarState;
  viewTypes: string[];
  anatomicalAxes: boolean;
  interiorLabel: string | null;
  hasSelection: boolean;
  onChange: (patch: Partial<ToolbarState>) => void;
  onReset: () => void;
  onScreenshot: () => void;
  onFullscreen: () => void;
}) {
  const modeOptions: Array<{ value: ViewMode; label: string; disabled?: boolean; title?: string }> = [
    { value: "EXTERIOR", label: "Exterior" },
    { value: "INTERIOR", label: "Interior", disabled: !viewTypes.includes("INTERIOR"), title: viewTypes.includes("INTERIOR") ? undefined : "This asset has no internal structures to reveal" },
    { value: "TRANSPARENT", label: "Transparent", disabled: !viewTypes.includes("TRANSPARENT") },
    { value: "SECTION", label: "Section", disabled: !viewTypes.includes("SECTION") },
  ];
  const axisLabels = anatomicalAxes ? { x: "Sagittal (X)", y: "Transverse (Y)", z: "Coronal (Z)" } : { x: "X axis", y: "Y axis", z: "Z axis" };
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-line bg-surface px-3 py-2">
      <Segmented label="View mode" value={state.viewMode} onChange={(viewMode) => onChange({ viewMode })} options={modeOptions} size="sm" />
      {state.viewMode === "TRANSPARENT" && (
        <label className="flex items-center gap-2 text-[11px] text-ink-2">
          Opacity
          <input type="range" min={0.1} max={1} step={0.05} value={state.opacity} onChange={(event) => onChange({ opacity: Number(event.target.value) })} className="w-24 accent-[var(--mt-accent)]" aria-label="Opacity" />
          <span className="w-8 tabular">{Math.round(state.opacity * 100)}%</span>
        </label>
      )}
      {state.viewMode === "SECTION" && (
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-ink-2">
          <Segmented size="sm" label="Section plane" value={state.section.axis} onChange={(axis) => onChange({ section: { ...state.section, axis } })} options={(["x", "y", "z"] as const).map((axis) => ({ value: axis, label: axisLabels[axis] }))} />
          <input type="range" min={-1.05} max={1.05} step={0.01} value={state.section.offset} onChange={(event) => onChange({ section: { ...state.section, offset: Number(event.target.value) } })} className="w-28 accent-[var(--mt-accent)]" aria-label="Section position" />
          <button type="button" className="rounded border border-line px-1.5 py-0.5 hover:bg-surface-2" onClick={() => onChange({ section: { ...state.section, flip: !state.section.flip } })}>Flip</button>
        </div>
      )}
      {state.viewMode === "INTERIOR" && interiorLabel && <span className="text-[11px] text-ink-3">Translucent: {interiorLabel}</span>}
      <div className="ml-auto flex flex-wrap items-center gap-1">
        <IconButton label="Isolate selected structure" icon={Crosshair} active={state.isolate} disabled={!hasSelection} onClick={() => onChange({ isolate: !state.isolate })} />
        <IconButton label="Show structure labels" icon={Tag} active={state.labels} onClick={() => onChange({ labels: !state.labels })} />
        <IconButton label="Show evidence overlay" icon={Layers} active={state.showEvidence} onClick={() => onChange({ showEvidence: !state.showEvidence })} />
        <IconButton label={state.projection === "perspective" ? "Switch to orthographic" : "Switch to perspective"} icon={state.projection === "perspective" ? Box : Scan} active={state.projection === "orthographic"} onClick={() => onChange({ projection: state.projection === "perspective" ? "orthographic" : "perspective" })} />
        <IconButton label="Reset camera" icon={RotateCcw} onClick={onReset} />
        <IconButton label="Save screenshot" icon={Camera} onClick={onScreenshot} />
        <IconButton label="Fullscreen" icon={Maximize2} onClick={onFullscreen} />
        <IconButton label="Performance monitor" icon={Gauge} active={state.showPerformance} onClick={() => onChange({ showPerformance: !state.showPerformance })} />
      </div>
    </div>
  );
}

export function PerformanceOverlay() {
  const stats = useViewportStats((state) => state.stats);
  return (
    <div className="pointer-events-none absolute right-3 top-3 z-10 rounded-lg border border-white/10 bg-black/70 px-3 py-2 font-mono text-[11px] leading-5 text-white/90 backdrop-blur">
      {stats ? (
        <>
          <p>{stats.fps === null ? "—" : `${stats.fps.toFixed(0)} fps`} <span className="text-white/50">(on-demand)</span></p>
          <p>{formatCount(stats.calls)} draw calls · {formatCount(stats.triangles)} tris{stats.points > 0 ? ` · ${formatCount(stats.points)} points` : ""}</p>
          <p>{stats.geometries} geometries · {stats.textures} textures · {stats.programs} programs</p>
          {stats.heapMb !== null && <p>JS heap {stats.heapMb.toFixed(0)} MB</p>}
        </>
      ) : (
        <p>Interact with the model to sample frames.</p>
      )}
    </div>
  );
}

function EvidenceItem({ item, mentions = [item], onFocus }: { item: AnatomyEvidenceItem; mentions?: AnatomyEvidenceItem[]; onFocus?: (atlasId: string) => void }) {
  const style = MAPPING_STYLE[item.mapping_state];
  const atlasId = item.mapping_state === "REGION_VERIFIED" || item.mapping_state === "SPATIALLY_REGISTERED" ? item.atlas_structure_id : null;
  return (
    <li className="rounded-lg border border-line bg-surface p-2.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-medium text-ink">
            {item.label}{item.value !== undefined && <span className="tabular text-ink-2"> · {formatNumber(item.value)} {item.unit}</span>}
            {mentions.length > 1 && <span className="ml-1.5 text-[11px] font-normal text-ink-3">×{mentions.length} mentions in one report</span>}
          </p>
          <div className="mt-1 flex flex-wrap gap-1">
            <span className="inline-flex items-center gap-1 text-[11px] text-ink-2"><span aria-hidden className={`h-2 w-2 rounded-sm ${style.swatch}`} />{style.label}</span>
            {item.assertion && <StatusBadge status={item.assertion} />}
            {item.certainty && item.certainty !== "CERTAIN" && <StatusBadge status={item.certainty} />}
            {item.comparison && <Badge tone="info" icon={false}>{humanize(item.comparison)}</Badge>}
          </div>
        </div>
        {atlasId && onFocus && (
          <button type="button" className="shrink-0 rounded-md border border-line px-1.5 py-0.5 text-[11px] text-ink-2 hover:bg-surface-2" onClick={() => onFocus(atlasId)} title={atlasId}>
            Locate
          </button>
        )}
      </div>
      {[...new Set(mentions.map((mention) => mention.source_span).filter(Boolean))].map((span) => (
        <p key={span} className="mt-1.5 line-clamp-2 text-[11px] leading-4 text-ink-2">“{span}”</p>
      ))}
      {item.documented_region && <p className="mt-1 text-[11px] text-ink-3">Documented region: {item.documented_region}{item.mapping_state !== "REGION_VERIFIED" && item.candidate_atlas_structure_id ? " (awaiting clinician confirmation)" : ""}</p>}
      <p className="mt-1 text-[11px] leading-4 text-ink-3">{item.reason}</p>
    </li>
  );
}

export function Inspector({ selected, variant, structures, atlasStructure, atlasPath, evidence, hasCase, onFocusAtlas }: {
  selected: TargetSummary | null;
  variant: AnatomyVariant;
  structures: StructureEntry[];
  atlasStructure: AtlasStructure | null;
  atlasPath: string[];
  evidence: AnatomySystemEvidence | null;
  hasCase: boolean;
  onFocusAtlas: (atlasId: string) => void;
}) {
  const entry = selected ? structures.find((structure) => structure.id === selected.structureId) : undefined;
  const related = evidence?.items.filter((item) => !atlasStructure || ((item.mapping_state === "REGION_VERIFIED" || item.mapping_state === "SPATIALLY_REGISTERED") && item.atlas_structure_id === atlasStructure.id)) ?? [];
  const structureLinked = Boolean(atlasStructure) && related.length > 0;
  const items = structureLinked ? related : evidence?.items ?? [];
  return (
    <div className="space-y-4">
      <section>
        <p className="text-[11px] font-medium text-ink-3">Selected structure</p>
        {selected ? (
          <div className="mt-1.5 space-y-2">
            <p className="text-sm font-semibold text-ink">{selected.label}</p>
            {atlasStructure ? (
              <KeyValue
                columns={1}
                items={[
                  { label: "Latin", value: atlasStructure.name_la ?? "—" },
                  { label: "Laterality", value: atlasStructure.side ?? "Midline / not applicable" },
                  { label: "Hierarchy", value: atlasPath.join(" › ") },
                  { label: "Atlas review status", value: <StatusBadge status={atlasStructure.review.toUpperCase()} /> },
                  { label: "Structure ID", value: atlasStructure.id, mono: true },
                ]}
              />
            ) : entry ? (
              <KeyValue
                columns={1}
                items={[
                  { label: "Label provenance", value: <StatusBadge status={entry.label_source} label={humanize(entry.label_source)} /> },
                  { label: "Source name", value: entry.source_key, mono: true },
                  { label: "Review", value: <StatusBadge status={entry.review_status} /> },
                  { label: "Triangles", value: formatCount(entry.triangles) },
                  ...(entry.note ? [{ label: "Curator note", value: entry.note }] : []),
                ]}
              />
            ) : (
              <p className="text-xs text-ink-2">Geometry not assigned to a manifest structure.</p>
            )}
          </div>
        ) : (
          <p className="mt-1.5 text-xs leading-5 text-ink-2">Click a structure in the model or the hierarchy. Labels carry their provenance; generic segments are never given anatomical names they do not have.</p>
        )}
      </section>

      <section>
        <div className="flex items-center justify-between gap-2">
          <p className="text-[11px] font-medium text-ink-3">{structureLinked ? "Evidence for this structure" : "Case evidence for this system"}</p>
          {evidence && <span className="text-[11px] tabular text-ink-3">{items.length}</span>}
        </div>
        <div className="mt-1.5">
          {!hasCase ? (
            <p className="text-xs text-ink-2">Select a case to see its evidence mapped to this system.</p>
          ) : !evidence ? (
            <p className="text-xs text-ink-2">Loading evidence…</p>
          ) : items.length === 0 ? (
            <p className="text-xs text-ink-2">No case evidence is associated with this system.</p>
          ) : (
            <ul className="space-y-1.5">{groupInOrder(items, anatomyEvidenceGroupKey).slice(0, 40).map(({ key, first, members }) => <EvidenceItem key={key} item={first} mentions={members} onFocus={variant.kind === "ATLAS_REFERENCE" || variant.system_id === "hybrid" ? onFocusAtlas : undefined} />)}</ul>
          )}
          {selected && !atlasStructure && evidence && evidence.items.length > 0 && (
            <p className="mt-2 text-[11px] leading-4 text-ink-3">This asset's segments are not linked to atlas terminology, so evidence is shown at organ level. Open the atlas variant to locate documented regions.</p>
          )}
        </div>
      </section>

      <section>
        <p className="mb-1.5 text-[11px] font-medium text-ink-3">Mapping categories</p>
        <MappingLegend counts={evidence?.state_counts} />
        {(evidence?.highlight.documented_structures?.length ?? 0) > 0 && (
          <p className="mt-1.5 flex items-start gap-2 text-xs">
            <span aria-hidden className="mt-0.5 h-3 w-3 shrink-0 rounded-sm bg-[#ff6a00]" />
            <span className="min-w-0">
              <span className="font-medium text-ink">Named in a report, unconfirmed</span>
              <span className="ml-1 tabular text-ink-3">({evidence?.highlight.documented_structures?.length} structures)</span>
              <span className="block text-[11px] leading-4 text-ink-3">Orange in the model: atlas structures an affirmed report statement names (for example "bilateral lower lobes"). Orientation only until a clinician confirms the region; not a located finding.</span>
            </span>
          </p>
        )}
      </section>
    </div>
  );
}

type BottomTab = "imaging" | "labs" | "history" | "models";

export function StudioBottomPanel({ systemId, caseRecord, uploads, statements, series, models }: {
  systemId: string;
  caseRecord: Case | null;
  uploads: UploadedFile[];
  statements: ReportStatement[];
  series: BiomarkerSeries[] | null;
  models: ModelRegistryRecord[];
}) {
  const [tab, setTab] = useState<BottomTab>("imaging");
  const images = uploads.filter((upload) => upload.modality === "IMAGE");
  const exams = new Map(caseRecord?.examinations.map((exam) => [exam.id, exam]) ?? []);
  const systemSeries = (series ?? []).filter((item) => systemId === "hybrid" || item.anatomy_system === systemId);
  const changes = statements.filter((statement) => statement.comparison && (systemId === "hybrid" || statement.anatomy_system === systemId));
  const relevantModels = models.filter((model) => systemId === "hybrid" || model.anatomy.toLowerCase().includes(systemId.replace(/s$/, "")));
  let body: ReactNode;
  if (!caseRecord && tab !== "models") {
    body = <p className="text-xs text-ink-2">Select a case to see its imaging, laboratory and historical evidence.</p>;
  } else if (tab === "imaging") {
    body = images.length === 0 ? <p className="text-xs text-ink-2">No imaging uploads in this case.</p> : (
      <ol className="flex gap-2 overflow-x-auto pb-1">
        {images.map((upload) => {
          const exam = upload.examination_id ? exams.get(upload.examination_id) : undefined;
          return (
            <li key={upload.id} className="w-48 shrink-0 rounded-lg border border-line bg-surface p-2.5">
              <p className="truncate text-xs font-medium text-ink" title={upload.filename}>{upload.filename}</p>
              <p className="mt-0.5 text-[11px] text-ink-3">{exam ? formatDate(exam.exam_date) : "Undated (no examination link)"}</p>
              <Link to={`/imaging?upload=${upload.id}`} className="mt-1.5 inline-block text-[11px] text-accent-text hover:underline">Open in viewer</Link>
            </li>
          );
        })}
      </ol>
    );
  } else if (tab === "labs") {
    body = systemSeries.length === 0 ? <p className="text-xs text-ink-2">No documented measurements are associated with this system.</p> : (
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {systemSeries.slice(0, 3).map((item) => (
          <div key={item.name} className="rounded-lg border border-line bg-surface p-2.5">
            <p className="text-xs font-medium text-ink">{item.display_name} <span className="text-ink-3">({item.unit}, n={item.points.length})</span></p>
            {item.points.length >= 2 ? <BiomarkerTrendChart series={item} height={120} /> : <p className="mt-2 text-[11px] text-ink-3">{item.points.length === 1 ? `${formatNumber(item.points[0].value)} ${item.unit} on ${formatDate(item.points[0].date)}` : "Undated values only"}</p>}
          </div>
        ))}
      </div>
    );
  } else if (tab === "history") {
    body = changes.length === 0 ? <p className="text-xs text-ink-2">No documented change language (stable, increased, new, resolved…) for this system. <Link to="/history" className="text-accent-text hover:underline">Compare examinations</Link></p> : (
      <ul className="space-y-1.5">
        {changes.slice(0, 12).map((statement) => (
          <li key={statement.id} className="flex flex-wrap items-baseline gap-2 text-xs">
            <Badge tone="info" icon={false}>{humanize(statement.comparison)}</Badge>
            <span className="font-medium text-ink">{statement.entity}</span>
            <span className="min-w-0 truncate text-ink-3">“{statement.source_span}”</span>
          </li>
        ))}
      </ul>
    );
  } else {
    body = (
      <div className="space-y-2">
        <Unavailable compact code="MODEL_NOT_VALIDATED" reason="No imaging, detection or segmentation model is validated for this anatomy; no finding is placed on the model." />
        {relevantModels.length > 0 && <p className="text-[11px] text-ink-3">Registered candidates: {relevantModels.map((model) => `${model.display_name} (${humanize(model.status)})`).join("; ")}.</p>}
        <Link to="/validation" className="text-[11px] text-accent-text hover:underline">Validation Center</Link>
      </div>
    );
  }
  return (
    <div className="border-t border-line bg-surface">
      <div className="flex items-center gap-2 border-b border-line px-3 py-1.5">
        <Activity aria-hidden size={14} className="text-ink-3" />
        <Segmented size="sm" label="Evidence panel" value={tab} onChange={setTab} options={[{ value: "imaging", label: `Imaging timeline (${images.length})` }, { value: "labs", label: "Laboratory trends" }, { value: "history", label: "Historical comparison" }, { value: "models", label: "Model evaluation" }]} />
      </div>
      <div className="max-h-56 overflow-y-auto p-3">{body}</div>
    </div>
  );
}

export function NoAnatomy({ message }: { message: string }) {
  return <EmptyState icon={Box} title="Anatomy manifest unavailable" detail={message} />;
}
