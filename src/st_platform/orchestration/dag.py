"""Lightweight DAG orchestrator (M11 T-M11-03, Prefect-compatible subset)."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from collections.abc import Callable


@dataclass
class TaskNode:
    name: str
    fn: Callable[[], Any]
    deps: list[str] = field(default_factory=list)
    retries: int = 0


class DagRunner:
    def __init__(self):
        self.nodes: dict[str, TaskNode] = {}

    def add(self, node: TaskNode) -> None:
        self.nodes[node.name] = node

    def run(self) -> dict[str, Any]:
        # topo sort
        indeg = {n: 0 for n in self.nodes}
        adj = defaultdict(list)
        for n, node in self.nodes.items():
            for d in node.deps:
                adj[d].append(n)
                indeg[n] += 1
        q = deque([n for n, d in indeg.items() if d == 0])
        order = []
        while q:
            n = q.popleft()
            order.append(n)
            for m in adj[n]:
                indeg[m] -= 1
                if indeg[m] == 0:
                    q.append(m)
        if len(order) != len(self.nodes):
            raise ValueError("cycle detected in DAG")
        results = {}
        for n in order:
            node = self.nodes[n]
            attempt = 0
            while True:
                try:
                    results[n] = node.fn()
                    break
                except Exception:
                    if attempt < node.retries:
                        attempt += 1
                        continue
                    raise
        return results

    def visualize(self) -> str:
        lines = []
        for n, node in self.nodes.items():
            deps = ",".join(node.deps) if node.deps else "-"
            lines.append(f"{n} (deps={deps}, retries={node.retries})")
        return "\n".join(lines)