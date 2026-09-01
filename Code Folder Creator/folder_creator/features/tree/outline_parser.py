from __future__ import annotations

import re
from typing import Any


Node = dict[str, Any]


def _count_leading_whitespace(line: str) -> tuple[int, str]:
    match = re.match(r"^([ \t]*)(.*)$", line)
    if match is None:
        return 0, line
    return len(match.group(1)), match.group(2)


def parse_indented_text(text: str) -> list[Node]:
    """Convert an indented text outline into template-compatible tree nodes."""
    raw_lines = [
        raw.rstrip("\n\r")
        for raw in text.splitlines()
        if raw.strip() and not raw.lstrip().startswith("#")
    ]

    if not raw_lines:
        return []

    indents = []
    for line in raw_lines:
        whitespace_length, stripped = _count_leading_whitespace(line)
        if not stripped.strip():
            continue
        normalized = line[:whitespace_length].replace("\t", " " * 4)
        if normalized:
            indents.append(len(normalized))

    indent_unit = min(indents) if indents else 4
    roots: list[Node] = []
    stack: list[tuple[int, Node]] = []

    for line in raw_lines:
        whitespace_length, name = _count_leading_whitespace(line)
        normalized = line[:whitespace_length].replace("\t", " " * 4)
        depth = len(normalized) // indent_unit if indent_unit > 0 else 0
        node: Node = {"name": name.strip(), "children": []}

        if not stack:
            roots.append(node)
            stack.append((depth, node))
            continue

        last_depth, last_node = stack[-1]
        if depth > last_depth:
            last_node["children"].append(node)
            stack.append((depth, node))
            continue

        while stack and stack[-1][0] >= depth:
            stack.pop()

        if stack:
            stack[-1][1]["children"].append(node)
        else:
            roots.append(node)
        stack.append((depth, node))

    return roots
