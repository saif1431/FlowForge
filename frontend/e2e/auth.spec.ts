import { expect, test } from "./fixtures";

for (const host of ["127.0.0.1", "localhost"]) {
test(`register, reject duplicate, login and revoke sessions on ${host}`, async ({ page, context }) => {
  const email = `browser-${Date.now()}@example.com`;
  const password = "a browser test password 123!";
  const origin = `http://${host}:3100`;
  await page.goto(`${origin}/account`);
  await expect(page).toHaveURL(/\/login$/);
  await page.goto(`${origin}/register`);
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("status")).toContainText("Account created");
  // Both hostnames reach the same database and reject case-insensitive duplicates.
  const otherHost = host === "localhost" ? "127.0.0.1" : "localhost";
  await page.goto(`http://${otherHost}:3100/register`);
  await page.getByLabel("Email address").fill(email.toUpperCase());
  await page.getByLabel("Password", { exact: true }).fill("a different browser password 456!");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "An account with this email already exists" })).toBeVisible();
  await expect(page.getByRole("status")).toHaveCount(0);
  await page.goto(`${origin}/login`);
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("incorrect password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Email or password is incorrect" })).toBeVisible();
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Your account" })).toBeVisible();
  await expect(page.getByText(email, { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Your account" })).toBeVisible();
  const cookies = await context.cookies(origin);
  const session = cookies.find((cookie) => cookie.name === "flowforge_session");
  expect(session?.httpOnly).toBe(true);
  expect(await page.evaluate(() => document.cookie)).not.toContain("flowforge_session");
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
  await expect(page.getByRole("button", { name: "Request verification" })).toHaveCount(0);
  await page.getByRole("link", { name: "Your organizations" }).click();
  await expect(page.getByRole("heading", { name: "Your organizations" })).toBeVisible();
  await page.getByLabel("Organization name").fill("Unverified local organization");
  await page.getByRole("button", { name: "Create organization", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Unverified local organization", exact: true })).toBeVisible();
  await page.goto(`${origin}/account`);
  await page.getByRole("button", { name: "Sign out all sessions" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto(`${origin}/account`);
  await expect(page).toHaveURL(/\/login$/);
});
}

test("login layout remains usable on a narrow screen", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
});
