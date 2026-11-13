import type { UploadedFile, Finding } from "../types/medtwin";
import { Link } from "../lib/router";
import { Card, StatusBadge } from "./ui";

interface ImageAnalysisViewProps {
  files: UploadedFile[];
  findings: Finding[];
  onRunImageAnalysis: (fileId: string) => void;
  loadingAnalysis: boolean;
  onOpenFileUpload: () => void;
}

/** Compatibility entrypoint: illustrated outputs have been retired. */
export function ImageAnalysisView(_props: ImageAnalysisViewProps) {
  return <Card title="Source-linked medical evidence" eyebrow="Original source and recorded computation required">
    <StatusBadge status="INSUFFICIENT_EVIDENCE" />
    <p className="mt-3 text-sm text-ink-2">Select an uploaded observation in the Case Command Center to inspect its recorded image overlay, digital signal or report passage.</p>
    <p className="mt-2 text-xs text-ink-3">Attribution is available only when a compatible model produced an actual source-bound explanation. A classification attention map does not establish a lesion boundary.</p>
    <Link to="/universal" className="mt-3 inline-block text-sm text-accent-text">Open Case Command Center</Link>
  </Card>;
}

export default ImageAnalysisView;
