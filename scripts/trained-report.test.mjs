import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { normalizeTrainedReport } from "../src/lib/trainedReport.ts";

const report = (id) => JSON.parse(readFileSync(new URL(`../docs/validation/models/${id}.json`, import.meta.url), "utf8"));
test("ECG fusion alias renders actual multilabel metrics without inventing per-class results", () => {
  const raw = report("ptbxl_ecg_demographic_fusion");
  const before = JSON.stringify(raw);
  const result = normalizeTrainedReport(raw, "multilabel_ecg_classification");
  assert.equal(result.kind, "multilabel");
  assert.deepEqual(result.report.metrics, raw.metrics);
  assert.equal(result.report.per_class, undefined);
  assert.equal(JSON.stringify(raw), before);
});
test("RSNA nested per-label evidence maps only recorded metrics", () => {
  const raw = report("brain_ct_rsna_ich_classifier");
  const result = normalizeTrainedReport(raw, "multilabel_image_classification");
  assert.equal(result.kind, "multilabel");
  assert.equal(result.report.metrics.macro_auroc, raw.mean_auroc);
  assert.equal(result.report.metrics.macro_auprc, undefined);
  assert.equal(result.report.per_class.length, Object.keys(raw.per_label).length);
  assert.equal(result.report.per_class[0].auroc, Object.values(raw.per_label)[0].auroc);
});
for (const id of ["brain_mri_stroke_lesion_segresnet", "brain_mri_glioma_segresnet", "ct_kidney_tumour_segresnet", "acdc_cardiac_mri_3d_unet"]) {
  test(`${id} preserves actual volumetric measures and source checkpoint`, () => {
    const raw = report(id);
    const result = normalizeTrainedReport(raw, "volumetric_semantic_segmentation");
    assert.equal(result.kind, "volume");
    assert.deepEqual(result.report.metrics, raw.metrics);
    assert.deepEqual(result.report.checkpoint, raw.checkpoint);
    assert.deepEqual(result.report.clinical_indices, raw.clinical_indices);
  });
}
test("skin dictionary class results and checkpoint hashes retain measured values", () => {
  const raw = report("skin_padufes_image_classifier");
  const result = normalizeTrainedReport(raw, "image_classification");
  assert.equal(result.kind, "classification");
  assert.equal(result.report.checkpoint.sha256, raw.checkpoint_sha256);
  assert.deepEqual(result.report.confidence_intervals_95.macro_f1, raw.macro_f1_ci95);
  const melanoma = result.report.per_class.find((row) => row.class === "melanoma");
  assert.equal(melanoma.support, raw.per_class.melanoma.test_n);
  assert.equal(melanoma.recall, raw.per_class.melanoma.sensitivity);
  assert.equal(melanoma.precision, undefined);
  assert.equal(result.report.confusion_matrix, undefined);
});
test("missing/nonfinite or wrong-task scores stay explicitly unsupported", () => {
  for (const [raw, task] of [[{}, "new_task"], [{ metrics: { accuracy: 0.8 } }, "volumetric_semantic_segmentation"], [{ metrics: { mean_case_macro_dice: NaN } }, "volumetric_semantic_segmentation"]]) {
    assert.equal(normalizeTrainedReport(raw, task).kind, "unsupported");
  }
});
