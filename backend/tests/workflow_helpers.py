from typing import Any
from uuid import uuid4


def graph(kind: str | None = None, config: dict[str, Any] | None = None) -> dict[str, Any]:
    start, middle, end = (str(uuid4()) for _ in range(3))
    nodes: list[dict[str, Any]] = [
        {"id": start, "kind": "manual_trigger"},
        {"id": end, "kind": "end"},
    ]
    edges: list[dict[str, Any]] = []
    if kind:
        nodes.insert(1, {"id": middle, "kind": kind, "config": config or {}})
        edges.append({"id": str(uuid4()), "source": start, "target": middle, "branch": "next"})
        branches = {"condition": ("true", "false"), "approval": ("approved", "rejected")}.get(
            kind, ("next",)
        )
        edges.extend(
            {"id": str(uuid4()), "source": middle, "target": end, "branch": branch}
            for branch in branches
        )
    else:
        edges.append({"id": str(uuid4()), "source": start, "target": end, "branch": "next"})
    return {"nodes": nodes, "edges": edges}
