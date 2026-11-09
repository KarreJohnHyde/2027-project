import { useState } from "react";
import { api, type FilmAssessment } from "../services/api";
import { useAsync } from "../lib/useAsync";
import FilmPanelPreview from "./FilmPanelPreview";
import { Card, ErrorBlock, LoadingBlock, SelectInput } from "./ui";

export default function PdfFilmPanels({ uploadId, pageCount }: { uploadId: number; pageCount: number }) {
  const [page, setPage] = useState(0);
  const assessment = useAsync(() => page ? api.getPdfFilmAssessment(uploadId, page) : null, [uploadId, page]);
  return <Card title="Film photographs in this PDF" eyebrow="Linked panel previews · source preserved" className="mb-4">
    <p className="mb-3 text-xs text-ink-2">Inspect a photographed scan page separately from its radiology report. Panel order is visual only; no DICOM geometry is inferred.</p>
    <SelectInput aria-label="Film page" value={page} onChange={(event) => setPage(Number(event.target.value))}><option value={0}>Select a page to assess</option>{Array.from({ length: Math.min(500, pageCount) }, (_, i) => <option key={i + 1} value={i + 1}>Page {i + 1}</option>)}</SelectInput>
    {assessment.loading && <LoadingBlock />}{assessment.error && <ErrorBlock message={assessment.error} />}
    {!assessment.loading && assessment.data && <FilmPanelPreview key={page} uploadId={uploadId} pdfPage={page} assessment={assessment.data as FilmAssessment} />}
  </Card>;
}
