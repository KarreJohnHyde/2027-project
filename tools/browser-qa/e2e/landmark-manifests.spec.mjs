// Runs only on the isolated Playwright stack. Coordinates and report are synthetic.
import { expect, test } from "@playwright/test";

test("landmark UI submits explicit measured pairs and refuses self-approval", async ({ page }) => {
  await page.goto("/");
  await page.fill("#login-username", process.env.MEDTWIN_E2E_USERNAME);
  await page.fill("#login-password", process.env.MEDTWIN_E2E_PASSWORD);
  await page.click("button[type=submit]");
  await page.waitForFunction(() => Boolean(localStorage.getItem("medtwin_token")));
  const token = await page.evaluate(() => localStorage.getItem("medtwin_token"));
  const headers = { Authorization: `Bearer ${token}` };
  const cases = await (await page.request.get("/api/v1/cases", { headers })).json();
  const caseId = cases[0].id;
  const upload = await page.request.post(`/api/v1/cases/${caseId}/uploads`, {
    headers,
    multipart: {
      file: { name: "synthetic-landmark-note.txt", mimeType: "text/plain", buffer: Buffer.from("SYNTHETIC TEST ONLY\nLiver lesion noted.\n") },
      deidentified: "true",
    },
  });
  expect(upload.status()).toBe(201);
  const uploadId = (await upload.json()).id;
  const job = await page.request.post(`/api/v1/uploads/${uploadId}/analysis-jobs`, { headers });
  expect(job.status()).toBe(201);
  const findings = await (await page.request.get(`/api/v1/cases/${caseId}/findings`, { headers })).json();
  // A report finding's label summarises its statements; the lesion is one of the statements.
  const finding = findings.find(item => (item.report_statements ?? []).some(statement => /lesion/i.test(statement.entity ?? "")));
  expect(finding).toBeTruthy();
  await page.evaluate(id => localStorage.setItem("medtwin.selectedCase", String(id)), caseId);
  await page.goto("/anatomy-studio");
  await page.getByText("Case landmark manifests — L2 research gate", { exact: true }).click();
  await page.locator("#landmark-finding").selectOption(String(finding.id));
  await page.getByText("Propose measured landmark correspondences", { exact: true }).click();
  await expect(page.locator("#landmark-limit")).toHaveValue("");
  await expect(page.locator("#landmark-fit")).toHaveValue("");
  await page.locator("#landmark-frame").fill("SYNTHETIC_LPS_mm_to_Atlas_mm");
  await page.locator("#landmark-region").fill("liver");
  await page.locator("#landmark-limit").fill("3");
  const fit = [
    { source: [0, 0, 0], target: [5, 6, 7] },
    { source: [10, 0, 0], target: [15, 6, 7] },
    { source: [0, 10, 0], target: [5, 16, 7] },
  ];
  const heldOut = [{ source: [0, 0, 10], target: [5, 6, 17] }];
  await page.locator("#landmark-fit").fill(JSON.stringify(fit));
  await page.locator("#landmark-held-out").fill(JSON.stringify(heldOut));
  await page.getByLabel("These measurements belong to this case/finding", { exact: false }).check();
  await page.getByRole("button", { name: "Submit for independent review" }).click();
  await expect(page.getByText(/Manifest #\d+ proposed\./)).toBeVisible();
  const manifests = await (await page.request.get(`/api/v1/findings/${finding.id}/landmark-manifests`, { headers })).json();
  const manifest = manifests.at(-1);
  expect(manifest.status).toBe("PROPOSED");
  expect(manifest.fit_landmarks).toEqual(fit);
  await page.locator("summary").filter({ hasText: `Manifest #${manifest.id}` }).click();
  await expect(page.getByRole("table").filter({ has: page.getByText("Fitting landmarks — millimetres", { exact: true }) })).toBeVisible();
  await expect(page.getByText(/The proposer cannot approve or reject their own manifest/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve manifest", exact: true })).toHaveCount(0);
  await expect(page.getByText(/L3 patient-specific reconstruction is unavailable/)).toBeVisible();
});
