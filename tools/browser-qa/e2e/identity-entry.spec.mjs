// The passwordless entry page and its browser session. Runs only on the isolated Playwright stack; every name here is
// synthetic and every visitor is created by the test.
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

const COOKIE = "medtwin_session";

function visitorName() {
  return `E2E Visitor ${randomUUID().slice(0, 8)}`;
}

async function enter(page, name, role = "Researcher") {
  await page.locator("#entry-name").fill(name);
  await page.locator("#entry-role").selectOption({ label: role });
  await page.getByRole("button", { name: "Enter MedTwin" }).click();
}

async function sessionUser(page) {
  const response = await page.request.get("/api/v1/auth/session");
  expect(response.status()).toBe(200);
  return (await response.json()).user;
}

test("the entry page asks only for details and has no sign-in or account screens", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Welcome to MedTwin" })).toBeVisible();
  await expect(page.getByText("Enter your details to begin.")).toBeVisible();
  for (const label of ["Name", "Age (optional)", "Gender (optional)", "Role"]) await expect(page.locator("label").filter({ hasText: label }).first()).toBeVisible();
  await expect(page.locator("#entry-name")).toHaveAttribute("required", "");
  await expect(page.locator("#entry-age")).not.toHaveAttribute("required", "");
  await expect(page.locator("#entry-gender option")).toHaveText(["Not given", "Female", "Male", "Other", "Prefer not to say"]);
  await expect(page.locator("#entry-role optgroup")).toHaveCount(6);
  for (const label of ["Researcher", "Student", "Clinician", "Doctor", "Nurse", "Clinical staff", "Surgeon", "Cardiology", "Neurosurgery", "Emergency department", "Other"]) {
    await expect(page.locator("#entry-role option", { hasText: label }).first()).toBeAttached();
  }
  await expect(page.getByRole("button", { name: "Enter MedTwin" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Try Demo" })).toBeVisible();
  await expect(page.locator("input[type=password]")).toHaveCount(0);
  for (const text of [/sign in/i, /create account/i, /username or email/i, /password/i, /have a username/i, /open my existing workspace/i, /start a new workspace/i]) {
    await expect(page.getByText(text)).toHaveCount(0);
  }
  // Validation happens before any request.
  let entries = 0;
  page.on("request", (request) => { if (request.url().includes("/auth/enter")) entries += 1; });
  await page.getByRole("button", { name: "Enter MedTwin" }).click();
  await expect(page.getByText("Enter your name.")).toBeVisible();
  await expect(page.getByText("Choose the role that describes you best.")).toBeVisible();
  await page.locator("#entry-name").fill("   ");
  await page.locator("#entry-age").fill("130");
  await page.getByRole("button", { name: "Enter MedTwin" }).click();
  await expect(page.getByText("Enter a whole number from 0 to 120, or leave it empty.")).toBeVisible();
  expect(entries).toBe(0);
});

test("a new visitor enters once and the same browser returns straight to the workspace", async ({ page, browser }) => {
  const name = visitorName();
  await page.goto("/");
  await enter(page, name, "Clinician");
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(name, { exact: true }).first()).toBeVisible();

  // The session is an HttpOnly, SameSite=Lax cookie; nothing secret is kept where page scripts can read it.
  const cookie = (await page.context().cookies()).find((item) => item.name === COOKIE);
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.sameSite).toBe("Lax");
  expect(cookie?.expires).toBeGreaterThan(Date.now() / 1000 + 24 * 3600);
  expect(await page.evaluate(() => document.cookie)).not.toContain(COOKIE);
  expect(await page.evaluate(() => Object.keys(localStorage).filter((key) => /token|visitor/i.test(key)))).toEqual([]);

  // A self-described role grants nothing.
  const user = await sessionUser(page);
  expect(user.role).toBe("public");
  expect(user.stated_role).toBe("clinician");

  // Reload: no form, and no second profile.
  await page.reload();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("#entry-name")).toHaveCount(0);
  expect((await sessionUser(page)).id).toBe(user.id);

  // The browser restarted: the persisted cookie still restores the same visitor.
  const restarted = await browser.newContext({ storageState: await page.context().storageState() });
  const later = await restarted.newPage();
  await later.goto("/");
  await expect(later.getByRole("button", { name: "Sign out" })).toBeVisible({ timeout: 30_000 });
  expect((await sessionUser(later)).id).toBe(user.id);
  await restarted.close();

  // Signing out revokes the session on the server; the browser then sees the entry page again.
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Welcome to MedTwin" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Welcome to MedTwin" })).toBeVisible();
  expect((await page.request.get("/api/v1/auth/session")).status()).toBe(401);
});

test("two people with the same name are separate visitors", async ({ browser }) => {
  const name = visitorName();
  const ids = [];
  for (let index = 0; index < 2; index += 1) {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto("/");
    await enter(page, name);
    await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible({ timeout: 30_000 });
    ids.push((await sessionUser(page)).id);
    await context.close();
  }
  expect(ids[0]).not.toBe(ids[1]);
});

test("a dropped response is retried with the same key and makes one visitor", async ({ page }) => {
  const keys = [];
  let created = null;
  await page.route("**/api/v1/auth/enter", async (route) => {
    keys.push(route.request().headers()["idempotency-key"]);
    if (created) return route.continue();
    // The server makes the visitor, but its answer never reaches the browser.
    created = await (await route.fetch()).json();
    return route.abort("connectionreset");
  });
  await page.goto("/");
  await enter(page, visitorName());
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible({ timeout: 30_000 });
  expect(keys.length).toBeGreaterThanOrEqual(2);
  expect(new Set(keys).size).toBe(1);
  expect((await sessionUser(page)).id).toBe(created.user.id);
});

test("an unreachable server shows a recoverable notice instead of a raw gateway error", async ({ page }) => {
  await page.route("**/api/v1/auth/session", (route) => route.fulfill({
    status: 503, contentType: "application/json",
    body: JSON.stringify({ code: "BACKEND_UNREACHABLE", detail: "The MedTwin server is not reachable (ECONNREFUSED). Start the full stack, then try again." }),
  }));
  await page.goto("/");
  await expect(page.getByText("Server unavailable")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/not reachable/)).toBeVisible();
  await expect(page.getByText(/502|Bad Gateway/)).toHaveCount(0);
  await expect(page.getByRole("link", { name: /Fictional teaching cases/ })).toBeVisible();
  await page.unroute("**/api/v1/auth/session");
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText("Server unavailable")).toHaveCount(0, { timeout: 15_000 });
  await expect(page.getByRole("button", { name: "Enter MedTwin" })).toBeEnabled();
});

test("a sign-in key from an earlier version moves to the cookie once", async ({ page }) => {
  const earlier = await page.request.post("/api/v1/auth/enter", { data: { name: visitorName(), role: "student" } });
  expect(earlier.status()).toBe(201);
  const { access_token: token, user_id: userId } = await earlier.json();
  await page.goto("/examples");
  await page.evaluate((value) => localStorage.setItem("medtwin_token", value), token);
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible({ timeout: 30_000 });
  expect((await sessionUser(page)).id).toBe(userId);
  expect(await page.evaluate(() => localStorage.getItem("medtwin_token"))).toBeNull();
});

test("Try Demo opens an isolated fictional workspace that survives a reload", async ({ page }) => {
  test.setTimeout(300_000);
  await page.goto("/");
  const started = Date.now();
  await page.getByRole("button", { name: "Try Demo" }).click();
  // The demo opens before its documents are analysed; the analysis follows and is reported in the notice.
  await expect(page.getByText(/Guest demo: the sample case and its documents are fictional/)).toBeVisible({ timeout: 20_000 });
  expect(Date.now() - started).toBeLessThan(20_000);
  const listed = await (await page.request.get("/api/v1/cases")).json();
  const demoCase = (Array.isArray(listed) ? listed : listed.items)[0];
  const analyses = async () => (await (await page.request.get(`/api/v1/cases/${demoCase.id}/jobs`)).json())
    .filter((job) => job.kind === "UPLOAD_ANALYSIS").map((job) => job.status).sort();
  // While the demo is being analysed, a sign-in elsewhere is answered promptly (the analysis no longer holds the
  // database write lock while it reads the documents).
  const signInStarted = Date.now();
  const other = await page.request.post("/api/v1/auth/login", { data: { username: process.env.MEDTWIN_E2E_USERNAME, password: process.env.MEDTWIN_E2E_PASSWORD } });
  expect(other.status()).toBe(200);
  expect(Date.now() - signInStarted).toBeLessThan(10_000);
  await expect.poll(analyses, { timeout: 240_000, intervals: [2_000] }).toEqual(["SUCCEEDED", "SUCCEEDED", "SUCCEEDED"]);
  await expect(page.getByText(/Analysing the fictional documents/)).toHaveCount(0, { timeout: 10_000 });
  const guest = await sessionUser(page);
  expect(guest.is_guest).toBe(true);
  await page.reload();
  await expect(page.getByText(/Guest demo: the sample case and its documents are fictional/)).toBeVisible({ timeout: 30_000 });
  expect((await sessionUser(page)).id).toBe(guest.id);
  // The demo account sees its own case only.
  const cases = await (await page.request.get("/api/v1/cases")).json();
  const list = Array.isArray(cases) ? cases : cases.items;
  expect(list.length).toBe(1);
  await page.getByRole("button", { name: "End demo" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "End demo" }).click();
  await expect(page.getByRole("heading", { name: "Welcome to MedTwin" })).toBeVisible();
});

test("registered accounts use a separate page and keep working", async ({ page }) => {
  await page.goto("/account");
  await page.fill("#account-identifier", process.env.MEDTWIN_E2E_USERNAME);
  await page.fill("#account-secret", process.env.MEDTWIN_E2E_PASSWORD);
  await page.getByRole("button", { name: "Open account" }).click();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible({ timeout: 30_000 });
  await expect(page).toHaveURL(/\/$/);
  expect((await sessionUser(page)).username).toBe(process.env.MEDTWIN_E2E_USERNAME);
});
