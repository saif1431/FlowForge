"""Bounded, deterministic graph validation; never executes user expressions or actions."""

from collections import deque
from uuid import UUID

from app.modules.workflows.schemas import (
    CONFIG_MODELS,
    ApprovalConfig,
    ConditionConfig,
    DelayConfig,
    EmailConfig,
    GraphInput,
    GraphIssue,
    GraphValidation,
    WebhookConfig,
)


def structural_issues(graph: GraphInput) -> list[GraphIssue]:
    issues: list[GraphIssue] = []
    nodes = {node.id for node in graph.nodes}
    if len(nodes) != len(graph.nodes):
        issues.append(GraphIssue(code="DUPLICATE_NODE", message="Node IDs must be unique."))
    if len({edge.id for edge in graph.edges}) != len(graph.edges):
        issues.append(GraphIssue(code="DUPLICATE_EDGE", message="Edge IDs must be unique."))
    branches: set[tuple[UUID, str]] = set()
    for edge in graph.edges:
        if edge.source not in nodes or edge.target not in nodes:
            issues.append(
                GraphIssue(
                    code="MISSING_ENDPOINT",
                    message="An edge references a missing node.",
                    edge_id=edge.id,
                )
            )
        if (edge.source, edge.branch) in branches:
            issues.append(
                GraphIssue(
                    code="DUPLICATE_BRANCH",
                    message="Each source branch can have only one edge.",
                    edge_id=edge.id,
                )
            )
        branches.add((edge.source, edge.branch))
    return issues


def validate_graph(graph: GraphInput) -> GraphValidation:
    issues = structural_issues(graph)
    if issues:
        return GraphValidation(valid=False, issues=issues)
    triggers = [node.id for node in graph.nodes if node.kind == "manual_trigger"]
    ends = [node.id for node in graph.nodes if node.kind == "end"]
    if len(triggers) != 1:
        issues.append(
            GraphIssue(code="TRIGGER_COUNT", message="The graph needs exactly one manual trigger.")
        )
    if not ends:
        issues.append(
            GraphIssue(code="END_REQUIRED", message="The graph needs at least one End node.")
        )
    outgoing: dict[UUID, list[UUID]] = {node.id: [] for node in graph.nodes}
    incoming: dict[UUID, list[UUID]] = {node.id: [] for node in graph.nodes}
    branches: dict[UUID, set[str]] = {node.id: set() for node in graph.nodes}
    for edge in graph.edges:
        outgoing[edge.source].append(edge.target)
        incoming[edge.target].append(edge.source)
        branches[edge.source].add(edge.branch)
    for node in graph.nodes:
        expected = {
            "condition": {"true", "false"},
            "approval": {"approved", "rejected"},
            "end": set(),
        }.get(node.kind, {"next"})
        if branches[node.id] != expected:
            issues.append(
                GraphIssue(
                    code="BRANCHES_INVALID",
                    message=f"{node.kind} requires branches: "
                    f"{', '.join(sorted(expected)) or 'none'}.",
                    node_id=node.id,
                )
            )
        if node.kind == "manual_trigger" and incoming[node.id]:
            issues.append(
                GraphIssue(
                    code="TRIGGER_INCOMING",
                    message="The trigger cannot have incoming edges.",
                    node_id=node.id,
                )
            )
        config = CONFIG_MODELS[node.kind].model_validate(node.config)
        incomplete = (
            isinstance(config, ApprovalConfig)
            and config.assignee is None
            or isinstance(config, ConditionConfig)
            and config.field is None
            or isinstance(config, EmailConfig)
            and (not config.to or not config.subject.strip() or not config.body.strip())
            or isinstance(config, WebhookConfig)
            and config.url is None
            or isinstance(config, DelayConfig)
            and config.seconds is None
        )
        if incomplete:
            issues.append(
                GraphIssue(
                    code="CONFIG_INCOMPLETE",
                    message="Complete the node configuration before publishing.",
                    node_id=node.id,
                )
            )
        if (
            isinstance(config, ConditionConfig)
            and config.operator in {"gt", "gte", "lt", "lte"}
            and type(config.value) not in (int, float)
        ):
            issues.append(
                GraphIssue(
                    code="CONDITION_VALUE",
                    message="Ordered comparisons require a numeric value.",
                    node_id=node.id,
                )
            )
    degree = {key: len(value) for key, value in incoming.items()}
    pending = deque(key for key, value in degree.items() if value == 0)
    visited = 0
    while pending:
        current = pending.popleft()
        visited += 1
        for target in outgoing[current]:
            degree[target] -= 1
            if degree[target] == 0:
                pending.append(target)
    if visited != len(graph.nodes):
        issues.append(GraphIssue(code="CYCLE", message="Workflow graphs cannot contain cycles."))

    def reachable(starts: list[UUID], links: dict[UUID, list[UUID]]) -> set[UUID]:
        seen: set[UUID] = set()
        queue = list(starts)
        while queue:
            current = queue.pop()
            if current not in seen:
                seen.add(current)
                queue.extend(links[current])
        return seen

    from_start = reachable(triggers, outgoing)
    to_end = reachable(ends, incoming)
    for node in graph.nodes:
        if len(triggers) == 1 and node.id not in from_start:
            issues.append(
                GraphIssue(
                    code="UNREACHABLE",
                    message="Every node must be reachable from the trigger.",
                    node_id=node.id,
                )
            )
        if node.id not in to_end:
            issues.append(
                GraphIssue(
                    code="NO_END_PATH",
                    message="Every node must have a path to an End node.",
                    node_id=node.id,
                )
            )
    return GraphValidation(valid=not issues, issues=issues)
