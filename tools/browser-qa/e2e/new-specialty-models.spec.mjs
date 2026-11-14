// Malaria and fetal-plane research models through the real upload → inference → evidence path on the isolated QA stack.
// Each uses the first held-out test image of its public dataset from the git-ignored _derived manifests; skipped if absent.
import { expect, test } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const CASES = [
  { model: "blood_smear_malaria_cell_classifier", type: "MICROSCOPY", manifest: "_derived/datasets/nih-malaria-cell-classification/samples.csv" },
  { model: "ultrasound_fetal_plane_classifier", type: "OBSTETRIC_ULTRASOUND", manifest: "_derived/datasets/fetal-planes-classification/samples.csv" },
];

function firstTestImage(manifest) {
  const file = path.join(ROOT, manifest);
  if (!existsSync(file)) return null;
  const [header, ...lines] = readFileSync(file, "utf8").trim().split(/\r?\n/);
  const columns = header.split(",");
  const row = lines.map((line) => line.split(",")).find((cells) => cells[columns.indexOf("split")] === "test");
  return row ? { path: row[columns.indexOf("path")], label: row[columns.indexOf("label")] } : null;
}

for (const item of CASES) {
  test(`${item.model} runs on an uploaded held-out test image`, async ({ page }) => {
    const sample = firstTestImage(item.manifest);
    test.skip(!sample || !existsSync(sample.path), "Requires the local public dataset manifest.");
    const login = await page.request.post("/api/v1/auth/login", { data: { username: process.env.MEDTWIN_E2E_USERNAME, password: process.env.MEDTWIN_E2E_PASSWORD } });
    const token = (await login.json()).access_token;
    const headers = { Authorization: `Bearer ${token}` };
    const created = await page.request.post("/api/v1/cases", { headers, data: { pseudonymous_id: `PUBLIC-${item.type}-${Date.now()}`, description: "Isolated browser acceptance test; public dataset image." } });
    const caseId = (await created.json()).id;
    const uploaded = await page.request.post(`/api/v1/cases/${caseId}/uploads`, { headers, multipart: {
      file: { name: path.basename(sample.path), buffer: readFileSync(sample.path), mimeType: "image/png" }, deidentified: "true", is_associated: "true" } });
    expect(uploaded.ok(), await uploaded.text()).toBeTruthy();
    const upload = await uploaded.json();
    const run = await page.request.post(`/api/v1/uploads/${upload.id}/research-inference`, { headers, data: { model_id: item.model, declared_input_type: item.type } });
    expect(run.ok(), await run.text()).toBeTruthy();
    const result = await run.json();
    expect(result.status).toBe("COMPLETED");
    expect(result.research_output.type).toBe("classification");
    expect(result.research_output.numeric_precision).toContain("as in the held-out evaluation");
    // The finding is stored as research evidence pending human review.
    expect(JSON.stringify(result)).toContain("PENDING_HUMAN_REVIEW");
    await page.addInitScript(({ value, id }) => { localStorage.setItem("medtwin_token", value); localStorage.setItem("medtwin.selectedCase", String(id)); }, { value: token, id: caseId });
    await page.goto(`/imaging?upload=${upload.id}`);
    await page.getByLabel("Research image type").selectOption(item.type);
    await expect(page.getByText("Research only · not clinically validated", { exact: true }).first()).toBeVisible();
  });
}
