import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import Workflows from "../src/components/workflows";
import { apiRequest, ApiError } from "../src/lib/auth-api";

const { router } = vi.hoisted(() => ({ router: { replace: vi.fn(), push: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("../src/lib/auth-api", async (original) => ({ ...(await original<typeof import("../src/lib/auth-api")>()), apiRequest: vi.fn() }));
beforeEach(() => { vi.resetAllMocks(); });

const version = { id: "v1", version_number: 1, status: "draft", revision: 1, graph: { nodes: [], edges: [] } };
function setup(permissions = ["workflow:read", "workflow:edit", "workflow:publish"], status = "draft") {
  vi.mocked(apiRequest).mockImplementation(async (path) => {
    if (path.endsWith("/access")) return { permissions };
    if (path.endsWith("/versions")) return { items: [{ ...version, status }], next_cursor: null };
    if (path.endsWith("/versions/v1")) return { ...version, status };
    return { id: "workflow", name: "Purchase review", description: "Test" };
  });
}

test("published graph is read-only and supports creating a fresh draft", async () => {
  setup(undefined, "published");
  render(<Workflows orgId="org" workflowId="workflow" />);
  expect(await screen.findByLabelText("Workflow graph (JSON)")).toHaveAttribute("readonly");
  expect(screen.queryByRole("button", { name: "Save draft" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Create new draft" })).toBeVisible();
});

test("read-only role has no authoring or publishing controls", async () => {
  setup(["workflow:read"]);
  render(<Workflows orgId="org" workflowId="workflow" />);
  expect(await screen.findByLabelText("Workflow graph (JSON)")).toHaveAttribute("readonly");
  expect(screen.queryByRole("button", { name: "Save draft" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Publish version" })).not.toBeInTheDocument();
});

test("revision conflict preserves edits and prevents accidental overwrite", async () => {
  setup();
  const original = vi.mocked(apiRequest).getMockImplementation()!;
  vi.mocked(apiRequest).mockImplementation(async (path, method, ...rest) => {
    if (method === "PUT") throw new ApiError(409, "This version changed.", "VERSION_CONFLICT");
    return original(path, method, ...rest);
  });
  render(<Workflows orgId="org" workflowId="workflow" />);
  const input = await screen.findByLabelText("Workflow graph (JSON)");
  const edits = '{"nodes": [], "edges": []}';
  fireEvent.change(input, { target: { value: edits } });
  fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Save draft" })).toBeDisabled());
  expect(input).toHaveValue(edits);
  expect(screen.getByText("This version changed.")).toBeVisible();
  expect(apiRequest).toHaveBeenCalledWith("/organizations/org/workflows/workflow/versions/v1/graph", "PUT", { expected_revision: 1, graph: { nodes: [], edges: [] } });
});

test("unsaved JSON disables publication and validation", async () => {
  setup();
  render(<Workflows orgId="org" workflowId="workflow" />);
  fireEvent.change(await screen.findByLabelText("Workflow graph (JSON)"), { target: { value: "not JSON" } });
  expect(screen.getByRole("button", { name: "Publish version" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Validate saved graph" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("valid JSON");
  expect(screen.getByLabelText("Workflow graph (JSON)")).toHaveValue("not JSON");
});

test("invalid publication displays safe node-specific issues", async () => {
  setup();
  const original = vi.mocked(apiRequest).getMockImplementation()!;
  vi.mocked(apiRequest).mockImplementation(async (path, method, ...rest) => {
    if (path.endsWith("/publish")) throw new ApiError(422, "Resolve validation errors.", "GRAPH_INVALID", { issues: [{ code: "END_REQUIRED", message: "The graph needs an End node." }] });
    return original(path, method, ...rest);
  });
  render(<Workflows orgId="org" workflowId="workflow" />);
  fireEvent.click(await screen.findByRole("button", { name: "Publish version" }));
  expect(await screen.findByText("The graph needs an End node.")).toBeVisible();
});

test("late response from a previous organization cannot expose its workflow", async () => {
  setup();
  const original = vi.mocked(apiRequest).getMockImplementation()!;
  let resolveOld: (value: unknown) => void = () => {};
  const delayed = new Promise((resolve) => { resolveOld = resolve; });
  vi.mocked(apiRequest).mockImplementation(async (path, ...rest) => {
    if (path === "/organizations/old/workflows/workflow") return delayed;
    if (path.startsWith("/organizations/new/")) throw new ApiError(404, "Not found.");
    return original(path, ...rest);
  });
  const { rerender } = render(<Workflows key="old" orgId="old" workflowId="workflow" />);
  await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("/organizations/old/workflows/workflow"));
  rerender(<Workflows key="new" orgId="new" workflowId="workflow" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
  resolveOld({ id: "workflow", name: "Private old workflow" });
  await waitFor(() => expect(screen.queryByText("Private old workflow")).not.toBeInTheDocument());
});
