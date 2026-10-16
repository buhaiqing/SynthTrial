#!/usr/bin/env python3
"""Generate the package-dependency mermaid diagram in docs/design.md §11.4.

The diagram is a CLAIM about the real import graph, so it is generated from that
graph rather than drawn by hand. A hand-drawn dependency diagram drifts silently:
it keeps looking self-consistent long after the code moved. Generating it makes
the claim falsifiable on every run.

    python3 tools/gen_dep_graph.py            # print the mermaid block
    python3 tools/gen_dep_graph.py --check    # exit 1 if docs/design.md is stale
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "st_platform"
DESIGN_MD = pathlib.Path(__file__).resolve().parents[1] / "docs" / "design.md"

# Root package labels, keyed by the on-disk name (dir or module stem).
LABELS = {
    "cli": "cli/stctl.py",
    "task": "task/",
    "inference": "inference/",
    "infer": "infer/",
    "safety": "safety/",
    "report": "report/",
    "registry": "registry/",
    "dataset": "dataset/",
    "audit": "audit/",
    "common": "common/",
    "store": "store.py",
    "evaluation": "evaluation/",
}
# Internal self-imports (a package re-exporting its own submodules) carry no
# architectural meaning and would clutter the diagram.
SELF_NOISE = {"common.version"}


def package_of(path: pathlib.Path) -> str | None:
    rel = path.relative_to(SRC)
    if len(rel.parts) == 1 and rel.suffix == ".py" and rel.stem != "__init__":
        return rel.stem
    if len(rel.parts) > 1:
        return rel.parts[0]
    return None


def package_from_dotted(target: str) -> str | None:
    """'st_platform.audit.ledger' -> 'audit';  'st_platform.store' -> 'store'."""
    parts = target.split(".")
    return parts[1] if len(parts) >= 2 else None


def real_edges() -> set[tuple[str, str]]:
    """(importer, imported) pairs derived from actual `from st_platform.*` imports."""
    edges: set[tuple[str, str]] = set()
    for py in sorted(SRC.rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        src = package_of(py)
        if src is None:
            continue
        for line in py.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*from\s+(st_platform\.[A-Za-z0-9_.]*)\s+import", line)
            if not m:
                continue
            target = m.group(1)
            if target in SELF_NOISE:
                continue
            dst = package_from_dotted(target)
            if dst is None or dst == src:
                continue
            edges.add((src, dst))
    return edges


def node_id(name: str) -> str:
    return "N_" + name.upper()


def render(edges: set[tuple[str, str]]) -> str:
    nodes = sorted({n for e in edges for n in e})
    lines = ["```mermaid", "flowchart LR"]
    for n in nodes:
        lines.append(f'    {node_id(n)}["{LABELS.get(n, n)}"]')
    lines.append("")
    for src, dst in sorted(edges):
        lines.append(f"    {node_id(src)} --> {node_id(dst)}")
    lines.append("")
    lines.append("    classDef orch fill:#e1f5fe,stroke:#0277bd,stroke-width:2px")
    lines.append("    classDef leaf fill:#eceff1,stroke:#607d8b")
    orch = [n for n in nodes if n in {"cli", "evaluation"}]
    leaf = [n for n in nodes if n in {"common", "dataset", "audit", "registry", "store"}]
    if orch:
        lines.append("    class " + ",".join(node_id(n) for n in orch) + " orch")
    if leaf:
        lines.append("    class " + ",".join(node_id(n) for n in leaf) + " leaf")
    lines.append("```")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    block = render(real_edges())
    if not args.check:
        print(block)
        return 0

    if not DESIGN_MD.exists():
        print(f"{DESIGN_MD} not found", file=sys.stderr)
        return 1
    if block not in DESIGN_MD.read_text(encoding="utf-8"):
        print("STALE: docs/design.md §11.4 does not match the real import graph.")
        print("Regenerate and paste, or run: python3 tools/gen_dep_graph.py")
        return 1
    print("up to date: docs/design.md §11.4 matches the real import graph")
    return 0


if __name__ == "__main__":
    sys.exit(main())
