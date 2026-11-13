import type { UploadedFile, Finding, ClinicalReportStatement } from "../types/medtwin";
import { Link } from "../lib/router";
import { Card, StatusBadge } from "./ui";

interface ModalityViewerProps {
  files: UploadedFile[];
  findings: Finding[];
  reportStatements: ClinicalReportStatement[];
  onRunImageAnalysis: (fileId: string) => void;
  onRunEcgAnalysis: (fileId: string) => void;
  onRunNlpAnalysis: (fileId: string) => void;
  loadingAnalysis: boolean;
}

/** Compatibility entrypoint: illustrated outputs have been retired. */
export function ModalityViewer(_props: ModalityViewerProps) {
  return <Card title="Source-linked medical evidence" eyebrow="Original source and recorded computation required">
    <StatusBadge status="INSUFFICIENT_EVIDENCE" />
    <p className="mt-3 text-sm text-ink-2">Select an uploaded observation in the Case Command Center to inspect its recorded image overlay, digital signal or report passage.</p>
    <p className="mt-2 text-xs text-ink-3">Attribution is available only when a compatible model produced an actual source-bound explanation. A classification attention map does not establish a lesion boundary.</p>
    <Link to="/universal" className="mt-3 inline-block text-sm text-accent-text">Open Case Command Center</Link>
  </Card>;
}

export default ModalityViewer;
