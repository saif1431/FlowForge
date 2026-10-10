"use client";

import { memo, useMemo, useState } from "react";
import { Background, Controls, Handle, MarkerType, MiniMap, Position, ReactFlow, type Node, type NodeProps, type Edge, type Connection } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { components } from "../lib/api-schema";
import { branches, connectionError, nodeCatalog, removeNodes, type Branch, type Graph, type NodeKind, type WorkflowNode } from "../lib/workflow-graph";
import WorkflowProperties from "./workflow-properties";

type CanvasNode = Node<{ node: WorkflowNode; invalid: boolean }, "workflow">;
const WorkflowCard = memo(function WorkflowCard({ data, selected, isConnectable }: NodeProps<CanvasNode>) {
  const node = data.node, info = nodeCatalog[node.kind], outputs = branches(node.kind);
  return <div className={`workflow-node node-${node.kind}${selected ? " is-selected" : ""}${data.invalid ? " is-invalid" : ""}`}>
    {node.kind !== "manual_trigger" && <Handle type="target" position={Position.Left} id="input" isConnectable={isConnectable} aria-label="Input" />}
    <span className="node-kind">{info.symbol} {info.title}</span>
    <strong>{node.label || info.title}</strong>
    {data.invalid && <span className="node-error">Needs attention</span>}
    <div className="node-outputs">{outputs.map((branch) => <span key={branch}>{branch}</span>)}</div>
    {outputs.map((branch, index) => <Handle key={branch} type="source" position={Position.Right} id={branch} isConnectable={isConnectable} style={{ top: `${(index + 1) * 100 / (outputs.length + 1)}%` }} aria-label={`${branch} output`} />)}
  </div>;
});
const nodeTypes = { workflow: WorkflowCard };

export default function WorkflowBuilder({ graph, onChange, readOnly, orgId, issues = [] }: {
  graph: Graph; onChange: (graph: Graph) => void; readOnly: boolean; orgId: string;
  issues?: components["schemas"]["GraphIssue"][];
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");
  const [branch, setBranch] = useState<Branch>("next");
  const [measurements, setMeasurements] = useState<Record<string, { width: number; height: number }>>({});
  const selectedNode = graph.nodes?.find((node) => node.id === selected);
  const sourceNode = graph.nodes?.find((node) => node.id === source);
  const nodes = useMemo<CanvasNode[]>(() => (graph.nodes ?? []).map((node) => ({
    id: node.id, type: "workflow", position: node.position ?? { x: 0, y: 0 },
    measured: measurements[node.id],
    data: { node, invalid: issues.some((issue) => issue.node_id === node.id) },
    selected: node.id === selected, ariaLabel: `${nodeCatalog[node.kind].title}: ${node.label || "Untitled"}`,
  })), [graph.nodes, issues, selected, measurements]);
  const edges = useMemo<Edge[]>(() => (graph.edges ?? []).map((edge) => ({
    id: edge.id, source: edge.source, target: edge.target, sourceHandle: edge.branch ?? "next", targetHandle: "input",
    label: edge.branch ?? "next", type: "smoothstep", selected: edge.id === selectedEdge,
    markerEnd: { type: MarkerType.ArrowClosed },
    style: { stroke: issues.some((issue) => issue.edge_id === edge.id) ? "#be123c" : "#5b7886", strokeWidth: 2 },
  })), [graph.edges, issues, selectedEdge]);

  function add(kind: NodeKind) {
    if (readOnly) return;
    if ((graph.nodes?.length ?? 0) >= 64) { setNotice("A graph can contain at most 64 nodes."); return; }
    const id = crypto.randomUUID(), index = graph.nodes?.length ?? 0;
    onChange({ ...graph, nodes: [...(graph.nodes ?? []), { id, kind, label: nodeCatalog[kind].title, config: {}, position: { x: 60 + index % 3 * 260, y: 60 + Math.floor(index / 3) * 180 } }] });
    setSelected(id); setNotice("");
  }

  function connect(connection: Connection) {
    if (readOnly) return;
    const output = (connection.sourceHandle ?? "next") as Branch;
    const error = connectionError(graph, connection.source, connection.target, output);
    if (error) { setNotice(error); return; }
    onChange({ ...graph, edges: [...(graph.edges ?? []), { id: crypto.randomUUID(), source: connection.source, target: connection.target, branch: output }] });
    setNotice("");
  }

  function updateNode(node: WorkflowNode) {
    if (!readOnly) onChange({ ...graph, nodes: graph.nodes?.map((item) => item.id === node.id ? node : item) });
  }

  return <div className="workflow-builder">
    <div className="builder-intro"><div><span className="eyebrow">WORKFLOW STUDIO</span><h3>Visual workflow builder</h3></div><span className="builder-badge">{readOnly ? "Read-only" : "Editing draft"}</span></div>
    <p className="builder-hint">Add steps, drag to arrange, and connect an output dot to an input dot. Select a step to configure it. You can also connect steps using the form below.</p>
    {!readOnly && <div className="builder-palette" aria-label="Node palette">{Object.entries(nodeCatalog).map(([kind, info]) => <button type="button" key={kind} title={info.hint} onClick={() => add(kind as NodeKind)} disabled={(graph.nodes?.length ?? 0) >= 64 || kind === "manual_trigger" && graph.nodes?.some((node) => node.kind === "manual_trigger")}><span aria-hidden="true">{info.symbol}</span> Add {info.title}</button>)}</div>}
    <div className="builder-workspace">
      <div className="builder-canvas" aria-label="Workflow canvas">
        <ReactFlow<CanvasNode> nodes={nodes} edges={edges} nodeTypes={nodeTypes}
          onNodesChange={(changes) => {
            const dimensions = changes.filter((change) => change.type === "dimensions");
            if (dimensions.length) setMeasurements((previous) => {
              const next = { ...previous };
              let changed = false;
              for (const change of dimensions) if (change.dimensions && (previous[change.id]?.width !== change.dimensions.width || previous[change.id]?.height !== change.dimensions.height)) {
                next[change.id] = change.dimensions; changed = true;
              }
              return changed ? next : previous;
            });
            const selection = changes.find((change) => change.type === "select" && change.selected);
            if (selection && "id" in selection) setSelected(selection.id);
            if (readOnly) return;
            let next = graph;
            const removed = new Set(changes.filter((change) => change.type === "remove").map((change) => change.id));
            if (removed.size) next = removeNodes(next, removed);
            const moves = changes.filter((change) => change.type === "position");
            if (moves.length) next = { ...next, nodes: next.nodes?.map((node) => {
              const move = moves.find((change) => change.id === node.id);
              return move?.position ? { ...node, position: move.position } : node;
            }) };
            if (next !== graph) onChange(next);
          }}
          onEdgesChange={(changes) => {
            if (readOnly) return;
            const removed = new Set(changes.filter((change) => change.type === "remove").map((change) => change.id));
            if (removed.size) onChange({ ...graph, edges: graph.edges?.filter((edge) => !removed.has(edge.id)) });
          }}
          onNodeClick={(_, node) => { setSelected(node.id); setSelectedEdge(null); }}
          onEdgeClick={(_, edge) => { setSelectedEdge(edge.id); setSelected(null); }}
          onPaneClick={() => { setSelected(null); setSelectedEdge(null); }}
          onBeforeDelete={async ({ nodes: deletedNodes, edges: deletedEdges }) => {
            if (!readOnly) {
              const next = removeNodes(graph, new Set(deletedNodes.map((node) => node.id)));
              const edgeIds = new Set(deletedEdges.map((edge) => edge.id));
              onChange({ ...next, edges: next.edges?.filter((edge) => !edgeIds.has(edge.id)) });
            }
            // Apply the complete deletion atomically, not separate callbacks
            // that could restore stale nodes while removing their edges.
            return false;
          }}
          onConnect={connect} nodesDraggable={!readOnly} nodesConnectable={!readOnly} edgesReconnectable={false}
          deleteKeyCode={readOnly ? null : ["Backspace", "Delete"]} nodeExtent={[[-100000, -100000], [100000, 100000]]}
          fitView fitViewOptions={{ maxZoom: 1, padding: 0.25 }} minZoom={0.15} maxZoom={1.5}>
          <Background gap={20} size={1} /><Controls showInteractive={false} /><MiniMap pannable zoomable />
        </ReactFlow>
        {!nodes.length && <div className="builder-empty">{readOnly ? "This version has no steps." : "Start with a Manual trigger, then add the steps in your process."}</div>}
      </div>
      {selectedNode ? <WorkflowProperties key={selectedNode.id} node={selectedNode} orgId={orgId} disabled={readOnly} onChange={updateNode} onDelete={() => { if (!readOnly) { onChange(removeNodes(graph, new Set([selectedNode.id]))); setSelected(null); } }} /> : <aside className="builder-properties"><h3>Step settings</h3><p>Select a step on the canvas or in the list below to inspect its settings.</p>{selectedEdge && !readOnly && <button type="button" className="danger-button" onClick={() => { onChange({ ...graph, edges: graph.edges?.filter((edge) => edge.id !== selectedEdge) }); setSelectedEdge(null); }}>Delete connection</button>}</aside>}
    </div>
    {notice && <p role="alert" className="auth-error">{notice}</p>}
    <div className="builder-node-list" aria-label="Workflow steps">{(graph.nodes ?? []).map((node) => <button key={node.id} type="button" aria-pressed={selected === node.id} onClick={() => setSelected(node.id)}>{node.label || nodeCatalog[node.kind].title}</button>)}</div>
    <details className="builder-connections"><summary>Connections ({graph.edges?.length ?? 0})</summary>
      {!readOnly && <form className="builder-connect-form" onSubmit={(event) => { event.preventDefault(); connect({ source, target, sourceHandle: branch, targetHandle: "input" }); }}>
        <label>From step<select value={source} onChange={(event) => { setSource(event.target.value); const node = graph.nodes?.find((item) => item.id === event.target.value); setBranch(node ? branches(node.kind)[0] ?? "next" : "next"); }}><option value="">Choose a step</option>{graph.nodes?.filter((node) => node.kind !== "end").map((node) => <option value={node.id} key={node.id}>{node.label || nodeCatalog[node.kind].title}</option>)}</select></label>
        <label>Output branch<select value={branch} onChange={(event) => setBranch(event.target.value as Branch)}>{(sourceNode ? branches(sourceNode.kind) : ["next"]).map((output) => <option key={output}>{output}</option>)}</select></label>
        <label>To step<select value={target} onChange={(event) => setTarget(event.target.value)}><option value="">Choose a step</option>{graph.nodes?.filter((node) => node.kind !== "manual_trigger" && node.id !== source).map((node) => <option value={node.id} key={node.id}>{node.label || nodeCatalog[node.kind].title}</option>)}</select></label>
        <button type="submit" disabled={!source || !target}>Connect steps</button>
      </form>}
      <ul>{graph.edges?.map((edge) => <li key={edge.id}><span>{graph.nodes?.find((node) => node.id === edge.source)?.label || "Step"} → <strong>{edge.branch ?? "next"}</strong> → {graph.nodes?.find((node) => node.id === edge.target)?.label || "Step"}</span>{!readOnly && <button type="button" aria-label={`Remove ${edge.branch ?? "next"} connection from ${graph.nodes?.find((node) => node.id === edge.source)?.label || "step"}`} onClick={() => onChange({ ...graph, edges: graph.edges?.filter((item) => item.id !== edge.id) })}>Remove</button>}</li>)}</ul>
    </details>
  </div>;
}
