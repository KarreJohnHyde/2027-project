import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

test("public teaching cases work without an account or backend and export only fictional data", async ({ page }) => {
  const apiRequests = [];
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/v1/**", (route) => { apiRequests.push(route.request().url()); return route.abort(); });
  await page.goto("/examples");
  await expect(page.getByRole("heading", { name: "Three cases. A clearer view of the evidence." })).toBeVisible();
  await expect(page.getByText(/^Fictional teaching adaptations:/)).toBeVisible();
  await expect(page.getByRole("group", { name: "Teaching cases" }).getByRole("button")).toHaveCount(3);
  await page.getByRole("button", { name: /^Maya/ }).click();
  await expect(page).toHaveURL(/case=maya-mixed-reports/);
  await expect(page.getByRole("heading", { name: "Illustrative measurements" })).toBeVisible();
  await page.getByRole("button", { name: "Read source B3", exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "Fictional chest CT summary", exact: true })).toBeVisible();
  await expect(page.getByText(/FICTIONAL CHEST CT SUMMARY/)).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download teaching case" }).click();
  const payload = JSON.parse(await readFile(await (await downloaded).path(), "utf8"));
  expect(payload.kind).toBe("SYNTHETIC_TEACHING_CASE");
  expect(payload.diagnostic_models_run).toBe(0);
  expect(payload.clinical_validation).toBe("NOT_PERFORMED");
  expect(payload.name).toBe("Maya");
  const forbidden = /^(owner|assets|file_hash|sha256|source_file_id|patient_id|date_of_birth|ocr|original_asset|file_path|username)$/;
  function check(value) {
    if (Array.isArray(value)) value.forEach(check);
    else if (value && typeof value === "object") for (const [key, nested] of Object.entries(value)) { expect(key).not.toMatch(forbidden); check(nested); }
  }
  check(payload);
  await page.getByRole("button", { name: /^Sam/ }).click();
  await expect(page.getByRole("heading", { name: "Read the formal echo details" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: /^Sam/ })).toHaveAttribute("aria-pressed", "true");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)).toBe(false);
  expect(apiRequests).toEqual([]);
  expect(errors).toEqual([]);
  expect(await page.evaluate(() => localStorage.getItem("medtwin_token"))).toBeNull();
});

test("entry page links to public examples while private reports remain behind sign-in", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /Fictional teaching cases/ }).click();
  await expect(page.getByRole("heading", { name: "Three cases. A clearer view of the evidence." })).toBeVisible();
  await page.goto("/private-references");
  await expect(page.getByRole("heading", { name: "Welcome to MedTwin" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your saved case reports" })).toHaveCount(0);
});
