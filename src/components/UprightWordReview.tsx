import { useRef, useState } from "react";
import type { ReportPageImage } from "../services/api";
import { universalJson } from "../services/universal";
import { Button, ErrorBlock, StatusBadge, TextInput } from "./ui";

type Box = [number, number, number, number];
export default function UprightWordReview({ uploadId, sha256, image }: { uploadId: number; sha256: string; image: ReportPageImage }) {
  const [selecting, setSelecting] = useState(false);
  const [box, setBox] = useState<Box>([0, 0, 0, 0]);
  const [attested, setAttested] = useState([false, false, false]);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const anchor = useRef<[number, number] | null>(null);
  const ticket = useRef(0);
  const invalidate = () => { ticket.current += 1; setResult(null); setError(null); setBusy(false); };
  function point(event: React.PointerEvent<HTMLDivElement>): [number, number] {
    const rect = event.currentTarget.getBoundingClientRect();
    return [Math.max(0, Math.min(image.width, Math.round((event.clientX - rect.left) / rect.width * image.width))), Math.max(0, Math.min(image.height, Math.round((event.clientY - rect.top) / rect.height * image.height)))];
  }
  async function recognize() {
    const request = ++ticket.current; setBusy(true); setError(null); setResult(null);
    try {
      const response = await universalJson<Record<string, unknown>>(`/uploads/${uploadId}/ocr/upright-word`, { method: "POST", body: JSON.stringify({ page: image.page, bbox_xyxy: box, expected_image_size: [image.width, image.height], source_file_sha256: sha256, coordinate_space: "REPORT_PAGE_PREVIEW_110_DPI", upright_attested: attested[0], single_word_attested: attested[1], latin_text_attested: attested[2] }) });
      if (request === ticket.current) setResult(response);
    } catch (failure) { if (request === ticket.current) setError(String(failure)); } finally { if (request === ticket.current) setBusy(false); }
  }
  return <div className="space-y-2">
    <div className={`relative mx-auto ${selecting ? "cursor-crosshair" : ""}`} style={{ width: "100%", maxWidth: `${448 * image.width / image.height}px`, touchAction: selecting ? "none" : "auto" }} onPointerDown={(event) => { if (!selecting) return; event.preventDefault(); invalidate(); anchor.current = point(event); setBox([...anchor.current, ...anchor.current] as Box); event.currentTarget.setPointerCapture(event.pointerId); }} onPointerMove={(event) => { if (!anchor.current) return; const end = point(event); const start = anchor.current; setBox([Math.min(start[0], end[0]), Math.min(start[1], end[1]), Math.max(start[0], end[0]), Math.max(start[1], end[1])]); }} onPointerUp={(event) => { anchor.current = null; if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}>
      <img src={image.url} alt={`Original report page ${image.page} for upload ${uploadId}`} draggable={false} className="h-auto w-full rounded bg-white" />
      {selecting && <svg aria-hidden="true" viewBox={`0 0 ${image.width} ${image.height}`} className="pointer-events-none absolute inset-0 h-full w-full"><rect x={box[0]} y={box[1]} width={Math.max(0, box[2] - box[0])} height={Math.max(0, box[3] - box[1])} fill="#0f766e22" stroke="#0f766e" strokeWidth={3} /></svg>}
    </div>
    <Button size="sm" aria-expanded={selecting} onClick={() => { setSelecting(!selecting); invalidate(); }}>Select one upright word for review</Button>
    {selecting && <div className="space-y-2 rounded-lg border border-line p-3 text-xs"><p>Drag tightly around one Latin-script word, or enter preview-pixel coordinates below. This preserves an explicitly upright crop; it does not apply the policy to a full page.</p><div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{["Left", "Top", "Right", "Bottom"].map((label, index) => <label key={label}>{label}<TextInput type="number" aria-label={`Word crop ${label.toLowerCase()}`} min={0} max={index % 2 ? image.height : image.width} value={box[index]} onChange={(e) => { invalidate(); setBox((current) => current.map((value, i) => i === index ? Number(e.target.value) : value) as Box); }} /></label>)}</div>{["The word is upright", "The crop contains exactly one word", "The text uses Latin script"].map((label, index) => <label key={label} className="flex items-center gap-2"><input type="checkbox" checked={attested[index]} onChange={(e) => { invalidate(); setAttested((current) => current.map((value, i) => i === index ? e.target.checked : value)); }} />{label}</label>)}<Button size="sm" loading={busy} disabled={!attested.every(Boolean) || box[2] - box[0] < 12 || box[3] - box[1] < 12} onClick={() => void recognize()}>Recognize selected word</Button>{error && <ErrorBlock message={error} />}{result && <div className="space-y-2"><StatusBadge status={String(result.status ?? "UNAVAILABLE")} /><p className="text-ink-2">OCR proposes text for human checking. Confidence is not correctness; no extracted field or clinical record is changed.</p>{typeof result.text_proposal === "string" && <p className="rounded-lg bg-surface-2 p-2 text-base font-semibold">{result.text_proposal}</p>}{typeof result.reason === "string" && <p>{result.reason}</p>}<details><summary className="cursor-pointer text-accent-text">Source coordinates and OCR provenance</summary><pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-all text-[11px]">{JSON.stringify(result, null, 2)}</pre></details></div>}</div>}
  </div>;
}
