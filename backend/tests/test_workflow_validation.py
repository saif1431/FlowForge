from uuid import uuid4

import pytest
from pydantic import ValidationError
from workflow_helpers import graph

from app.modules.workflows.schemas import GraphInput
from app.modules.workflows.validation import validate_graph


@pytest.mark.parametrize(
    "kind, config",
    [
        (None, {}),
        ("condition", {"field": "input.amount", "operator": "gt", "value": 1}),
        ("condition", {"field": "input.active", "value": True}),
        ("approval", {"assignee": {"kind": "member", "id": str(uuid4())}, "due_after_minutes": 60}),
        ("email", {"to": ["finance@example.com"], "subject": "Review", "body": "Ready"}),
        ("webhook", {"url": "https://example.com/event"}),
        ("delay", {"seconds": 10}),
    ],
)
def test_all_node_types_and_single_branch_merges(
    kind: str | None, config: dict[str, object]
) -> None:
    report = validate_graph(GraphInput.model_validate(graph(kind, config)))
    assert report.valid, report.issues


@pytest.mark.parametrize(
    "change, code",
    [
        ("empty", "TRIGGER_COUNT"),
        ("missing_end", "END_REQUIRED"),
        ("two_triggers", "TRIGGER_COUNT"),
        ("cycle", "CYCLE"),
        ("unreachable", "UNREACHABLE"),
        ("missing_branch", "BRANCHES_INVALID"),
        ("end_edge", "BRANCHES_INVALID"),
        ("duplicate_node", "DUPLICATE_NODE"),
        ("duplicate_edge", "DUPLICATE_EDGE"),
        ("missing_endpoint", "MISSING_ENDPOINT"),
        ("duplicate_branch", "DUPLICATE_BRANCH"),
        ("incomplete", "CONFIG_INCOMPLETE"),
        ("string_order", "CONDITION_VALUE"),
    ],
)
def test_invalid_graphs_report_actionable_errors(change: str, code: str) -> None:
    data = graph("condition", {"field": "input.amount", "operator": "gt", "value": 1})
    nodes, edges = data["nodes"], data["edges"]
    if change == "empty":
        data = {"nodes": [], "edges": []}
    elif change == "missing_end":
        nodes[-1]["kind"] = "delay"
    elif change == "two_triggers":
        nodes.append({"id": str(uuid4()), "kind": "manual_trigger"})
    elif change == "cycle":
        edges[-1]["target"] = nodes[0]["id"]
    elif change == "unreachable":
        nodes.append({"id": str(uuid4()), "kind": "end"})
    elif change == "missing_branch":
        edges.pop()
    elif change == "end_edge":
        edges.append({"id": str(uuid4()), "source": nodes[-1]["id"], "target": nodes[0]["id"]})
    elif change == "duplicate_node":
        nodes.append(nodes[0])
    elif change == "duplicate_edge":
        edges.append(edges[0])
    elif change == "missing_endpoint":
        edges[0]["target"] = str(uuid4())
    elif change == "duplicate_branch":
        edges.append({**edges[0], "id": str(uuid4())})
    elif change == "incomplete":
        nodes[1]["config"] = {}
    elif change == "string_order":
        nodes[1]["config"]["value"] = "1"
    report = validate_graph(GraphInput.model_validate(data))
    assert not report.valid and code in {issue.code for issue in report.issues}


@pytest.mark.parametrize(
    "kind, config",
    [
        ("condition", {"field": "__import__('os').system('whoami')"}),
        ("condition", {"field": "input.amount", "value": float("inf")}),
        ("condition", {"field": "input.amount", "value": {"secret": "x"}}),
        ("email", {"to": ["invalid"]}),
        ("delay", {"seconds": -1}),
        ("approval", {"assignee": {"kind": "anyone", "id": str(uuid4())}}),
        ("webhook", {"url": "https://127.0.0.1/path"}),
        ("webhook", {"url": "https://10.0.0.1/path"}),
        ("webhook", {"url": "http://example.com"}),
        ("webhook", {"url": "https://user:secret@example.com"}),
        ("webhook", {"url": "https://example.com?token=secret"}),
        ("webhook", {"url": "https://example.com", "headers": {"Authorization": "secret"}}),
        ("manual_trigger", {"password": "secret"}),
    ],
)
def test_config_allowlists_reject_unsafe_and_malformed_input(
    kind: str, config: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        GraphInput.model_validate(graph(kind, config))


def test_graph_limits_and_finite_coordinates() -> None:
    with pytest.raises(ValidationError):
        GraphInput.model_validate(
            {"nodes": [{"id": str(uuid4()), "kind": "end"} for _ in range(65)]}
        )
    data = graph()
    data["nodes"][0]["position"] = {"x": float("nan"), "y": 0}
    with pytest.raises(ValidationError):
        GraphInput.model_validate(data)
