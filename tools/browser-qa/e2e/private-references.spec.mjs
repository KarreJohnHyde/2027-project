// Synthetic prepared report only. Actual patient records never enter QA fixtures or screenshots.
import { expect, test } from "@playwright/test";

test("private reference reports show sources, limits and reported measurements without a shared case", async ({ page }) => {
  const login = await page.request.post("/api/v1/auth/login", { data: { username: process.env.MEDTWIN_E2E_USERNAME, password: process.env.MEDTWIN_E2E_PASSWORD } });
  expect(login.ok()).toBeTruthy();
  const { access_token: token } = await login.json();
  const headers = { Authorization: `Bearer ${token}` };
  const actual = await page.request.get("/api/v1/private-references", { headers });
  expect(actual.ok()).toBeTruthy();
  expect(await actual.json()).toEqual([]);
  const id = "00000000-0000-4000-8000-000000000001";
  const ref = [{ source: "doc1", page: 2 }];
  const summary = { id, title: "SYNTHETIC reference", summary: "Fictional test packet.", source_count: 1, page_count: 2, created_at: "2024-01-01", trust: { ground_truth: false } };
  const report = { ...summary, facts: [{ title: "Source finding", text: "Synthetic statement requiring review.", refs: ref }],
    timeline: [{ date: "2024-01-01", title: "Historical study", text: "Upload dates are not exam dates.", refs: ref }],
    measurements: [{ label: "Synthetic measurement", value: "12", unit: "test units", date: "2024-01-01", interval: "10–15", flag: "Source interval only.", refs: ref }],
    conflicts: ["Synthetic demographic conflict."], insights: [{ title: "Missing follow-up", text: "No individual forecast available.", refs: ref }],
    limitations: ["Fictional test fixture."], model_outputs: [{ organ: "Synthetic organ", test: "Photographed test", finding: "Synthetic target", model: "No matching validated version", status: "ABSTAIN", reason: "Not a native signal." }],
    processing: { ocr_engine: "synthetic-ocr", renderer: "synthetic renderer", summary_method: "Synthetic test.", diagnostic_models_run: [], forecast_status: "UNAVAILABLE" },
    sources: [{ id: "doc1", label: "Synthetic source", page_count: 2, sha256: "a".repeat(64), bytes: 67, contains_identifiers: false,
      pages: [1,2].map((number) => ({ page: number, asset: `doc1_page_${number}`, description: `Synthetic page ${number}`, ocr: { text: `SYNTHETIC OCR ${number}`, engine: "synthetic", line_count: 1, mean_confidence: .9 } })) }] };
  await page.addInitScript((value) => { localStorage.setItem("medtwin_token", value); localStorage.removeItem("medtwin.selectedCase"); }, token);
  await page.route("**/api/v1/private-references", (route) => route.fulfill({ json: [summary] }));
  await page.route(`**/api/v1/private-references/${id}`, (route) => route.fulfill({ json: report }));
  await page.route(`**/api/v1/private-references/${id}/assets/*`, (route) => route.fulfill({ contentType: "image/png", body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aN5cAAAAASUVORK5CYII=", "base64") }));
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/private-references");
  await expect(page.getByRole("heading", { name: "Your saved case reports" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Selected case" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Check before interpreting" })).toBeVisible();
  await expect(page.getByText("Synthetic measurement", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Document", { exact: true })).toHaveValue("doc1");
  await page.getByRole("button", { name: "Show doc1 page 2" }).first().click();
  await expect(page.getByText("Synthetic page 2", { exact: true })).toBeVisible();
  await expect(page.getByRole("img", { name: "Synthetic source, page 2" })).toBeVisible();
  await page.getByText("Machine-read text", { exact: false }).click();
  await expect(page.getByText("SYNTHETIC OCR 2", { exact: true })).toBeVisible();
  await expect(page.getByText(/^abstain$/i)).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export private report" }).click();
  expect((await downloaded).suggestedFilename()).toBe(`private-reference-${id}.json`);
  expect(errors).toEqual([]);
});
