import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Component-only fallback when the workstation cannot start Python. These are
// explicit local registry fixtures, never a substitute for the API integration run.
async function fixtureSession(page) {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
  const raw = JSON.parse(await readFile(path.join(root, "model_registry/models.json"), "utf8"));
  const snapshot = JSON.parse(await readFile(path.join(root, "model_registry/validation_status.json"), "utf8"));
  const models = raw.models.map((model) => {
    const status = snapshot.models.find((item) => item.model_id === model.model_id);
    return { ...model, registry_state: status?.registry_state ?? "NOT_VERIFIED", research_gate: status?.research_inference,
      activation: { eligible: false, blockers: [], ...status?.clinical_activation, checkpoint_hash_matches: Boolean(status?.checkpoint_sha256), missing_fields: [], missing_artifacts: [] } };
  });
  const responses = {
    "/auth/me": { id: 1, username: "coverage-fixture", full_name: "Synthetic UI Fixture", role: "researcher", verification_status: "VERIFIED", is_active: true },
    "/cases": [], "/system/health": { status: "FIXTURE_ONLY", models_status: {} },
    "/models": { ...raw, models }, "/capabilities": { capabilities: [] },
    "/datasets": { datasets: [], global_blockers: [] }, "/datasets/task-audit": { datasets: [] },
    "/research-learning": { strategies: [], notice: "Component test fixture only", benchmark: null },
  };
  await page.route("**/api/v1/**", async (route) => {
    const endpoint = new URL(route.request().url()).pathname.replace("/api/v1", "");
    await route.fulfill({ status: endpoint in responses ? 200 : 404, contentType: "application/json", body: JSON.stringify(responses[endpoint] ?? { detail: "No component fixture" }) });
  });
  return "component-test-token";
}

test("coverage filters declared targets, exports full versions and handles unsupported searches", async ({ page }, testInfo) => {
  let token;
  if (process.env.MEDTWIN_COVERAGE_FIXTURE === "1") {
    token = await fixtureSession(page);
  } else {
    const login = await page.request.post("/api/v1/auth/login", { data: {
      username: process.env.MEDTWIN_E2E_USERNAME, password: process.env.MEDTWIN_E2E_PASSWORD,
    } });
    expect(login.ok()).toBeTruthy();
    token = (await login.json()).access_token;
  }
  await page.addInitScript((value) => localStorage.setItem("medtwin_token", value), token);
  await page.goto("/models");
  await page.getByRole("radio", { name: "Organ / test coverage", exact: true }).click();
  const filter = page.getByLabel("Filter capability coverage");
  await expect(filter).toBeVisible();
  // "0 of 0 targets" is the loading state before /models answers; wait for the registry itself.
  await expect(page.getByText(/^[1-9]\d* of [1-9]\d* targets$/)).toBeVisible({ timeout: 60_000 });
  await filter.fill("kidney_stone_detector");
  await expect(page.getByText(/^1 of \d+ targets$/)).toBeVisible();
  await expect(page.getByText(/^Label: Kidney stone$/i)).toBeVisible();
  await expect(page.getByText("Not clinically activated", { exact: true })).toBeVisible();
  const downloading = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export filtered CSV" }).click();
  const download = await downloading;
  const content = await readFile(await download.path(), "utf8");
  expect(content).toContain('"kidney_stone_detector"');
  expect(content).toMatch(/"[a-f0-9]{64}"/);
  expect(content).toContain("Not clinically activated");
  expect(content).not.toContain('"gi_kvasir_v2_classifier"');
  await page.screenshot({ path: testInfo.outputPath("capability-coverage.png"), fullPage: true });
  await filter.fill("unregistered-test-target-123");
  await expect(page.getByText("No registered target matches", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Export filtered CSV" })).toBeDisabled();
});
