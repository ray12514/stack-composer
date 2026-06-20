from __future__ import annotations

from pathlib import Path
from typing import Any

TODO_HEADER = "# TODO(scaffold): Review this generated template before promoting it.\n"


def write_text_with_todo(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.startswith("# TODO"):
        text = TODO_HEADER + text
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def copy_path_tree_with_todos(source: Path, destination: Path) -> None:
    for path in sorted(p for p in source.rglob("*") if p.is_file()):
        relative = path.relative_to(source)
        write_text_with_todo(destination / relative, path.read_text(encoding="utf-8"))


def copy_resource_tree_with_todos(resource: Any, destination: Path) -> None:
    for child in sorted(resource.iterdir(), key=lambda item: item.name):
        target = destination / child.name
        if child.is_dir():
            copy_resource_tree_with_todos(child, target)
            continue
        write_text_with_todo(target, child.read_text(encoding="utf-8"))
