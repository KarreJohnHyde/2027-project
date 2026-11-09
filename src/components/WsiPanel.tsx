import { useEffect, useState } from "react";
import { Card, ErrorBlock, KeyValue, LoadingBlock, SelectInput, Table } from "./ui";
import { api, type WsiDescription } from "../services/api";
import { errorMessage, formatNumber } from "../lib/format";
import { useAsync } from "../lib/useAsync";

/** Pyramid, resolution, tissue tiles and full-resolution regions of a whole-slide image (viewing only; no model). */
export default function WsiPanel({ uploadId, slide }: { uploadId: number; slide: WsiDescription }) {
  const tissue = useAsync(() => api.getWsiTissue(uploadId), [uploadId]);
  const [tileIndex, setTileIndex] = useState(0);
  const [level, setLevel] = useState(0);
  const [region, setRegion] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const tiles = tissue.data?.tissue_tiles ?? [];
  const tile = tiles[tileIndex] ?? null;

  useEffect(() => {
    if (!tile || !tissue.data) return;
    let created: string | null = null;
    let cancelled = false;
    const factor = slide.levels[level]?.downsample ?? 1;
    const size = tissue.data.tile_size_px;
    api.getWsiRegionUrl(uploadId, { level, x: Math.floor(tile[0] / factor), y: Math.floor(tile[1] / factor), width: Math.max(64, Math.round((size * 2) / factor)), height: Math.max(64, Math.round((size * 2) / factor)) })
      .then((url) => { created = url; if (cancelled) URL.revokeObjectURL(url); else { setRegion(url); setError(null); } })
      .catch((failure: unknown) => !cancelled && setError(errorMessage(failure)));
    return () => { cancelled = true; if (created) URL.revokeObjectURL(created); };
  }, [uploadId, tile, level, slide.levels, tissue.data]);

  return (
    <Card title="Whole-slide image" eyebrow={`${slide.format} · tiled pyramid`}>
      <div className="space-y-3">
        <KeyValue columns={3} items={[
          { label: "Size (level 0)", value: `${formatNumber(slide.dimensions[0], 0)} × ${formatNumber(slide.dimensions[1], 0)} px` },
          { label: "Resolution", value: slide.microns_per_pixel ? `${formatNumber(slide.microns_per_pixel, 3)} µm/pixel` : "Not recorded by the scanner" },
          { label: "Magnification", value: slide.objective_magnification ? `${formatNumber(slide.objective_magnification, 0)}×` : "Not recorded" },
        ]} />
        <Table headers={["Level", "Size (px)", "Downsample", "Tile"]} dense>
          {slide.levels.map((item) => (
            <tr key={item.level}>
              <td className="tabular text-ink">{item.level}</td>
              <td className="tabular text-ink-2">{formatNumber(item.width, 0)} × {formatNumber(item.height, 0)}</td>
              <td className="tabular text-ink-2">{formatNumber(item.downsample, 2)}</td>
              <td className="tabular text-ink-2">{item.tile ? `${item.tile[0]} × ${item.tile[1]}` : "untiled"}</td>
            </tr>
          ))}
        </Table>
        {tissue.loading && <LoadingBlock label="Finding tissue tiles" />}
        {tissue.error && <ErrorBlock message={tissue.error} />}
        {tissue.data && (
          <>
            <p className="text-[11px] leading-4 text-ink-3">
              {tissue.data.tissue_tile_count} of {tissue.data.total_tiles} tiles of {tissue.data.tile_size_px} px contain tissue ({tissue.data.rule}). {tissue.data.semantics}
              {" "}No pathology model is registered: slide-level labels are needed to train or evaluate one.
            </p>
            {tiles.length > 0 && (
              <div className="flex flex-wrap gap-2">
                <label className="text-xs text-ink-2">Tissue tile
                  <SelectInput aria-label="Tissue tile" value={tileIndex} onChange={(event) => setTileIndex(Number(event.target.value))}>
                    {tiles.slice(0, 500).map(([x, y], index) => <option key={`${x}-${y}`} value={index}>#{index + 1} at x {x}, y {y}</option>)}
                  </SelectInput>
                </label>
                <label className="text-xs text-ink-2">Level
                  <SelectInput aria-label="Pyramid level" value={level} onChange={(event) => setLevel(Number(event.target.value))}>
                    {slide.levels.map((item) => <option key={item.level} value={item.level}>{item.level} (÷{formatNumber(item.downsample, 1)})</option>)}
                  </SelectInput>
                </label>
              </div>
            )}
          </>
        )}
        {error && <ErrorBlock message={error} />}
        {region && <img src={region} alt={`Slide region at level ${level}`} className="max-h-[32rem] rounded border border-line" style={{ imageRendering: level === 0 ? "auto" : "pixelated" }} />}
      </div>
    </Card>
  );
}
