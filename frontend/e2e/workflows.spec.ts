import { expect, test } from "@playwright/test";

const api = "http://127.0.0.1:8100/api/v1";
const headers = { Origin: "http://127.0.0.1:3100", "X-CSRF-Protection": "1" };

test("create, validate, publish, clone and resolve a conflicting workflow draft", async ({ page, context }) => {
  test.setTimeout(90_000);
  const data = { email: `workflow-owner-${Date.now()}@example.com`, password: "a browser test password 123!" };
  expect((await context.request.post(`${api}/auth/register`, { headers, data })).status()).toBe(202);
  expect((await context.request.post(`${api}/auth/login`, { headers, data })).status()).toBe(200);
  expect((await context.request.post("http://127.0.0.1:8100/__test__/verify-email")).status()).toBe(204);
  const createdOrg = await context.request.post(`${api}/organizations`, { headers, data: { name: "Workflow Studio" } });
  expect(createdOrg.status()).toBe(201);
  const org = (await createdOrg.json()).id;
  await page.goto(`/app/${org}/members`);
  await page.getByRole("link", { name: "Workflows", exact: true }).click();
  await page.getByLabel("Workflow name").fill("Purchase review");
  await page.getByLabel("Description", { exact: true }).fill("Draft and publication acceptance test");
  await page.getByRole("button", { name: "Create workflow" }).click();
  await expect(page.getByRole("heading", { name: "Purchase review", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Publish version" }).click();
  await expect(page.getByText("The graph needs exactly one manual trigger.")).toBeVisible();
  await page.getByRole("button", { name: "Load example graph" }).click();
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByText("Draft saved.")).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Validate saved graph" }).click();
  await expect(page.getByText("Graph is valid.")).toBeVisible();
  const savedGraph = await page.getByLabel("Workflow graph (JSON)").inputValue();
  await page.getByRole("button", { name: "Publish version" }).click();
  await expect(page.getByRole("heading", { name: "Version 1: published" })).toBeVisible();
  await expect(page.getByLabel("Workflow graph (JSON)")).toHaveAttribute("readonly");
  await page.getByRole("button", { name: "Create new draft" }).click();
  await expect(page.getByRole("heading", { name: "Version 2: draft" })).toBeVisible();
  const second = await context.newPage();
  try {
    await second.goto(page.url());
    await expect(second.getByRole("heading", { name: "Version 2: draft" })).toBeVisible();
    const graph = JSON.parse(await page.getByLabel("Workflow graph (JSON)").inputValue());
    graph.nodes[0].label = "First editor";
    await page.getByLabel("Workflow graph (JSON)").fill(JSON.stringify(graph));
    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(page.getByText("Draft saved.")).toBeVisible();
    graph.nodes[0].label = "Second editor";
    const edits = JSON.stringify(graph);
    await second.getByLabel("Workflow graph (JSON)").fill(edits);
    await second.getByRole("button", { name: "Save draft" }).click();
    await expect(second.getByText("This version changed. Reload it before saving or publishing.")).toBeVisible();
    await expect(second.getByLabel("Workflow graph (JSON)")).toHaveValue(edits);
    await expect(second.getByRole("button", { name: "Save draft" })).toBeDisabled();
    second.once("dialog", (dialog) => dialog.accept());
    await second.getByRole("button", { name: "Reload saved version" }).click();
    await expect(second.getByLabel("Workflow graph (JSON)")).toContainText("First editor");
    await page.getByRole("button", { name: "Version 1 (published)", exact: true }).click();
    await expect(page.getByLabel("Workflow graph (JSON)")).toHaveValue(savedGraph);
    await page.setViewportSize({ width: 375, height: 812 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  } finally { await second.close(); }
});
