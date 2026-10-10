import type { components } from "./api-schema";

export type Graph = components["schemas"]["GraphInput"];
export type WorkflowNode = components["schemas"]["NodeInput"];
export type WorkflowEdge = components["schemas"]["EdgeInput"];
export type NodeKind = WorkflowNode["kind"];
export type Branch = NonNullable<WorkflowEdge["branch"]>;
export const nodeCatalog: Record<NodeKind, { title: string; hint: string; symbol: string }> = {
  manual_trigger: { title: "Manual trigger", hint: "Start a workflow", symbol: "▶" },
  approval: { title: "Approval", hint: "Request a human decision", symbol: "✓" },
  condition: { title: "Condition", hint: "Choose between two paths", symbol: "◇" },
  email: { title: "Email", hint: "Define a notification", symbol: "✉" },
  webhook: { title: "Webhook", hint: "Define an HTTPS request", symbol: "↗" },
  delay: { title: "Delay", hint: "Define a waiting period", symbol: "◷" },
  end: { title: "End", hint: "Finish this path", symbol: "■" },
};
export function branches(kind: NodeKind): Branch[] {
  return kind === "end" ? [] : kind === "condition" ? ["true", "false"] : kind === "approval" ? ["approved", "rejected"] : ["next"];
}

// The advanced JSON editor may contain incomplete input. Never mount the canvas
// with a malformed graph or silently remove fields that the API should reject.
export function canvasGraph(text: string): Graph | null {
  try {
    const graph = JSON.parse(text);
    if (!graph || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) return null;
    const ids = new Set<string>();
    for (const node of graph.nodes) {
      if (!node || typeof node.id !== "string" || ids.has(node.id) || !Object.hasOwn(nodeCatalog, node.kind)) return null;
      if (node.label !== undefined && typeof node.label !== "string") return null;
      if (node.config !== undefined && (!node.config || typeof node.config !== "object" || Array.isArray(node.config))) return null;
      if (node.position && (!Number.isFinite(node.position.x) || !Number.isFinite(node.position.y))) return null;
      ids.add(node.id);
    }
    const edges = new Set<string>();
    for (const edge of graph.edges) {
      if (!edge || typeof edge.id !== "string" || edges.has(edge.id) || !ids.has(edge.source) || !ids.has(edge.target)) return null;
      if (edge.branch !== undefined && !["next", "true", "false", "approved", "rejected"].includes(edge.branch)) return null;
      edges.add(edge.id);
    }
    return graph;
  } catch { return null; }
}

export function connectionError(graph: Graph, source: string, target: string, branch: Branch): string | null {
  const from = graph.nodes?.find((node) => node.id === source);
  const to = graph.nodes?.find((node) => node.id === target);
  if (!from || !to) return "Choose both a source and a destination.";
  if (source === target) return "A node cannot connect to itself.";
  if (to.kind === "manual_trigger") return "The trigger cannot have incoming connections.";
  if (!branches(from.kind).includes(branch)) return "Choose an output branch supported by this node.";
  if (graph.edges?.some((edge) => edge.source === source && (edge.branch ?? "next") === branch)) return "This branch already has a connection. Remove it before reconnecting.";
  if ((graph.edges?.length ?? 0) >= 128) return "A graph can contain at most 128 connections.";
  const pending = [target], seen = new Set<string>();
  while (pending.length) {
    const current = pending.pop()!;
    if (current === source) return "This connection would create a cycle.";
    if (seen.has(current)) continue;
    seen.add(current);
    for (const edge of graph.edges ?? []) if (edge.source === current) pending.push(edge.target);
  }
  return null;
}

export function removeNodes(graph: Graph, ids: Set<string>): Graph {
  return { ...graph, nodes: graph.nodes?.filter((node) => !ids.has(node.id)), edges: graph.edges?.filter((edge) => !ids.has(edge.source) && !ids.has(edge.target)) };
}
