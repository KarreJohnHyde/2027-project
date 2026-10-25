import { useCallback, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { Info } from "lucide-react";
import AnatomyViewport, { type TargetSummary, type ViewportApi, type ViewportLayer } from "../anatomy/AnatomyViewport";
import { ancestry, atlasLookup, chooseTier, loadAtlasIndex, loadManifest, selectAtlasStructures } from "../anatomy/data";
import { AssetStatus, HierarchyList, Inspector, NoAnatomy, PerformanceOverlay, StudioBottomPanel, SystemList, VariantList, ViewerToolbar, type ToolbarState } from "../anatomy/StudioPanels";
import type { AnatomyManifest, AtlasIndex, AtlasStructure, HybridLayer, TierName } from "../anatomy/types";
import { Badge, Button, Disclosure, ErrorBlock, LoadingBlock, SectionTitle, SelectInput, StatusBadge, TextArea } from "../components/ui";
import { api } from "../services/api";
import { errorMessage, formatNumber, humanize } from "../lib/format";
import { usePreferences } from "../lib/preferences";
import { navigate, useLocation } from "../lib/router";
import { useAsync } from "../lib/useAsync";
import { useSelectedCase, useWorkspace } from "../state/workspace";

const STRUCTURE_CACHE = new WeakMap<AtlasIndex, Map<string, AtlasStructure[]>>();

/** Structure selections are pure functions of the atlas; cache them outside React. */
function cachedStructures(atlas: AtlasIndex, key: string, selection: { groups?: string[]; systems?: string[]; exclude?: string[] }): AtlasStructure[] {
  let cache = STRUCTURE_CACHE.get(atlas);
  if (!cache) {
    cache = new Map();
    STRUCTURE_CACHE.set(atlas, cache);
  }
  let structures = cache.get(key);
  if (!structures) {
    structures = selectAtlasStructures(atlas, selection);
    cache.set(key, structures);
  }
  return structures;
}

/** Placement in the atlas frame: measured translation, or bbox scale-then-translate for unregistered assets. */
function layerMatrix(layer: HybridLayer): THREE.Matrix4 {
  const matrix = new THREE.Matrix4();
  if (layer.kind === "ASSET_LAYER" && layer.translation_m) {
    matrix.makeTranslation(layer.translation_m[0], layer.translation_m[1], layer.translation_m[2]);
  } else if (layer.kind === "UNREGISTERED_COMPARISON" && layer.transform) {
    const [x, y, z] = layer.transform.translation;
    matrix.makeTranslation(x, y, z).multiply(new THREE.Matrix4().makeScale(layer.transform.scale, layer.transform.scale, layer.transform.scale));
  }
  return matrix;
}

const HYBRID_LAYER_SYSTEM: Record<string, string> = {
  skeleton: "skeletal", nervous: "nervous", heart: "heart", lungs: "lungs", brain: "brain",
  liver: "liver", pancreas: "pancreas", intestines: "intestines", kidneys: "kidneys",
};

function RegistrationReview({ layer }: { layer: HybridLayer }) {
  const [decision, setDecision] = useState<"ACCEPTED_FOR_EDUCATIONAL_DISPLAY" | "REJECTED" | "NEEDS_LANDMARKS">("NEEDS_LANDMARKS");
  const [comments, setComments] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reviews = useAsync(() => api.getRegistrationReviews(layer.id), [layer.id]);
  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.submitRegistrationReview(layer.id, decision, comments);
      setComments("");
      reviews.reload();
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-2 text-xs">
      {layer.transform && <p className="text-[11px] leading-4 text-ink-2">Scale {formatNumber(layer.transform.scale, 5)} fitted to stature; residual width {formatNumber(layer.transform.residual_width_mm, 1)} mm, depth {formatNumber(layer.transform.residual_depth_mm, 1)} mm. {layer.transform.caveat}</p>}
      {layer.alignment && <p className="text-[11px] leading-4 text-ink-2">Translation {layer.alignment.translation_m.map((value) => `${formatNumber(value * 1000, 1)} mm`).join(", ")}; residual {layer.alignment.residual_after_translation_mm.join(" / ")} mm. {layer.alignment.caveat}</p>}
      <SelectInput aria-label="Review decision" value={decision} onChange={(event) => setDecision(event.target.value as typeof decision)}>
        <option value="NEEDS_LANDMARKS">Needs landmark registration</option>
        <option value="ACCEPTED_FOR_EDUCATIONAL_DISPLAY">Accept for educational display only</option>
        <option value="REJECTED">Reject placement</option>
      </SelectInput>
      <TextArea rows={2} aria-label="Review comments" placeholder="Reviewer comments" value={comments} onChange={(event) => setComments(event.target.value)} />
      {error && <ErrorBlock message={error} />}
      <Button size="sm" variant="primary" loading={busy} onClick={() => void submit()}>Record review</Button>
      {(reviews.data ?? []).slice(0, 3).map((review) => (
        <p key={String(review.id)} className="text-[11px] text-ink-3">#{String(review.id)} {humanize(String(review.decision))} · {String(review.created_at).slice(0, 10)}</p>
      ))}
    </div>
  );
}

function Studio({ manifest, atlas }: { manifest: AnatomyManifest; atlas: AtlasIndex }) {
  const { search } = useLocation();
  const detail = usePreferences((state) => state.detail);
  const showPerformanceDefault = usePreferences((state) => state.showPerformance);
  const caseId = useWorkspace((state) => state.caseId);
  const evidenceVersion = useWorkspace((state) => state.evidenceVersion);
  const uploads = useWorkspace((state) => state.evidence.uploads);
  const statements = useWorkspace((state) => state.evidence.statements);
  const models = useWorkspace((state) => state.models);
  const selectedCase = useSelectedCase();
  const lookup = atlasLookup(atlas);

  const initialSystem = manifest.systems.find((item) => item.id === search.get("system")) ?? manifest.systems[0];
  const initialVariant = initialSystem.variants.includes(search.get("variant") ?? "") ? (search.get("variant") as string) : initialSystem.default_variant;
  const [systemId, setSystemId] = useState(initialSystem.id);
  const [variantId, setVariantId] = useState(initialVariant);
  const [tierOverride, setTierOverride] = useState<TierName | null>(null);
  const [toolbar, setToolbar] = useState<ToolbarState>({ viewMode: "EXTERIOR", opacity: 0.45, section: { axis: "y", offset: 0, flip: false }, isolate: false, labels: false, projection: "perspective", showEvidence: true, showPerformance: showPerformanceDefault });
  const [selected, setSelected] = useState<TargetSummary | null>(null);
  const [hovered, setHovered] = useState<TargetSummary | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());
  const [targets, setTargets] = useState<TargetSummary[]>([]);
  const [interiorKey, setInteriorKey] = useState<string | null>(null);
  const [resetToken, setResetToken] = useState(0);
  const hybridSystem = manifest.systems.find((item) => item.hybrid)!;
  const [hybridOn, setHybridOn] = useState<Record<string, boolean>>(() => Object.fromEntries((hybridSystem.hybrid?.layers ?? []).map((layer) => [layer.id, layer.default_on])));
  const viewportApi = useRef<ViewportApi | null>(null);
  const viewportBox = useRef<HTMLDivElement>(null);
  const pendingFocus = useRef<string | null>(null);

  const system = manifest.systems.find((item) => item.id === systemId) ?? manifest.systems[0];
  const variant = manifest.variants[variantId] ?? manifest.variants[system.default_variant];
  const tier = chooseTier(variant, detail, tierOverride);
  const isHybrid = Boolean(system.hybrid);
  const viewTypes = isHybrid ? ["EXTERIOR", "INTERIOR", "TRANSPARENT", "SECTION", "LAYERED"] : variant.view_types;

  const evidence = useAsync(() => (caseId ? api.getAnatomyEvidence(caseId) : null), [caseId, evidenceVersion]);
  const trends = useAsync(() => (caseId ? api.getBiomarkerTrends(caseId) : null), [caseId, evidenceVersion]);
  const systemEvidence = evidence.data?.systems[system.id] ?? null;

  const layerMatrices = useMemo(() => new Map((hybridSystem.hybrid?.layers ?? []).map((layer) => [layer.id, layerMatrix(layer)])), [hybridSystem]);
  const structuresFor = useCallback((key: string, selection: { groups?: string[]; systems?: string[]; exclude?: string[] }) => cachedStructures(atlas, key, selection), [atlas]);

  const layers = useMemo<ViewportLayer[]>(() => {
    const quality = detail === "preview" ? "economy" : "standard";
    const atlasChunks = (ids: string[]) => atlas.chunks.filter((chunk) => ids.includes(chunk.id)).map((chunk) => ({ id: chunk.id, url: chunk[quality].url }));
    if (system.hybrid) {
      const result: ViewportLayer[] = [];
      for (const layer of system.hybrid.layers) {
        if (!hybridOn[layer.id]) continue;
        if (layer.kind === "ATLAS_LAYER") {
          result.push({ kind: "atlas", key: `hybrid:${layer.id}`, chunks: atlasChunks(layer.chunks ?? []), structures: structuresFor(`hybrid:${layer.id}`, { groups: layer.atlas_groups, systems: layer.atlas_systems, exclude: layer.exclude_groups }), palette: atlas.palette });
          continue;
        }
        const layerVariant = manifest.variants[layer.variant_id ?? ""];
        const layerTier = chooseTier(layerVariant, detail);
        const url = layerVariant?.tiers?.[layerTier]?.url;
        if (!layerVariant || !url) continue;
        result.push({ kind: "asset", key: `hybrid:${layer.id}:${layerTier}`, url, structures: layerVariant.structures ?? [], groupBy: layerVariant.group_by ?? "node", matrix: layerMatrices.get(layer.id) });
      }
      return result;
    }
    if (variant.kind === "ATLAS_REFERENCE" && variant.atlas) {
      return [{ kind: "atlas", key: `atlas:${variant.id}`, chunks: atlasChunks(variant.atlas.chunks), structures: structuresFor(`variant:${variant.id}`, { groups: variant.atlas.groups }), palette: atlas.palette }];
    }
    const url = variant.tiers?.[tier]?.url;
    return url ? [{ kind: "asset", key: `asset:${variant.id}:${tier}`, url, structures: variant.structures ?? [], groupBy: variant.group_by ?? "node" }] : [];
  }, [system, variant, tier, hybridOn, atlas, manifest, detail, structuresFor, layerMatrices]);

  const framing = useMemo(() => (system.hybrid ? { mode: "box" as const, min: system.hybrid.body_bounds.min, max: system.hybrid.body_bounds.max } : { mode: "fit" as const }), [system]);

  const verifiedKeys = useMemo(() => {
    if (!toolbar.showEvidence || !evidence.data) return new Set<string>();
    const ids = new Set((isHybrid ? Object.values(evidence.data.systems) : [evidence.data.systems[system.id]]).flatMap((item) => item?.highlight.verified_structures ?? []));
    return new Set(targets.filter((target) => ids.has(target.structureId)).map((target) => target.key));
  }, [toolbar.showEvidence, evidence.data, isHybrid, system.id, targets]);

  const schematicKeys = useMemo(() => {
    if (!toolbar.showEvidence || !evidence.data || !isHybrid) return new Set<string>();
    const layersWithEvidence = Object.entries(HYBRID_LAYER_SYSTEM).filter(([, organ]) => (evidence.data?.systems[organ]?.state_counts.SCHEMATIC_ORGAN_ONLY ?? 0) > 0).map(([layer]) => `hybrid:${layer}`);
    return new Set(targets.filter((target) => layersWithEvidence.includes(target.layer)).map((target) => target.key));
  }, [toolbar.showEvidence, evidence.data, isHybrid, targets]);

  const onTargets = useCallback((next: TargetSummary[], interior: string | null) => {
    setTargets(next);
    setInteriorKey(interior);
    if (pendingFocus.current) {
      const match = next.find((target) => target.structureId === pendingFocus.current);
      if (match) {
        setSelected(match);
        pendingFocus.current = null;
      }
    }
  }, []);

  function resetView(nextViewTypes: string[]) {
    setSelected(null);
    setHovered(null);
    setHidden(new Set());
    setTargets([]);
    setTierOverride(null);
    setToolbar((current) => ({ ...current, isolate: false, viewMode: nextViewTypes.includes(current.viewMode) ? current.viewMode : "EXTERIOR" }));
  }

  function chooseSystem(id: string) {
    const next = manifest.systems.find((item) => item.id === id)!;
    setSystemId(id);
    setVariantId(next.default_variant);
    resetView(next.hybrid ? ["EXTERIOR", "INTERIOR", "TRANSPARENT", "SECTION"] : manifest.variants[next.default_variant].view_types);
    navigate(`/anatomy-studio?system=${id}`, { replace: true });
  }

  function chooseVariant(id: string) {
    setVariantId(id);
    resetView(manifest.variants[id].view_types);
    navigate(`/anatomy-studio?system=${system.id}&variant=${id}`, { replace: true });
  }

  function focusAtlas(atlasId: string) {
    const target = targets.find((item) => item.structureId === atlasId);
    if (target) {
      setSelected(target);
      return;
    }
    const atlasVariant = `atlas-${system.id}`;
    if (!isHybrid && manifest.variants[atlasVariant] && variant.id !== atlasVariant) {
      pendingFocus.current = atlasId;
      chooseVariant(atlasVariant);
    }
  }

  function screenshot() {
    const data = viewportApi.current?.screenshot();
    if (!data) return;
    const link = document.createElement("a");
    link.href = data;
    link.download = `medtwin-${variant.id}-${new Date().toISOString().replace(/[:.]/g, "-")}.png`;
    link.click();
  }

  const hierarchy = useMemo(() => targets.map((target) => {
    let group = "Structures";
    if (target.layer.startsWith("hybrid:")) group = system.hybrid?.layers.find((layer) => target.layer.startsWith(`hybrid:${layer.id}`))?.label ?? "Layer";
    else if (variant.kind === "ATLAS_REFERENCE") {
      const structure = lookup.byId.get(target.structureId);
      group = structure?.parent ? lookup.byId.get(structure.parent)?.name ?? "Structures" : "Structures";
    }
    const entry = variant.structures?.find((item) => item.id === target.structureId);
    return { key: target.key, label: target.label, group, detail: entry ? `${target.label} · ${humanize(entry.label_source)}` : undefined };
  }).sort((left, right) => left.group.localeCompare(right.group) || left.label.localeCompare(right.label)), [targets, system, variant, lookup]);

  const atlasStructure = selected && (selected.layer.startsWith("atlas:") || (isHybrid && lookup.byId.has(selected.structureId))) ? lookup.byId.get(selected.structureId) ?? null : null;
  const atlasPath = atlasStructure ? ancestry(lookup, atlasStructure).slice(0, -1).map((item) => item.name) : [];
  const interiorLabel = targets.find((target) => target.key === interiorKey)?.label ?? null;
  const assetStructures = isHybrid ? [] : variant.structures ?? [];

  return (
    <div className="flex min-h-[calc(100vh-3.5rem)] flex-col xl:h-[calc(100vh-3.5rem)] xl:flex-row">
      <aside className="w-full shrink-0 space-y-4 overflow-y-auto border-b border-line bg-sidebar p-3 xl:w-72 xl:border-b-0 xl:border-r">
        <div>
          <SectionTitle>Anatomical systems</SectionTitle>
          <SystemList manifest={manifest} systemId={system.id} evidence={evidence.data?.systems} onSelect={chooseSystem} />
        </div>
        {isHybrid ? (
          <div>
            <SectionTitle>Body layers</SectionTitle>
            <ul className="space-y-1">
              {system.hybrid!.layers.map((layer) => (
                <li key={layer.id} className="rounded-lg border border-line bg-surface p-2">
                  <label className="flex items-start gap-2 text-xs">
                    <input type="checkbox" checked={Boolean(hybridOn[layer.id])} onChange={(event) => setHybridOn((current) => ({ ...current, [layer.id]: event.target.checked }))} className="mt-0.5 accent-[var(--mt-accent)]" />
                    <span className="min-w-0 flex-1">
                      <span className="font-medium text-ink">{layer.label}</span>
                      <span className="mt-1 flex flex-wrap gap-1">
                        <StatusBadge status={layer.registration} />
                        {layer.structure_count ? <Badge tone="neutral" icon={false}>{layer.structure_count} structures</Badge> : null}
                      </span>
                    </span>
                  </label>
                  {layer.kind !== "ATLAS_LAYER" && (
                    <div className="mt-2"><Disclosure summary="Placement review"><RegistrationReview layer={layer} /></Disclosure></div>
                  )}
                </li>
              ))}
            </ul>
            <p className="mt-2 text-[11px] leading-4 text-ink-3">Atlas layers share one reference atlas frame. This is a generic adult male reference body, not the patient's anatomy.</p>
          </div>
        ) : (
          <>
            <div>
              <SectionTitle>Model variants</SectionTitle>
              <VariantList manifest={manifest} system={system} variantId={variant.id} onSelect={chooseVariant} />
            </div>
            <div>
              <SectionTitle>Asset status</SectionTitle>
              <AssetStatus variant={variant} tier={tier} onTier={(next) => setTierOverride(next)} />
            </div>
          </>
        )}
        <div>
          <SectionTitle>Available views</SectionTitle>
          <div className="flex flex-wrap gap-1">{viewTypes.map((type) => <Badge key={type} tone="neutral" icon={false}>{humanize(type)}</Badge>)}</div>
        </div>
        <div>
          <SectionTitle>Hierarchy</SectionTitle>
          <HierarchyList
            entries={hierarchy}
            hidden={hidden}
            selectedKey={selected?.key ?? null}
            onToggle={(key) => setHidden((current) => {
              const next = new Set(current);
              if (next.has(key)) next.delete(key);
              else next.add(key);
              return next;
            })}
            onSelect={(key) => setSelected(targets.find((target) => target.key === key) ?? null)}
            onShowAll={() => setHidden(new Set())}
          />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <ViewerToolbar
          state={toolbar}
          viewTypes={viewTypes}
          anatomicalAxes={isHybrid || variant.kind === "ATLAS_REFERENCE"}
          interiorLabel={interiorLabel}
          hasSelection={Boolean(selected)}
          onChange={(patch) => setToolbar((current) => ({ ...current, ...patch }))}
          onReset={() => setResetToken((value) => value + 1)}
          onScreenshot={screenshot}
          onFullscreen={() => void viewportBox.current?.requestFullscreen?.()}
        />
        <div ref={viewportBox} className="relative h-[58vh] min-h-[340px] xl:h-auto xl:flex-1">
          <AnatomyViewport
            layers={layers}
            framing={framing}
            viewMode={toolbar.viewMode}
            opacity={toolbar.opacity}
            section={toolbar.section}
            isolate={toolbar.isolate}
            labels={toolbar.labels}
            projection={toolbar.projection}
            selectedKey={selected?.key ?? null}
            hoveredKey={hovered?.key ?? null}
            hidden={hidden}
            verifiedKeys={verifiedKeys}
            schematicKeys={schematicKeys}
            onSelect={setSelected}
            onHover={setHovered}
            onTargets={onTargets}
            onApi={(handle) => {
              viewportApi.current = handle;
            }}
            measurePerformance={toolbar.showPerformance}
            resetToken={resetToken}
          />
          <div className="pointer-events-none absolute left-3 top-3 z-10 max-w-[70%] space-y-1">
            <span className="inline-flex items-center gap-1.5 rounded-md bg-black/65 px-2 py-1 text-[11px] text-white backdrop-blur">
              <Info aria-hidden size={12} /> L1 generic reference anatomy · {humanize(isHybrid ? "SOURCE_FRAME_SHARED" : variant.registration.status)} · not patient-specific
            </span>
            {hovered && <span className="block w-fit rounded-md bg-black/65 px-2 py-1 text-[11px] text-white">{hovered.label}</span>}
          </div>
          {toolbar.showPerformance && <PerformanceOverlay />}
        </div>
        <StudioBottomPanel systemId={system.id} caseRecord={selectedCase} uploads={uploads} statements={statements} series={trends.data?.series ?? null} models={models} />
      </div>

      <aside className="w-full shrink-0 overflow-y-auto border-t border-line bg-surface p-3 xl:w-80 xl:border-l xl:border-t-0">
        <div className="mb-3">
          <p className="text-xs font-medium text-accent-text">{system.specialty}</p>
          <h1 className="text-base font-semibold text-ink">{system.label}</h1>
          <p className="mt-1 text-xs leading-5 text-ink-2">{system.summary}</p>
        </div>
        {evidence.error && <ErrorBlock message={evidence.error} onRetry={evidence.reload} />}
        <Inspector
          selected={selected}
          variant={variant}
          structures={assetStructures}
          atlasStructure={atlasStructure}
          atlasPath={atlasPath}
          evidence={systemEvidence}
          hasCase={Boolean(caseId)}
          onFocusAtlas={focusAtlas}
        />
        <div className="mt-4 space-y-1.5 border-t border-line pt-3">
          {system.limitations.map((limitation) => <p key={limitation} className="text-[11px] leading-4 text-ink-3">{limitation}</p>)}
          <a href={`${import.meta.env.BASE_URL}anatomy/derived/atlas/ATTRIBUTION.md`} target="_blank" rel="noreferrer" className="text-[11px] text-accent-text hover:underline">Atlas attribution</a>
        </div>
      </aside>
    </div>
  );
}

export default function AnatomyStudioPage() {
  const data = useAsync(() => Promise.all([loadManifest(), loadAtlasIndex()]), []);
  if (data.error) return <div className="p-6"><NoAnatomy message={data.error} /></div>;
  if (!data.data) return <div className="p-6"><LoadingBlock label="Loading anatomy manifest" /></div>;
  return <Studio manifest={data.data[0]} atlas={data.data[1]} />;
}
