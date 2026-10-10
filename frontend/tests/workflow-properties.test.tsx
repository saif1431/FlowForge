import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { useState } from "react";
import WorkflowProperties from "../src/components/workflow-properties";
import type { WorkflowNode } from "../src/lib/workflow-graph";
import { apiRequest } from "../src/lib/auth-api";

vi.mock("../src/lib/auth-api", () => ({ apiRequest: vi.fn() }));

function Editor({ kind }: { kind: WorkflowNode["kind"] }) {
  const [node, setNode] = useState<WorkflowNode>({ id: "node", kind, label: "Step", config: {} });
  return <><WorkflowProperties node={node} orgId="org" disabled={false} onChange={setNode} onDelete={() => {}} /><output data-testid="node">{JSON.stringify(node)}</output></>;
}
test("condition editor preserves numeric, boolean and null comparison types", () => {
  render(<Editor kind="condition" />);
  fireEvent.change(screen.getByLabelText("Input field"), { target: { value: "input.amount" } });
  fireEvent.change(screen.getByLabelText("Comparison"), { target: { value: "gt" } });
  fireEvent.change(screen.getByLabelText("Value type"), { target: { value: "number" } });
  fireEvent.change(screen.getByLabelText("Comparison value"), { target: { value: "5000" } });
  expect(JSON.parse(screen.getByTestId("node").textContent!).config).toEqual({ field: "input.amount", operator: "gt", value: 5000 });
  fireEvent.change(screen.getByLabelText("Value type"), { target: { value: "boolean" } });
  expect(JSON.parse(screen.getByTestId("node").textContent!).config.value).toBe(true);
  fireEvent.change(screen.getByLabelText("Value type"), { target: { value: "null" } });
  expect(JSON.parse(screen.getByTestId("node").textContent!).config.value).toBeNull();
});
test("email fields produce recipient arrays and retain message text", () => {
  render(<Editor kind="email" />);
  fireEvent.change(screen.getByLabelText("Recipients (comma separated)"), { target: { value: "one@example.com,two@example.com" } });
  fireEvent.change(screen.getByLabelText("Email subject"), { target: { value: "Review completed" } });
  fireEvent.change(screen.getByLabelText("Email body"), { target: { value: "Your request is ready." } });
  expect(JSON.parse(screen.getByTestId("node").textContent!).config).toEqual({ to: ["one@example.com", "two@example.com"], subject: "Review completed", body: "Your request is ready." });
});
test("read-only settings cannot be edited or deleted", () => {
  const onChange = vi.fn();
  render(<WorkflowProperties node={{ id: "node", kind: "delay", label: "Delay", config: { seconds: 60 } }} orgId="org" disabled onChange={onChange} onDelete={vi.fn()} />);
  expect(screen.getByLabelText("Node label")).toBeDisabled();
  expect(screen.getByLabelText("Delay (seconds)")).toBeDisabled();
  expect(screen.queryByRole("button", { name: "Delete node" })).not.toBeInTheDocument();
  expect(onChange).not.toHaveBeenCalled();
});

test("approval settings use eligible organization members and load team choices", async () => {
  vi.mocked(apiRequest).mockImplementation(async (path) => path.endsWith("/members") ? {
    items: [{ id: "owner", email: "owner@example.com", role_code: "owner" }, { id: "viewer", email: "viewer@example.com", role_code: "viewer" }], next_cursor: null,
  } : { items: [{ id: "finance", name: "Finance" }], next_cursor: null });
  render(<Editor kind="approval" />);
  expect(await screen.findByRole("option", { name: "owner@example.com (owner)" })).toBeVisible();
  expect(screen.queryByRole("option", { name: /viewer@example.com/ })).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox", { name: "Approver" }), { target: { value: "owner" } });
  expect(JSON.parse(screen.getByTestId("node").textContent!).config.assignee).toEqual({ kind: "member", id: "owner" });
  fireEvent.change(screen.getByRole("combobox", { name: "Assign to" }), { target: { value: "team" } });
  expect(await screen.findByRole("option", { name: "Finance" })).toBeVisible();
  fireEvent.change(screen.getByRole("combobox", { name: "Approver" }), { target: { value: "finance" } });
  expect(JSON.parse(screen.getByTestId("node").textContent!).config.assignee).toEqual({ kind: "team", id: "finance" });
  expect(apiRequest).toHaveBeenCalledWith("/organizations/org/teams", "GET", undefined, expect.any(AbortSignal));
});
