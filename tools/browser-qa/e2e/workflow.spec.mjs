// Actual application screens on the isolated QA stack. Optional supplied report
// inputs must be identity-redacted derivatives; they never enter the repository.
import { expect, test } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

test.use({ viewport: { width: 1536, height: 1024 }, launchOptions: { args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] } });

// The public CT control: an explicit MEDTWIN_E2E_NATIVE_CT_FILE, or the held-out RSNA slice that
// scripts/prepare_e2e_ct_control.py writes to the git-ignored .cache folder. Without either the test skips.
const PREPARED_CT_CONTROL = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../.cache/e2e-controls/public-ct-control.png");
const NATIVE_CT_FILE = process.env.MEDTWIN_E2E_NATIVE_CT_FILE || (existsSync(PREPARED_CT_CONTROL) ? PREPARED_CT_CONTROL : "");

async function post(page, endpoint, token, data, multipart) {
  const response = await page.request.post(`/api/v1${endpoint}`, { headers: token ? { Authorization: `Bearer ${token}` } : {}, ...(multipart ? { multipart } : { data }) });
  expect(response.ok(), `${endpoint}: HTTP ${response.status()}`).toBeTruthy();
  return response.json();
}

async function session(page, pseudonym) {
  const login = await post(page, "/auth/login", null, { username: process.env.MEDTWIN_E2E_USERNAME, password: process.env.MEDTWIN_E2E_PASSWORD });
  const token = login.access_token;
  const caseRecord = await post(page, "/cases", token, { pseudonymous_id: `${pseudonym}-${randomUUID().slice(0, 8)}`, description: "Isolated browser acceptance test. Research only; no patient identity or clinical validation." });
  // A normal API-issued QA credential in a fresh browser context. No user browser
  // state, account password UI or privileged authentication shortcut is used.
  await page.addInitScript(({ token, caseId }) => {
    localStorage.setItem("medtwin_token", token);
    localStorage.setItem("medtwin.selectedCase", String(caseId));
  }, { token, caseId: caseRecord.id });
  return { token, caseId: caseRecord.id };
}

async function upload(page, token, caseId, name, buffer, mimeType, examinationId) {
  return post(page, `/cases/${caseId}/uploads`, token, undefined, {
    file: { name, buffer, mimeType }, deidentified: "true", is_associated: "true",
    ...(examinationId ? { examination_id: String(examinationId) } : {}),
  });
}

function artifacts(testInfo) {
  const base = process.env.MEDTWIN_E2E_SCREENSHOT_DIR || testInfo.outputPath("screens");
  const folder = path.join(base, testInfo.title.replace(/[^a-z0-9]+/gi, "_").slice(0, 70));
  mkdirSync(folder, { recursive: true });
  return folder;
}

async function capture(page, folder, name) {
  await expect(page.locator("main")).toBeVisible();
  await page.screenshot({ path: path.join(folder, name + ".png"), fullPage: true });
}

test("report and photographed film remain usable across the complete application", async ({ page }, testInfo) => {
  test.setTimeout(240_000);
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  const folder = artifacts(testInfo);
  const lobarAssetAvailable = process.env.MEDTWIN_E2E_NO_DERIVED_ASSETS !== "1" && existsSync(new URL("../../../public/anatomy/derived/brain-lobes-versal/standard.glb", import.meta.url));
  if (!lobarAssetAvailable) await page.route("**/anatomy/derived/**", (route) => route.fulfill({ status: 404, body: "Optional anatomy derivative is not published." }));
  const { token, caseId } = await session(page, "REPORT-FILM-BROWSER-ACCEPTANCE");
  const supplied = process.env.MEDTWIN_E2E_REPORT_FILE;
  const reportName = supplied ? "identity-redacted-report.pdf" : "synthetic-neuro-report.txt";
  const report = await upload(page, token, caseId, reportName,
    supplied ? readFileSync(supplied) : Buffer.from("SYNTHETIC SOFTWARE FIXTURE - NOT A PATIENT\nReport date: 2023-03-07\nRight high parietal lobe hemorrhagic contusion with mild perilesional edema.\nNo midline shift.\nNo skull fracture.\nRight parietal scalp soft tissue swelling.\n"),
    supplied ? "application/pdf" : "text/plain");
  let film;
  if (process.env.MEDTWIN_E2E_FILM_FILE) film = readFileSync(process.env.MEDTWIN_E2E_FILM_FILE);
  else {
    await page.goto("/");
    film = Buffer.from(await page.evaluate(() => {
      const canvas = document.createElement("canvas"); canvas.width = 1000; canvas.height = 480;
      const ctx = canvas.getContext("2d"); ctx.fillStyle = "black"; ctx.fillRect(0, 0, 1000, 480);
      for (let row = 0; row < 2; row++) for (let col = 0; col < 5; col++) {
        ctx.beginPath(); ctx.ellipse(col * 200 + 100, row * 240 + 120, 85, 105, 0, 0, Math.PI * 2);
        ctx.fillStyle = "#375f6e"; ctx.fill(); ctx.lineWidth = 12; ctx.strokeStyle = "white"; ctx.stroke();
        ctx.fillStyle = "#e64137"; ctx.fillRect(col * 200 + 30, row * 240 + 100, 20, 20);
      }
      return canvas.toDataURL("image/png").split(",")[1];
    }), "base64");
  }
  const image = await upload(page, token, caseId, "source-film-montage.png", film, "image/png");
  const processed = await post(page, `/cases/${caseId}/workflow/process-reports`, token, {});
  expect(processed.results[0].status).toBe("SUCCEEDED");
  for (let i = 0; i < 2; i++) await post(page, `/uploads/${image.id}/multimodel`, token, { model_ids: ["brain_ct_rsna_ich_classifier"], declared_input_type: "HEAD_CT" });
  const synthesis = await (await page.request.get(`/api/v1/cases/${caseId}/evidence-synthesis`, { headers: { Authorization: `Bearer ${token}` } })).json();
  expect(synthesis.model_findings).toHaveLength(0);
  expect(synthesis.abstentions).toHaveLength(1);
  expect(synthesis.abstentions[0].attempt_count).toBe(2);
  expect(synthesis.overall_disease_probability).toBeNull();
  writeFileSync(path.join(folder, "evidence-synthesis.json"), JSON.stringify(synthesis, null, 2));

  await page.goto("/cases");
  await expect(page.getByRole("heading", { name: "Integrated case workflow" })).toBeVisible();
  await expect(page.getByText("Combined", { exact: true })).toBeVisible();
  await capture(page, folder, "01-case-workflow");
  await page.goto("/documents");
  await page.getByLabel("Report", { exact: true }).selectOption({ label: reportName });
  await expect(page.locator('[data-testid="source-statement"]').first()).toBeVisible();
  await capture(page, folder, "02-document-intelligence");
  await page.goto(`/imaging?upload=${image.id}`);
  const panel = page.getByAltText("Source film panel 1, viewing preview only");
  await expect(panel).toBeVisible();
  await expect(page.getByText(/This upload is a suspected photographed CT film or montage/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Run research model", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Run chest radiograph model", exact: true })).toHaveCount(0);
  await capture(page, folder, "03-film-preview-and-model-gate");
  await page.getByRole("button", { name: "Panel 2", exact: true }).click();
  await expect(page.getByAltText("Source film panel 2, viewing preview only")).toBeVisible();
  await page.getByRole("button", { name: "Panel 2", exact: true }).click();
  await expect(page.getByAltText("Source film panel 2, viewing preview only")).toBeVisible();
  await capture(page, folder, "04-selected-source-panel");
  await page.goto("/multimodal");
  await expect(page.getByText("3 recorded attempts", { exact: false })).toHaveCount(0);
  await expect(page.getByText("2 recorded attempts", { exact: false })).toBeVisible();
  await expect(page.getByText("Model output modalities:", { exact: true })).toBeVisible();
  await capture(page, folder, "05-multimodal-synthesis");
  await page.getByRole("link", { name: "View reported brain region" }).first().click();
  await expect(page.locator("canvas").first()).toBeVisible({ timeout: 60_000 });
  if (lobarAssetAvailable) {
    await expect(page.locator("section").filter({ has: page.getByText("Selected structure", { exact: true }) }).getByText("Parietal lobe", { exact: true })).toBeVisible({ timeout: 60_000 });
  } else {
    // Clean CI checkouts omit derived geometry. Keep the report association
    // visible and require an explicit asset failure, without claiming a mesh.
    await expect(page.getByRole("alert").filter({ hasText: "Asset could not be rendered" })).toBeVisible();
    await expect(page.getByText(/Documented region: Parietal lobe/).first()).toBeVisible();
    await expect(page.getByText("Click a structure in the model or the hierarchy.", { exact: false })).toBeVisible();
  }
  await capture(page, folder, "06-reported-atlas-region");
  for (const [route, name] of [["/documents/verify", "07-verification"], ["/history", "08-insufficient-history"], ["/prognosis-studio?organ=brain", "09-conditional-prognosis"], ["/models", "10-model-registry"], ["/datasets", "11-dataset-registry"]]) {
    await page.goto(route);
    await expect(page.locator("h1").first()).toBeVisible();
    await capture(page, folder, name);
  }
  await page.goto("/reports");
  const exportButton = page.getByRole("button", { name: "Export JSON", exact: true });
  await expect(exportButton).toBeEnabled({ timeout: 30_000 });
  const download = page.waitForEvent("download"); await exportButton.click();
  const file = await download; const exportPath = path.join(folder, "research-report.json"); await file.saveAs(exportPath);
  const exported = JSON.parse(readFileSync(exportPath));
  expect(exported.schema_version).toBe("medtwin-evidence-export-4.0.0");
  expect(exported.case_workflow.case_id).toBe(caseId);
  expect(exported.forecast_evaluation_history).toHaveLength(0);
  await capture(page, folder, "12-research-report");
  const unexpectedErrors = errors.filter((message) => lobarAssetAvailable || !message.startsWith("Could not load /anatomy/derived/brain-lobes-versal/standard.glb:"));
  expect(unexpectedErrors).toEqual([]);
});

test("synthetic reviewed history supports real comparison and baseline output", async ({ page }, testInfo) => {
  const folder = artifacts(testInfo);
  const { token, caseId } = await session(page, "SYNTHETIC-LONGITUDINAL-BROWSER-ACCEPTANCE");
  for (const [date, value] of [["2024-01-01", 70], ["2024-02-01", 72], ["2024-03-01", 76]]) {
    const exam = await post(page, `/cases/${caseId}/examinations`, token, { exam_date: date + "T00:00:00", modality: "REPORT" });
    await upload(page, token, caseId, `synthetic-${date}.txt`, Buffer.from(`SYNTHETIC SOFTWARE FIXTURE - NOT A PATIENT\nReport date: ${date}\nHeart rate: ${value} bpm.\n`), "text/plain", exam.id);
  }
  await post(page, `/cases/${caseId}/workflow/process-reports`, token, {});
  const measurements = await (await page.request.get(`/api/v1/cases/${caseId}/measurements`, { headers: { Authorization: `Bearer ${token}` } })).json();
  expect(measurements.filter(m => m.name === "heart_rate")).toHaveLength(3);
  for (const findingId of new Set(measurements.map(m => m.finding_id))) await post(page, `/reviews/${findingId}`, token, { review_status: "CONFIRMED", reviewer_comments: "Synthetic fixture checked for automated software testing; not clinical review." });
  await page.goto("/history");
  await expect(page.getByRole("button", { name: "Compare", exact: true })).toBeDisabled();
  await page.getByRole("checkbox", { name: /these two examinations belong to the same patient/ }).check();
  await page.getByRole("button", { name: "Compare", exact: true }).click();
  await expect(page.getByRole("cell", { name: "Heart rate heart_rate", exact: true })).toBeVisible();
  await capture(page, folder, "01-observed-comparison");
  await page.goto("/prognosis-studio?organ=heart");
  await page.getByLabel("Observed variable").selectOption("heart_rate|bpm");
  await page.getByRole("checkbox", { name: /these historical observations belong to the same patient/ }).check();
  await page.getByRole("button", { name: "Evaluate baseline", exact: true }).click();
  await expect(page.getByText("Research prototype", { exact: true }).last()).toBeVisible();
  await expect(page.getByText("Backtest MAE / RMSE", { exact: true })).toBeVisible();
  await capture(page, folder, "02-research-baseline");
  await page.goto("/reports");
  await expect(page.getByRole("heading", { name: "Saved longitudinal forecast evaluations" })).toBeVisible();
  const download = page.waitForEvent("download"); await page.getByRole("button", { name: "Export JSON", exact: true }).click();
  const file = await download; const exportPath = path.join(folder, "synthetic-longitudinal-report.json"); await file.saveAs(exportPath);
  const data = JSON.parse(readFileSync(exportPath));
  expect(data.forecast_evaluation_history[0].predicted_value).toBe(76);
  expect(data.forecast_evaluation_history[0].baseline_analysis.chronological_series).toHaveLength(3);
  await capture(page, folder, "03-saved-forecast-report");
});

test("public digital CT control shows real checkpoint output separately", async ({ page }, testInfo) => {
  test.skip(!NATIVE_CT_FILE, "Requires a local public-dataset control image (run scripts/prepare_e2e_ct_control.py).");
  const folder = artifacts(testInfo);
  const { token, caseId } = await session(page, "PUBLIC-DATASET-CT-RESEARCH-CONTROL");
  const image = await upload(page, token, caseId, "public-digital-ct-control.png", readFileSync(NATIVE_CT_FILE), "image/png");
  const run = await post(page, `/uploads/${image.id}/research-inference`, token, { model_id: "brain_ct_rsna_ich_classifier", declared_input_type: "HEAD_CT" });
  expect(run.status).toBe("COMPLETED");
  expect(run.research_output.type).toBe("multilabel_classification");
  writeFileSync(path.join(folder, "research-model-output.json"), JSON.stringify(run, null, 2));
  await page.goto(`/imaging?upload=${image.id}`);
  await page.getByLabel("Research image type").selectOption("HEAD_CT");
  await expect(page.getByRole("columnheader", { name: "Probability", exact: true })).toBeVisible();
  await expect(page.getByText("Research only · not clinically validated", { exact: true })).toBeVisible();
  await capture(page, folder, "01-real-ct-model-output");
  await page.goto("/multimodal");
  await expect(page.getByRole("link", { name: "Open stored model output", exact: true })).toBeVisible();
  await capture(page, folder, "02-scan-only-model-evidence");
});
