/** Adapt saved report schemas for display without changing their source artifacts. */
type Report = Record<string, unknown>;
export type TrainedReportKind = "multilabel" | "volume" | "survival" | "classification" | "detection" | "segmentation" | "unsupported";
const object = (value: unknown): Report => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Report : {};
const number = (value: unknown) => typeof value === "number" && Number.isFinite(value);

export function normalizeTrainedReport(input: Report, task?: string): { report: Report; kind: TrainedReportKind } {
  const report = { ...input };
  const metrics = { ...object(input.metrics) };
  const declared = String(input.task_type ?? task ?? "");
  if (input.macro_f1_ci95 && !object(input.confidence_intervals_95).macro_f1) {
    report.confidence_intervals_95 = { ...object(input.confidence_intervals_95), macro_f1: input.macro_f1_ci95 };
  }
  if (!report.checkpoint && typeof input.checkpoint_sha256 === "string") report.checkpoint = { sha256: input.checkpoint_sha256 };
  const perClass = input.per_class;
  if (perClass && !Array.isArray(perClass)) report.per_class = Object.entries(object(perClass)).map(([name, values]) => {
    const row = object(values);
    return { ...row, class: name, ...(number(row.test_n) ? { support: row.test_n } : {}), ...(number(row.sensitivity) ? { recall: row.sensitivity } : {}) };
  });
  // RSNA's saved report records mean AUROC and individual label results at the
  // top level. Map only existing measurements; do not synthesize AUPRC/F1/ECE.
  if (number(input.mean_auroc) && Object.keys(object(input.per_label)).length) {
    metrics.macro_auroc = input.mean_auroc;
    report.metrics = metrics;
    report.per_class = Object.entries(object(input.per_label)).map(([label, values]) => {
      const row = object(values);
      return { ...row, class: row.name ?? label, ...(row.auroc_ci95 ? { auroc_95ci: row.auroc_ci95 } : {}) };
    });
    report.task_type = "multilabel_classification";
    return { report, kind: "multilabel" };
  }
  if (["multilabel_classification", "multilabel_ecg_classification", "multilabel_image_classification"].includes(declared) && number(metrics.macro_auroc)) {
    report.task_type = "multilabel_classification";
    return { report, kind: "multilabel" };
  }
  if (["volumetric_segmentation", "volumetric_semantic_segmentation"].includes(declared) && number(metrics.mean_case_macro_dice)) {
    report.task_type = "volumetric_segmentation";
    return { report, kind: "volume" };
  }
  if (["survival", "survival_prediction"].includes(declared) && number(metrics.harrell_c)) return { report, kind: "survival" };
  if (number(object(object(input.test).metrics).map_50_95)) return { report, kind: "detection" };
  if (number(object(input.test).mean_foreground_dice_per_image)) return { report, kind: "segmentation" };
  if ((!declared || declared === "image_classification") && number(metrics.accuracy)) return { report, kind: "classification" };
  return { report, kind: "unsupported" };
}
