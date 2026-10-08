import { expect, test, type BrowserContext } from "@playwright/test";

const api = "http://127.0.0.1:8100/api/v1";
const headers = { Origin: "http://127.0.0.1:3100", "X-CSRF-Protection": "1" };

async function account(context: BrowserContext, email: string) {
  const data = { email, password: "a browser test password 123!" };
  expect((await context.request.post(`${api}/auth/register`, { headers, data })).status()).toBe(202);
  expect((await context.request.post(`${api}/auth/login`, { headers, data })).status()).toBe(200);
  expect((await context.request.post("http://127.0.0.1:8100/__test__/verify-email")).status()).toBe(204);
}

test("Owner appoints Admin; Admin manages teams; demotion removes access", async ({ page, context, browser }) => {
  test.setTimeout(90_000);
  const recipient = await browser.newContext();
  const email = `team-admin-${Date.now()}@example.com`;
  try {
    await account(context, `team-owner-${Date.now()}@example.com`);
    const created = await context.request.post(`${api}/organizations`, { headers, data: { name: "Team Studio" } });
    expect(created.status()).toBe(201);
    const org = (await created.json()).id;
    const invited = await context.request.post(`${api}/organizations/${org}/invitations`, { headers, data: { email } });
    expect(invited.status()).toBe(201);
    await account(recipient, email);
    expect((await recipient.request.post(`${api}/invitations/${(await invited.json()).id}/accept`, { headers })).status()).toBe(200);
    await page.goto(`/app/${org}/members`);
    const roleSelect = page.getByLabel(`Role for ${email}`, { exact: true });
    await roleSelect.selectOption("admin");
    await roleSelect.locator("..").getByRole("button", { name: "Save role" }).click();
    await expect(page.getByRole("status")).toContainText("Changes saved");
    const admin = await recipient.newPage();
    await admin.goto(`/app/${org}/members`);
    await expect(admin.getByRole("button", { name: "Invite member" })).toBeVisible();
    await expect(admin.getByRole("button", { name: "Save role" })).toHaveCount(0);
    await admin.getByRole("link", { name: "Teams", exact: true }).click();
    await admin.getByLabel("New team name").fill("Finance");
    await admin.getByRole("button", { name: "Create team", exact: true }).click();
    await admin.getByRole("button", { name: "Finance", exact: true }).click();
    await admin.getByLabel("Add organization member").selectOption({ label: email });
    await admin.getByRole("button", { name: "Add to team", exact: true }).click();
    await expect(admin.getByText(email, { exact: true })).toBeVisible();
    await admin.getByLabel("Team name", { exact: true }).fill("Finance Review");
    await admin.getByRole("button", { name: "Rename team" }).click();
    await expect(admin.getByRole("heading", { name: "Finance Review" })).toBeVisible();
    await admin.reload();
    await admin.getByRole("button", { name: "Finance Review", exact: true }).click();
    await expect(admin.getByText(email, { exact: true })).toBeVisible();
    await admin.setViewportSize({ width: 375, height: 812 });
    expect(await admin.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
    await roleSelect.selectOption("viewer");
    const demoted = page.waitForResponse((response) => response.request().method() === "PATCH" && response.url().endsWith("/role"));
    await roleSelect.locator("..").getByRole("button", { name: "Save role" }).click();
    expect((await demoted).status()).toBe(204);
    await expect(roleSelect).toHaveValue("viewer");
    // Attempt a mutation with the still-open Admin view: the backend must reject it.
    const rejected = admin.waitForResponse((response) => response.request().method() === "POST" && response.url().endsWith("/teams"));
    await admin.getByLabel("New team name").fill("Forbidden");
    await admin.getByRole("button", { name: "Create team", exact: true }).click();
    expect((await rejected).status()).toBe(403);
    await expect(admin.getByRole("button", { name: "Create team", exact: true })).toHaveCount(0);
    await admin.getByRole("button", { name: "Finance Review", exact: true }).click();
    await expect(admin.getByText(email, { exact: true })).toBeVisible();
    await expect(admin.getByRole("button", { name: "Delete team" })).toHaveCount(0);
    await page.getByRole("link", { name: "Teams", exact: true }).click();
    await page.getByRole("button", { name: "Finance Review", exact: true }).click();
    await page.getByRole("button", { name: `Remove ${email} from team`, exact: true }).click();
    await expect(page.getByText("This team has no members.")).toBeVisible();
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "Delete team" }).click();
    await expect(page.getByText("No teams to display.")).toBeVisible();
  } finally { await recipient.close(); }
});
