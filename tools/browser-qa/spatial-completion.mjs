// Actual isolated-QA UI proof. No inference/training; registration creates an unapproved candidate only.
import { chromium } from "playwright-core";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
const root = process.cwd();
const read = (file) => JSON.parse(readFileSync(file, "utf8").replace(/^\uFEFF/, ""));
const stack = read(path.join(root, ".cache/review-20261113/stack.json"));
if (stack.mode !== "qa") throw new Error("Isolated QA stack required");
const credentials = read(stack.credentials_file);
const proof = read(path.join(root, "artifacts/completion-2026-11-13/imaging/qa-proof.json"));
const out = path.join(root, "artifacts/completion-2026-11-13/imaging/browser"); mkdirSync(out, { recursive: true });
const results = { scope: "Existing authorized public brain research source and original synthetic phantom only; no new model inference or clinical validation.", checks: [], page_errors: [], server_errors: [] };
const browser = await chromium.launch({ channel: "msedge", headless: true, args: ["--use-angle=d3d11", "--enable-gpu-rasterization", "--ignore-gpu-blocklist"] });
const context = await browser.newContext({ viewport: { width: 1500, height: 1100 } });
const page = await context.newPage(); page.setDefaultTimeout(30000);
page.on("pageerror", (error) => results.page_errors.push(String(error)));
page.on("response", (response) => { if (response.status() >= 500) results.server_errors.push({ status: response.status(), path: new URL(response.url()).pathname }); });
const check = (name, passed, detail = {}) => { results.checks.push({ name, passed: Boolean(passed), ...detail }); if (!passed) throw new Error(name); };
async function openSpatial(caseId, uploadId) {
  await page.evaluate((id) => localStorage.setItem("medtwin.selectedCase", String(id)), caseId);
  await page.goto(stack.web_url + "/universal");
  await page.getByRole("tab", { name: "Spatial imaging", exact: true }).click();
  await page.getByLabel("Spatial source upload", { exact: true }).selectOption(String(uploadId));
  return page.getByTestId("universal-imaging-workbench");
}
async function planeHash(axis) {
  const image = page.locator(`section[aria-label^="${axis} "] svg image`).first();
  await image.waitFor({ state: "attached" });
  return image.evaluate(async (element) => {
    const content = await (await fetch(element.getAttribute("href"))).arrayBuffer();
    return [...new Uint8Array(await crypto.subtle.digest("SHA-256", content))].map((v) => v.toString(16).padStart(2, "0")).join("");
  });
}
try {
  await page.goto(stack.web_url + "/account");
  await page.locator("#account-identifier").fill(credentials.username);
  await page.locator("#account-secret").fill(credentials.password);
  await page.getByRole("button", { name: "Open account", exact: true }).click();
  await page.getByRole("button", { name: "Sign out", exact: true }).waitFor();
  let workbench = await openSpatial(proof.brain.case_id, proof.brain.upload_id);
  await workbench.getByText("FRAME_SELECTION_REQUIRED", { exact: true }).waitFor();
  check("4D source refuses implicit frame selection", await workbench.locator('section[aria-label^="axial "] svg').count() === 0);
  await workbench.getByLabel("Fourth-axis interpretation", { exact: true }).selectOption("channel");
  await workbench.getByLabel("Fourth-axis frame index", { exact: true }).fill("0");
  const first = await planeHash("axial");
  check("explicit channel0 produces all three native views", await workbench.locator('section[aria-label$="index plane"] svg').count() === 3);
  await workbench.getByLabel("Fourth-axis frame index", { exact: true }).fill("1");
  await page.waitForResponse((response) => response.url().includes("/spatial/render?") && response.url().includes("frame_index=1") && response.url().includes("axis=sagittal"));
  const second = await planeHash("axial");
  check("channel1 uses distinct actual source pixels", first !== second, { channel0_png_sha256: first, channel1_png_sha256: second });
  await workbench.getByLabel("Show original model mask on all planes", { exact: true }).check();
  await page.waitForFunction(() => [...document.querySelectorAll('section[aria-label$="index plane"] svg')].every((svg) => svg.querySelectorAll("image").length >= 2));
  check("stored multichannel run mask appears on all three native planes", true);
  if (proof.brain.anatomical_metadata.status === "AVAILABLE") {
    await workbench.getByLabel("Plane geometry", { exact: true }).selectOption("anatomical");
    await workbench.getByText("Native voxel (i,j,k):", { exact: false }).waitFor();
    await planeHash("sagittal");
    check("coded known-unit source is physically resampled to anatomical RAS planes", await workbench.getByText("Physically resampled anatomical RAS-mm planes.", { exact: false }).count() === 1);
    await workbench.getByLabel("Show original model mask on all planes", { exact: true }).check();
    await page.waitForFunction(() => [...document.querySelectorAll('section[aria-label^="axial "] svg,section[aria-label^="coronal "] svg,section[aria-label^="sagittal "] svg')].every((svg) => svg.querySelectorAll("image").length >= 2));
    check("original masks are remapped into the anatomical display grid", true);
    check("editing stays anchored to original native axial voxels", await workbench.getByText("Reviewer edits remain anchored", { exact: false }).count() === 1 && await workbench.locator('canvas[aria-label^="Editable mask"]').count() === 0);
  }
  await workbench.locator('section[aria-label^="axial "]').scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(out, "brain-anatomical-workbench.png"), fullPage: false });
  workbench = await openSpatial(proof.synthetic_registration.case_id, proof.synthetic_registration.fixed_upload_id);
  await workbench.getByText("Voxel (i,j,k):", { exact: false }).waitFor();
  const panel = workbench.getByTestId("spatial-registration-panel");
  await panel.locator("summary").first().click();
  await panel.getByLabel("Registration fixed source", { exact: true }).selectOption(String(proof.synthetic_registration.fixed_upload_id));
  await panel.getByLabel("Registration moving source", { exact: true }).selectOption(String(proof.synthetic_registration.moving_upload_id));
  const compute = panel.getByRole("button", { name: "Compute unapproved rigid candidate", exact: true });
  check("registration requires explicit source correspondence attestations", await compute.isDisabled());
  await panel.getByLabel("I confirm these sources describe the same subject.", { exact: true }).check();
  await panel.getByLabel("I confirm these sources cover the same anatomical region with sufficient overlap.", { exact: true }).check();
  await panel.getByLabel("Registration similarity metric", { exact: true }).selectOption("mean_squares");
  await panel.getByLabel("Registration held-out landmarks JSON", { exact: true }).fill(JSON.stringify(proof.synthetic_registration.request.landmarks));
  await compute.click();
  await panel.getByText("CANDIDATE_UNVALIDATED", { exact: false }).waitFor();
  check("actual UI registration reports an unapproved source candidate", true);
  check("held-out physical landmarks produce a measured TRE", await panel.getByText(/MEASURED_ENGINEERING_TRE.*mean TRE/).count() === 1);
  await panel.getByText("Inspect both RAS-mm transform directions", { exact: true }).click();
  check("both transform directions and source identity are reviewable", (await panel.locator("pre").textContent()).includes("moving_to_fixed_ras_mm"));
  await panel.scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(out, "synthetic-registration-candidate.png"), fullPage: false });
  await panel.getByLabel("Registration similarity metric", { exact: true }).selectOption("mattes");
  check("changing registration controls invalidates the stale candidate", await panel.getByText("CANDIDATE_UNVALIDATED", { exact: false }).count() === 0);
  await page.setViewportSize({ width: 390, height: 844 });
  results.mobile_layout = await page.evaluate(() => ({ viewport: innerWidth, document_width: document.documentElement.scrollWidth }));
  check("spatial controls fit mobile viewport", results.mobile_layout.document_width <= results.mobile_layout.viewport);
  check("no uncaught page errors", results.page_errors.length === 0);
  check("no backend500 responses", results.server_errors.length === 0);
} catch (error) {
  results.failure = String(error); process.exitCode = 1;
  await page.screenshot({ path: path.join(out, "failure.png"), fullPage: false });
} finally {
  writeFileSync(path.join(out, "proof.json"), JSON.stringify(results, null, 2));
  await browser.close(); console.log(JSON.stringify(results));
}
