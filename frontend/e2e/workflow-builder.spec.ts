import { expect, test } from "./fixtures";

const api = "http://127.0.0.1:8100/api/v1";
const headers = { Origin: "http://127.0.0.1:3100", "X-CSRF-Protection": "1" };

test("visual builder persists positions, config and branches, validates and protects conflicting edits", async ({ page, context }) => {
  test.setTimeout(120_000);
  const data = { email: `builder-${Date.now()}@example.com`, password: "a browser test password 123!" };
  expect((await context.request.post(`${api}/auth/register`, { headers, data })).status()).toBe(202);
  expect((await context.request.post(`${api}/auth/login`, { headers, data })).status()).toBe(200);
  expect((await context.request.post("http://127.0.0.1:8100/__test__/verify-email")).status()).toBe(204);
  const org = (await (await context.request.post(`${api}/organizations`, { headers, data: { name: "Visual builder acceptance" } })).json()).id;
  const created = await (await context.request.post(`${api}/organizations/${org}/workflows`, { headers, data: { name: "Expense routing" } })).json();
  await page.goto(`/app/${org}/workflows/${created.workflow.id}`);
  for (const kind of ["Manual trigger", "Condition", "End"]) await page.getByRole("button", { name: `Add ${kind}`, exact: true }).click();
  await expect(page.locator(".react-flow__minimap-node")).toHaveCount(3);
  const steps = page.getByLabel("Workflow steps", { exact: true });
  await steps.getByRole("button", { name: "Condition", exact: true }).click();
  await page.getByLabel("Node label", { exact: true }).fill("Amount check");
  await page.getByLabel("Input field", { exact: true }).fill("input.amount");
  await page.getByRole("combobox", { name: "Comparison", exact: true }).selectOption("gt");
  await page.getByRole("combobox", { name: "Value type", exact: true }).selectOption("number");
  await page.getByLabel("Comparison value", { exact: true }).fill("5000");
  await page.getByLabel("Position Y", { exact: true }).fill("200");
  await page.getByText("Connections (0)", { exact: true }).click();
  async function connect(from: string, branch: string, to: string) {
    await page.getByRole("combobox", { name: "From step", exact: true }).selectOption({ label: from });
    await page.getByRole("combobox", { name: "Output branch", exact: true }).selectOption(branch);
    await page.getByRole("combobox", { name: "To step", exact: true }).selectOption({ label: to });
    await page.getByRole("button", { name: "Connect steps", exact: true }).click();
  }
  await connect("Manual trigger", "next", "Amount check");
  await connect("Amount check", "true", "End");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByText("Draft saved.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Validate saved graph" }).click();
  await expect(page.getByText("condition requires branches: false, true.")).toBeVisible();
  await expect(page.locator(".node-condition")).toHaveClass(/is-invalid/);
  await connect("Amount check", "false", "End");

  // The actual React Flow handles connect nodes too, independently of the form.
  await page.getByRole("button", { name: "Add Delay", exact: true }).click();
  await page.getByLabel("Delay (seconds)").fill("60");
  const delay = page.locator(".react-flow__node").filter({ has: page.locator(".node-delay") });
  const end = page.locator(".react-flow__node").filter({ has: page.locator(".node-end") });
  await page.getByRole("button", { name: "Fit View", exact: true }).click();
  await delay.locator('[data-handleid="next"]').dragTo(end.locator('[data-handleid="input"]'));
  await expect(page.getByText("Connections (4)", { exact: true })).toBeVisible();
  await steps.getByRole("button", { name: "Delay", exact: true }).click();
  await page.getByRole("button", { name: "Delete node", exact: true }).click();
  await expect(page.getByText("Connections (3)", { exact: true })).toBeVisible();
  await expect(steps.getByRole("button", { name: "Delay", exact: true })).toHaveCount(0);

  // Drag a real node and verify the new coordinates survive a server round trip.
  const condition = page.locator(".node-condition");
  const bounds = await condition.boundingBox();
  await page.mouse.move(bounds!.x + 45, bounds!.y + 35);
  await page.mouse.down(); await page.mouse.move(bounds!.x + 85, bounds!.y + 90, { steps: 8 }); await page.mouse.up();
  const y = await page.getByLabel("Position Y", { exact: true }).inputValue();
  expect(Number(y)).not.toBe(200);
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByText("Draft saved.", { exact: true })).toBeVisible();
  await page.reload();
  await page.getByLabel("Workflow steps", { exact: true }).getByRole("button", { name: "Amount check", exact: true }).click();
  await expect(page.getByLabel("Position Y", { exact: true })).toHaveValue(y);
  await expect(page.getByLabel("Comparison value", { exact: true })).toHaveValue("5000");
  await page.getByRole("button", { name: "Validate saved graph" }).click();
  await expect(page.getByText("Graph is valid.", { exact: true })).toBeVisible();
  const second = await context.newPage();
  try {
    await second.goto(page.url());
    await second.getByLabel("Workflow steps", { exact: true }).getByRole("button", { name: "Amount check", exact: true }).click();
    await second.getByLabel("Node label", { exact: true }).fill("Local conflicting edit");
    await page.getByLabel("Node label", { exact: true }).fill("Saved amount check");
    await page.getByRole("button", { name: "Save draft", exact: true }).click();
    await expect(page.getByText("Draft saved.", { exact: true })).toBeVisible();
    await second.getByRole("button", { name: "Save draft", exact: true }).click();
    await expect(second.getByText("This version changed. Reload it before saving or publishing.")).toBeVisible();
    await expect(second.getByLabel("Node label", { exact: true })).toHaveValue("Local conflicting edit");
    await expect(second.getByRole("button", { name: "Save draft", exact: true })).toBeDisabled();
    second.once("dialog", (dialog) => dialog.dismiss());
    await second.getByRole("button", { name: "Reload saved version" }).click();
    await expect(second.getByLabel("Node label", { exact: true })).toHaveValue("Local conflicting edit");
    second.once("dialog", (dialog) => dialog.accept());
    await second.getByRole("button", { name: "Reload saved version" }).click();
    await expect(second.getByLabel("Workflow steps", { exact: true }).getByRole("button", { name: "Saved amount check", exact: true })).toBeVisible();
  } finally { await second.close(); }
  await page.getByRole("button", { name: "Publish version" }).click();
  await expect(page.getByRole("heading", { name: "Version 1: published" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Add Condition", exact: true })).toHaveCount(0);
  await page.getByLabel("Workflow steps", { exact: true }).getByRole("button", { name: "Saved amount check", exact: true }).click();
  await expect(page.getByLabel("Node label", { exact: true })).toBeDisabled();
  await page.screenshot({ path: "../.local/m5-builder-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  await page.screenshot({ path: "../.local/m5-builder-mobile.png", fullPage: true });
});
