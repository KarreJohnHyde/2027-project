import type { ReportPage } from "../services/api";
import { humanize } from "./format";

/** The 1-based page holding a text offset, from the pages' start offsets. */
export function pageOf(pageStarts: number[], offset: number): number {
  let page = 1;
  pageStarts.forEach((start, index) => { if (offset >= start) page = index + 1; });
  return page;
}

/** "Imaging report · CT", "Laboratory report", "Not typed". */
export function pageTypeLabel(page: ReportPage | undefined): string {
  const kind = page?.document_type;
  if (!kind) return "Not typed";
  const modality = kind.imaging_modality;
  return `${humanize(kind.document_type)}${modality ? ` · ${modality === "CT" || modality === "MRI" ? modality : humanize(modality)}` : ""}`;
}
