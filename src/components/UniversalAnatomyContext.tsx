import { useMemo, useState } from "react";
import AnatomyViewport, { type TargetSummary, type ViewportLayer } from "../anatomy/AnatomyViewport";
import { chooseTier, loadManifest } from "../anatomy/data";
import { useAsync } from "../lib/useAsync";
import { ErrorBlock, LoadingBlock } from "./ui";

export default function UniversalAnatomyContext({ systemId }: { systemId: string | null }) {
  const manifest = useAsync(loadManifest, []);
  const [target, setTarget] = useState<TargetSummary | null>(null);
  const [opacity, setOpacity] = useState(.85);
  const variant = useMemo(() => {
    const system = manifest.data?.systems.find((item) => item.id === systemId);
    return system?.variants.map((id) => manifest.data!.variants[id]).filter((item) => item?.available && item.kind === "STANDALONE_ASSET" && item.license.commercial_use && item.tiers).sort((a, b) => (a.tiers?.preview?.bytes ?? a.tiers?.standard?.bytes ?? Infinity) - (b.tiers?.preview?.bytes ?? b.tiers?.standard?.bytes ?? Infinity))[0];
  }, [manifest.data, systemId]);
  const layers = useMemo<ViewportLayer[]>(() => variant ? [{ kind: "asset", key: variant.id, url: variant.tiers![chooseTier(variant, "preview")]!.url, structures: variant.structures ?? [], groupBy: variant.group_by ?? "node" }] : [], [variant]);
  if (manifest.loading) return <LoadingBlock label="Loading reference anatomy" />;
  if (manifest.error) return <ErrorBlock message={manifest.error} />;
  if (!variant) return <p className="text-xs text-ink-3">No dedicated commercially reusable standalone asset is available for this source association. Whole-body reference structures remain searchable in Anatomy Studio.</p>;
  return <div className="space-y-2">
    <div className="h-64 overflow-hidden rounded-lg bg-[#111827]" role="group" aria-label="Generic source-associated anatomy reference">
      <AnatomyViewport layers={layers} framing={{ mode: "fit" }} viewMode="TRANSPARENT" opacity={opacity} section={{ axis: "z", offset: 0, flip: false }} isolate={false} labels={true} projection="perspective" selectedKey={target?.key ?? null} hoveredKey={null} hidden={new Set()} onSelect={setTarget} onHover={() => undefined} resetToken={0} />
    </div>
    <label className="flex items-center gap-2 text-xs">Reference transparency<input type="range" aria-label="Reference anatomy opacity" min={.15} max={1} step={.05} value={opacity} onChange={(e) => setOpacity(Number(e.target.value))} /></label>
    {target && <p className="text-xs text-ink-2">Selected reference structure: {target.label}</p>}
    <p className="text-[11px] text-ink-3">{variant.label} · {variant.license.id}. Generic independent asset frame, not patient geometry or lesion localization.</p>
    {variant.source.author && <p className="text-[11px] text-ink-3">Source: {variant.source.author}{variant.source.source_url && <> · <a href={variant.source.source_url} target="_blank" rel="noreferrer" className="text-accent-text underline">Attribution</a></>}</p>}
  </div>;
}
