import { expect, test, type BrowserContext } from "@playwright/test";

const api = "http://127.0.0.1:8100";
const headers = { Origin: "http://127.0.0.1:3100", "X-CSRF-Protection": "1" };

async function account(context: BrowserContext, email: string) {
  const data = { email, password: "a browser test password 123!" };
  expect((await context.request.post(`${api}/api/v1/auth/register`, { headers, data })).status()).toBe(202);
  expect((await context.request.post(`${api}/api/v1/auth/login`, { headers, data })).status()).toBe(200);
  expect((await context.request.post(`${api}/__test__/verify-email`)).status()).toBe(204);
}

test("create, switch, invite, join, remove and reject a foreign tenant", async ({ page, context, browser }) => {
  test.setTimeout(90_000);
  const recipient = await browser.newContext();
  const email = `member-${Date.now()}@example.com`;
  try {
    await account(context, `owner-${Date.now()}@example.com`);
    await page.goto("/organizations");
    await page.getByLabel("Organization name").fill("Design Studio");
    const created = page.waitForResponse((response) => response.url() === `${api}/api/v1/organizations` && response.request().method() === "POST");
    await page.getByRole("button", { name: "Create organization", exact: true }).click();
    expect((await created).status()).toBe(201);
    await expect(page.getByRole("heading", { name: "Design Studio", exact: true })).toBeVisible({ timeout: 20_000 });
    const firstUrl = page.url();
    await page.getByLabel("Invite email address").fill(email);
    await page.getByRole("button", { name: "Invite member", exact: true }).click();
    await expect(page.getByText(email, { exact: true })).toBeVisible();
    await page.getByRole("link", { name: "Create or join an organization" }).click();
    await expect(page).toHaveURL(/\/organizations$/);
    await expect(page.getByRole("heading", { name: "Your organizations", exact: true })).toBeVisible();
    await page.getByLabel("Organization name").fill("Research Lab");
    await page.getByRole("button", { name: "Create organization", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Research Lab", exact: true })).toBeVisible();
    const foreignUrl = page.url();
    await expect(page.getByText(email, { exact: true })).toHaveCount(0);
    await page.getByRole("link", { name: "Design Studio", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Design Studio", exact: true })).toBeVisible();

    await account(recipient, email);
    const member = await recipient.newPage();
    await member.goto("/organizations");
    await member.getByRole("button", { name: "Accept invitation" }).click();
    await expect(member.getByRole("link", { name: "Design Studio", exact: true })).toBeVisible();
    await member.getByRole("link", { name: "Design Studio", exact: true }).click();
    await expect(member.getByRole("heading", { name: "Members", exact: true })).toBeVisible();
    await expect(member.getByRole("button", { name: "Invite member" })).toHaveCount(0);
    await member.goto(foreignUrl);
    await expect(member.getByRole("alert").filter({ hasText: "not found" })).toBeVisible();
    await expect(member.getByRole("heading", { name: "Research Lab" })).toHaveCount(0);

    await page.goto(firstUrl);
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "Remove member", exact: true }).click();
    await expect(page.getByRole("status")).toContainText("Changes saved");
    await member.goto(firstUrl);
    await expect(member.getByRole("alert").filter({ hasText: "not found" })).toBeVisible();
    await expect(member.getByRole("heading", { name: "Members", exact: true })).toHaveCount(0);
    await page.setViewportSize({ width: 375, height: 812 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  } finally { await recipient.close(); }
});
