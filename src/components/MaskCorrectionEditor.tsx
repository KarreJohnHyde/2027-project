import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import { Eraser, Paintbrush, Pentagon, RotateCcw, Save, Undo2 } from "lucide-react";
import { Button, ErrorBlock, Segmented, SelectInput, TextInput } from "./ui";
import { api, type ReferenceAnnotation, type ResearchOutput, type ResearchRun } from "../services/api";
import { decodeCocoRle } from "../lib/rle";
import { errorMessage, formatNumber } from "../lib/format";

type SegmentationOutput = Extract<ResearchOutput, { type: "segmentation" }>;
type Tool = "brush" | "eraser" | "polygon";

// Correction layer colour (orange), distinct from the model (cyan) and reference (yellow) layers.
const CORRECTION_RGBA: [number, number, number, number] = [251, 146, 60, 150];
const HISTORY_LIMIT = 30;

/** The run's mask for one class name (empty when the model predicted none of it), or every segment when name is null. */
function segmentMask(output: SegmentationOutput, name: string | null): Uint8Array {
  const [width, height] = output.image_size;
  const mask = new Uint8Array(width * height);
  for (const segment of output.segments) {
    if (name !== null && segment.segment !== name) continue;
    const decoded = decodeCocoRle(segment.rle.counts, segment.rle.size[0], segment.rle.size[1]);
    for (let index = 0; index < decoded.length; index += 1) if (decoded[index]) mask[index] = 1;
  }
  return mask;
}

/**
 * Brush-and-eraser correction of a 2-D segmentation run's mask, drawn at the source image's own pixels.
 * Saving stores the edit beside the run (REVIEWER_CORRECTION layer); the run's output never changes.
 */
export default function MaskCorrectionEditor({ run, output, imageUrl, classNames = [], onSaved, save: saveCorrection }: {
  run: ResearchRun; output: SegmentationOutput; imageUrl: string; classNames?: string[]; onSaved: (annotation: ReferenceAnnotation) => void;
  /** Where the edited mask goes; by default a 2-D correction of the run (a volume slice editor passes its own). */
  save?: (mask: Blob, fields: { className: string; note: string }) => Promise<ReferenceAnnotation>;
}) {
  const [width, height] = output.image_size;
  // Every class the model can output is offered, so a class the model missed entirely can still be painted.
  const foreground = classNames.filter((name) => name && name.toLowerCase() !== "background");
  const choices = foreground.length > 1 ? foreground : output.segments.length > 1 ? [...new Set(output.segments.map((segment) => segment.segment))] : [];
  const single = choices.length === 0;
  const [chosenClass, setChosenClass] = useState<string | null>(single ? null : (output.segments[0]?.segment ?? choices[0] ?? null));
  const original = useMemo(() => segmentMask(output, chosenClass), [output, chosenClass]);
  const mask = useRef<Uint8Array>(original.slice());
  const history = useRef<Uint8Array[]>([]);
  const last = useRef<[number, number] | null>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [tool, setTool] = useState<Tool>("brush");
  const [points, setPoints] = useState<Array<[number, number]>>([]);
  const [radius, setRadius] = useState(Math.max(2, Math.round(Math.max(width, height) / 80)));
  const [note, setNote] = useState("");
  const [changed, setChanged] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Segment names are the model's class names, so a single-class model's correction is named after its one class.
  const className = chosenClass ?? (foreground.length === 1 ? foreground[0] : undefined) ?? output.segments[0]?.segment ?? output.foreground_label ?? "foreground";

  const paint = useCallback((x0: number, y0: number, x1: number, y1: number) => {
    const context = canvas.current?.getContext("2d");
    if (!context) return;
    const left = Math.max(0, Math.floor(x0)), top = Math.max(0, Math.floor(y0));
    const right = Math.min(width, Math.ceil(x1)), bottom = Math.min(height, Math.ceil(y1));
    if (right <= left || bottom <= top) return;
    const region = context.createImageData(right - left, bottom - top);
    for (let y = top; y < bottom; y += 1) {
      for (let x = left; x < right; x += 1) {
        if (mask.current[y * width + x]) region.data.set(CORRECTION_RGBA, ((y - top) * (right - left) + (x - left)) * 4);
      }
    }
    context.putImageData(region, left, top);
  }, [width, height]);

  const countChanges = useCallback(() => {
    let count = 0;
    for (let index = 0; index < original.length; index += 1) if (mask.current[index] !== original[index]) count += 1;
    setChanged(count);
  }, [original]);

  useEffect(() => {
    mask.current = original.slice();
    history.current = [];
    paint(0, 0, width, height);
  }, [original, paint, width, height]);

  function pixel(event: PointerEvent<HTMLCanvasElement>): [number, number] {
    const rect = event.currentTarget.getBoundingClientRect();
    return [((event.clientX - rect.left) * width) / rect.width, ((event.clientY - rect.top) * height) / rect.height];
  }

  function stamp(cx: number, cy: number) {
    const value = tool === "brush" ? 1 : 0;
    const r2 = radius * radius;
    for (let y = Math.max(0, Math.floor(cy - radius)); y <= Math.min(height - 1, Math.ceil(cy + radius)); y += 1) {
      for (let x = Math.max(0, Math.floor(cx - radius)); x <= Math.min(width - 1, Math.ceil(cx + radius)); x += 1) {
        if ((x - cx) ** 2 + (y - cy) ** 2 <= r2) mask.current[y * width + x] = value;
      }
    }
  }

  function strokeTo(point: [number, number]) {
    const from = last.current ?? point;
    const distance = Math.hypot(point[0] - from[0], point[1] - from[1]);
    const steps = Math.max(1, Math.ceil(distance / Math.max(1, radius / 2)));
    for (let step = 0; step <= steps; step += 1) stamp(from[0] + ((point[0] - from[0]) * step) / steps, from[1] + ((point[1] - from[1]) * step) / steps);
    paint(Math.min(from[0], point[0]) - radius - 1, Math.min(from[1], point[1]) - radius - 1, Math.max(from[0], point[0]) + radius + 2, Math.max(from[1], point[1]) + radius + 2);
    last.current = point;
  }

  /** Sets every pixel whose centre lies inside the polygon (even-odd rule) to value; one undo step. */
  function fillPolygon(value: 0 | 1) {
    if (points.length < 3) return;
    history.current = [...history.current.slice(-(HISTORY_LIMIT - 1)), mask.current.slice()];
    const xs = points.map(([x]) => x), ys = points.map(([, y]) => y);
    const top = Math.max(0, Math.floor(Math.min(...ys))), bottom = Math.min(height - 1, Math.ceil(Math.max(...ys)));
    for (let y = top; y <= bottom; y += 1) {
      const cy = y + 0.5;
      const crossings: number[] = [];
      for (let index = 0; index < points.length; index += 1) {
        const [x1, y1] = points[index], [x2, y2] = points[(index + 1) % points.length];
        if ((y1 <= cy && cy < y2) || (y2 <= cy && cy < y1)) crossings.push(x1 + ((cy - y1) * (x2 - x1)) / (y2 - y1));
      }
      crossings.sort((a, b) => a - b);
      for (let pair = 0; pair + 1 < crossings.length; pair += 2) {
        for (let x = Math.max(0, Math.ceil(crossings[pair] - 0.5)); x <= Math.min(width - 1, Math.floor(crossings[pair + 1] - 0.5)); x += 1) mask.current[y * width + x] = value;
      }
    }
    paint(Math.min(...xs) - 1, top - 1, Math.max(...xs) + 2, bottom + 2);
    setPoints([]);
    countChanges();
  }

  function onPointerDown(event: PointerEvent<HTMLCanvasElement>) {
    if (tool === "polygon") {
      const point = pixel(event);
      setPoints((current) => [...current, point]);
      return;
    }
    event.currentTarget.setPointerCapture(event.pointerId);
    history.current = [...history.current.slice(-(HISTORY_LIMIT - 1)), mask.current.slice()];
    last.current = null;
    strokeTo(pixel(event));
  }

  function onPointerMove(event: PointerEvent<HTMLCanvasElement>) {
    if (last.current === null || !event.currentTarget.hasPointerCapture(event.pointerId)) return;
    strokeTo(pixel(event));
  }

  function onPointerUp(event: PointerEvent<HTMLCanvasElement>) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    last.current = null;
    countChanges();
  }

  function undo() {
    const previous = history.current.pop();
    if (!previous) return;
    mask.current = previous;
    paint(0, 0, width, height);
    countChanges();
  }

  function reset() {
    history.current = [...history.current.slice(-(HISTORY_LIMIT - 1)), mask.current.slice()];
    mask.current = original.slice();
    paint(0, 0, width, height);
    setChanged(0);
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const output8 = document.createElement("canvas");
      output8.width = width;
      output8.height = height;
      const context = output8.getContext("2d");
      if (!context) throw new Error("Canvas is unavailable in this browser.");
      const image = context.createImageData(width, height);
      for (let index = 0; index < mask.current.length; index += 1) {
        const value = mask.current[index] ? 255 : 0;
        image.data[index * 4] = value;
        image.data[index * 4 + 1] = value;
        image.data[index * 4 + 2] = value;
        image.data[index * 4 + 3] = 255;
      }
      context.putImageData(image, 0, 0);
      const blob = await new Promise<Blob | null>((resolve) => output8.toBlob(resolve, "image/png"));
      if (!blob) throw new Error("The corrected mask could not be encoded.");
      const created = saveCorrection ? await saveCorrection(blob, { className, note: note.trim() }) : await api.addMaskCorrection(run.id, blob, { className, note: note.trim() });
      onSaved(created);
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-2 p-3">
      <p className="text-[11px] leading-4 text-ink-3">
        Paint to add pixels to the class, erase to remove them, or click polygon corners and fill or cut the enclosed pixels. Edits are made at the image's own {formatNumber(width, 0)} × {formatNumber(height, 0)} pixels.
        Saving stores your correction beside run #{run.id} as a separate layer; the model output is not changed. A correction starts from the model's mask, so it is not independent ground truth.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Segmented label="Editing tool" size="sm" value={tool} onChange={setTool} options={[
          { value: "brush", label: <span className="inline-flex items-center gap-1"><Paintbrush aria-hidden className="h-3.5 w-3.5" />Brush</span> },
          { value: "eraser", label: <span className="inline-flex items-center gap-1"><Eraser aria-hidden className="h-3.5 w-3.5" />Eraser</span> },
          { value: "polygon", label: <span className="inline-flex items-center gap-1"><Pentagon aria-hidden className="h-3.5 w-3.5" />Polygon</span> },
        ]} />
        {tool === "polygon" && (
          <>
            <Button size="sm" variant="secondary" disabled={points.length < 3} onClick={() => fillPolygon(1)}>Fill polygon</Button>
            <Button size="sm" variant="secondary" disabled={points.length < 3} onClick={() => fillPolygon(0)}>Cut polygon</Button>
            <Button size="sm" variant="secondary" disabled={points.length === 0} onClick={() => setPoints([])}>Clear {points.length} point(s)</Button>
          </>
        )}
        <label className="flex items-center gap-2 text-[11px] text-ink-3">
          Size
          <input type="range" min={1} max={Math.max(8, Math.round(Math.max(width, height) / 15))} value={radius} onChange={(event) => setRadius(Number(event.target.value))} aria-label="Brush radius in source pixels" className="accent-[var(--mt-accent)]" />
          <span className="tabular w-10 text-ink-2">{radius} px</span>
        </label>
        <Button size="sm" variant="secondary" icon={Undo2} onClick={undo}>Undo</Button>
        <Button size="sm" variant="secondary" icon={RotateCcw} onClick={reset}>Start again from the model</Button>
      </div>
      {!single && (
        <SelectInput aria-label="Class to correct" value={chosenClass ?? ""} onChange={(event) => { setChosenClass(event.target.value); setChanged(0); }}>
          {choices.map((name) => {
            const predicted = output.segments.some((segment) => segment.segment === name);
            return <option key={name} value={name}>{name}{predicted ? "" : " (not predicted by the model)"}</option>;
          })}
        </SelectInput>
      )}
      <div className="relative overflow-hidden rounded bg-black">
        <img src={imageUrl} alt="" draggable={false} className="block h-auto w-full select-none" />
        <canvas
          ref={canvas}
          width={width}
          height={height}
          role="img"
          aria-label={`Editable mask for ${className}`}
          className="absolute inset-0 h-full w-full cursor-crosshair"
          style={{ imageRendering: "pixelated", touchAction: "none" }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        />
        {points.length > 0 && (
          <svg aria-hidden viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="pointer-events-none absolute inset-0 h-full w-full">
            <polyline points={[...points, ...(points.length > 2 ? [points[0]] : [])].map(([x, y]) => `${x},${y}`).join(" ")} fill="none" stroke="#ffffff"
              strokeWidth={1.5} strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />
            {points.map(([x, y], index) => <circle key={index} cx={x} cy={y} r={Math.max(1.5, width / 200)} fill="#ffffff" />)}
          </svg>
        )}
      </div>
      <p className="text-[11px] text-ink-3">{formatNumber(changed, 0)} pixel(s) differ from the model's mask for {className}.</p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="min-w-48 flex-1 text-[11px] text-ink-3">Note (optional, no patient details)<TextInput value={note} maxLength={160} onChange={(event) => setNote(event.target.value)} className="h-8 text-xs" /></label>
        <Button size="sm" variant="primary" icon={Save} loading={saving} disabled={changed === 0} onClick={() => void save()}>Save correction</Button>
      </div>
      {error && <ErrorBlock message={error} />}
    </div>
  );
}
