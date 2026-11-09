// New research workflows on the isolated QA stack. No patient inputs or inference.
import { expect, test } from "@playwright/test";

async function session(page, pseudonym) {
  const response = await page.request.post("/api/v1/auth/login", { data: {
    username: process.env.MEDTWIN_E2E_USERNAME, password: process.env.MEDTWIN_E2E_PASSWORD,
  } });
  expect(response.ok()).toBeTruthy();
  const { access_token: token } = await response.json();
  const headers = { Authorization: `Bearer ${token}` };
  const created = await page.request.post("/api/v1/cases", { headers, data: { pseudonymous_id: pseudonym } });
  expect(created.ok()).toBeTruthy();
  const { id: caseId } = await created.json();
  await page.addInitScript(({ token, caseId }) => {
    localStorage.setItem("medtwin_token", token);
    localStorage.setItem("medtwin.selectedCase", String(caseId));
  }, { token, caseId });
  return { headers, caseId };
}

test("case pages load while optional model metadata is delayed or unavailable", async ({ page }) => {
  const { caseId } = await session(page, "SYNTHETIC-DELAYED-MODEL-METADATA");
  let release;
  const barrier = new Promise((resolve) => { release = resolve; });
  await page.route("**/api/v1/models", async (route) => {
    await barrier;
    await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Synthetic optional metadata outage" }) });
  });
  try {
    await page.goto("/documents", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("combobox", { name: "Selected case", exact: true })).toHaveValue(String(caseId), { timeout: 5000 });
    await expect(page.locator("h1").first()).toBeVisible();
  } finally { release(); }
});

test("task routing refuses ambiguity and selects a unique registered segmentation task", async ({ page }, testInfo) => {
  const { headers, caseId } = await session(page, "SYNTHETIC-ROUTING-BROWSER");
  await page.goto("/models");
  const encoded = await page.evaluate(() => {
    const canvas = document.createElement("canvas"); canvas.width = 96; canvas.height = 80;
    const context = canvas.getContext("2d"); const pixels = context.createImageData(96, 80);
    for (let i = 0; i < pixels.data.length; i += 4) {
      pixels.data[i] = (i * 17) % 255; pixels.data[i + 1] = (i * 31) % 255; pixels.data[i + 2] = (i * 43) % 255; pixels.data[i + 3] = 255;
    }
    context.putImageData(pixels, 0, 0); return canvas.toDataURL("image/png").split(",")[1];
  });
  const response = await page.request.post(`/api/v1/cases/${caseId}/uploads`, { headers, multipart: {
    file: { name: "synthetic-noise.png", buffer: Buffer.from(encoded, "base64"), mimeType: "image/png" },
    deidentified: "true", is_associated: "true",
  } });
  expect(response.ok()).toBeTruthy();
  const { id } = await response.json();
  await page.goto(`/imaging?upload=${id}`);
  await page.getByLabel("Research image type", { exact: true }).selectOption("ENDOSCOPY");
  await expect(page.getByLabel("Research model", { exact: true })).toHaveValue("");
  await page.getByText("Automatically match a research model to the task", { exact: true }).click();
  await page.getByRole("button", { name: "Find compatible model", exact: true }).click();
  await expect(page.getByRole("status", { name: "Model routing result" })).toContainText(/Multiple distinct supported tasks/i);
  await expect(page.getByLabel("Research model", { exact: true })).toHaveValue("");
  await page.getByLabel("Automatic model task").selectOption("segmentation");
  await page.getByRole("button", { name: "Find compatible model", exact: true }).click();
  await expect(page.getByLabel("Research model", { exact: true })).toHaveValue("gi_kvasir_seg_polyp_segmenter");
  await expect(page.getByRole("button", { name: "Run research model", exact: true })).toBeDisabled();
  await page.getByLabel("Automatic model task").selectOption("forecast");
  await page.getByRole("button", { name: "Find compatible model", exact: true }).click();
  await expect(page.getByRole("status", { name: "Model routing result" })).toContainText(/No validated upload forecast model/i);
  // A delayed answer for the previous source must not overwrite the user's new source.
  let release;
  let captured;
  const releaseResponse = new Promise((resolve) => { release = resolve; });
  const requestCaptured = new Promise((resolve) => { captured = resolve; });
  await page.route("**/model-selection", async (route) => {
    const response = await route.fetch(); captured(); await releaseResponse; await route.fulfill({ response });
  });
  await page.getByLabel("Automatic model task").selectOption("segmentation");
  await page.getByRole("button", { name: "Find compatible model", exact: true }).click();
  await requestCaptured;
  await page.getByLabel("Research image type", { exact: true }).selectOption("ANGIOGRAPHY");
  release();
  await expect(page.getByRole("button", { name: "Find compatible model", exact: true })).toBeEnabled();
  await expect(page.getByLabel("Research image type", { exact: true })).toHaveValue("ANGIOGRAPHY");
  await expect(page.getByLabel("Research model", { exact: true })).toHaveValue("");
  await page.screenshot({ path: testInfo.outputPath("task-routing.png"), fullPage: true });
});

test("model registry displays measured learning results with clinical activation disabled", async ({ page }, testInfo) => {
  const { headers } = await session(page, "SYNTHETIC-LEARNING-BROWSER");
  const registryCount = (await (await page.request.get("/api/v1/models", { headers })).json()).models.length;
  await page.goto("/models");
  await expect(page.getByRole("heading", { name: "Experimental learning strategies" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Research job progress" })).toBeVisible();
  await expect(page.getByText("MSD liver acquisition", { exact: true })).toBeVisible();
  await expect(page.getByText("BloodMNIST28", { exact: true })).toBeVisible();
  await expect(page.getByText("Disabled; benchmark results only", { exact: true })).toBeVisible();
  await expect(page.getByText("70% / 69.6%", { exact: true })).toBeVisible();
  await expect(page.getByText("Registry entries", { exact: true }).locator("../..").getByText(String(registryCount), { exact: true })).toBeVisible({ timeout: 60_000 });
  await page.screenshot({ path: testInfo.outputPath("learning-results.png"), fullPage: true });
});

test("skin fusion requires documented attributes and clears them when the model changes", async ({ page }) => {
  const { headers, caseId } = await session(page, "SYNTHETIC-SKIN-FUSION-BROWSER");
  await page.goto("/models");
  const encoded = await page.evaluate(() => {
    const canvas = document.createElement("canvas"); canvas.width = 128; canvas.height = 128;
    const context = canvas.getContext("2d");
    context.fillStyle = "#b9897c"; context.fillRect(0, 0, 128, 128);
    context.fillStyle = "#754a40"; context.fillRect(40, 40, 40, 40);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  const uploaded = await page.request.post(`/api/v1/cases/${caseId}/uploads`, { headers, multipart: {
    file: { name: "synthetic-colour-fixture.png", buffer: Buffer.from(encoded, "base64"), mimeType: "image/png" },
    deidentified: "true", is_associated: "true",
  } });
  expect(uploaded.ok()).toBeTruthy();
  const { id } = await uploaded.json();
  await page.goto(`/imaging?upload=${id}`);
  await page.getByLabel("Research image type", { exact: true }).selectOption("DERMATOLOGY");
  const model = page.getByLabel("Research model", { exact: true });
  await model.selectOption("skin_padufes_image_tabular_classifier");
  await expect(page.getByLabel("Skin research age", { exact: true })).toBeVisible();
  await page.getByLabel(/I confirm this upload is/).check();
  await page.getByRole("button", { name: "Run research model", exact: true }).click();
  await expect(page.getByText("Enter the documented age and lesion region before running the image and attributes model.", { exact: true })).toBeVisible();
  await page.getByLabel("Skin research age", { exact: true }).fill("60");
  await page.getByLabel("Skin research region", { exact: true }).selectOption({ index: 1 });
  await page.getByLabel("Skin research gender", { exact: true }).selectOption("FEMALE");
  await expect(page.getByRole("button", { name: "Run research model", exact: true })).toBeDisabled();
  await model.selectOption("skin_padufes_image_classifier");
  await expect(page.getByLabel("Skin research age", { exact: true })).toHaveCount(0);
  await model.selectOption("skin_padufes_image_tabular_classifier");
  await expect(page.getByLabel("Skin research age", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("Skin research region", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("Skin research gender", { exact: true })).toHaveValue("");
});
