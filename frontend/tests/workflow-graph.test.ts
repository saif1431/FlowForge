import { expect, test } from "vitest";
import { canvasGraph, connectionError, removeNodes, type Graph } from "../src/lib/workflow-graph";
import { createWorkflowDraft } from "../src/lib/workflow-draft";

const graph: Graph = {
  nodes: [{ id: "start", kind: "manual_trigger", label: "Start" }, { id: "condition", kind: "condition", label: "Condition" }, { id: "end", kind: "end", label: "End" }],
  edges: [{ id: "e1", source: "start", target: "condition", branch: "next" }],
};
test("connections enforce single outputs, direction, and acyclic paths", () => {
  expect(connectionError(graph, "condition", "end", "true")).toBeNull();
  expect(connectionError(graph, "condition", "end", "false")).toBeNull();
  expect(connectionError(graph, "start", "end", "next")).toContain("already has");
  expect(connectionError(graph, "end", "condition", "next")).toContain("supported");
  expect(connectionError(graph, "condition", "start", "true")).toContain("trigger");
  expect(connectionError(graph, "condition", "condition", "true")).toContain("itself");
  const loop: Graph = { nodes: [...graph.nodes!, { id: "delay", kind: "delay", label: "Delay" }], edges: [...graph.edges!, { id: "e2", source: "condition", target: "delay", branch: "true" }] };
  expect(connectionError(loop, "delay", "condition", "next")).toContain("cycle");
});
test("deleting a node also removes its incoming and outgoing connections", () => {
  const updated = removeNodes(graph, new Set(["condition"]));
  expect(updated.nodes?.map((node) => node.id)).toEqual(["start", "end"]);
  expect(updated.edges).toEqual([]);
  expect(graph.edges).toHaveLength(1);
});
test("advanced input cannot crash the canvas or silently lose unknown fields", () => {
  expect(canvasGraph("not JSON")).toBeNull();
  expect(canvasGraph('{"nodes":[null],"edges":[]}')).toBeNull();
  expect(canvasGraph(JSON.stringify({ nodes: [{ id: "a", kind: "unknown" }], edges: [] }))).toBeNull();
  expect(canvasGraph(JSON.stringify({ ...graph, nodes: [graph.nodes![0], graph.nodes![0]] }))).toBeNull();
  expect(canvasGraph(JSON.stringify({ ...graph, extra: "keep" }))).toEqual({ ...graph, extra: "keep" });
});
test("draft stores keep unsaved tenant data isolated and preserve the saved baseline", () => {
  const first = createWorkflowDraft(), second = createWorkflowDraft();
  first.getState().setSavedText("saved"); first.getState().setEditor("local edits");
  expect(first.getState().savedText).toBe("saved");
  expect(second.getState().editor).toBe("");
});
