#!/usr/bin/env python3
"""Validate a staged Obsidian note before it replaces a source note."""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:
    raise SystemExit("Validation requires PyYAML; do not commit the staged note.") from exc

REQUIRED_KEYS = {"author", "description", "source", "published", "clipped", "tags", "category", "key_points", "quality", "related_concepts", "aliases"}

def read_utf8(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"Cannot read valid UTF-8: {path}: {exc}") from exc

def split_frontmatter(text: str, path: Path) -> tuple[dict, str]:
    normal = text.replace("\r\n", "\n")
    if not normal.startswith("---\n"):
        raise ValueError(f"Missing opening YAML delimiter: {path}")
    end = normal.find("\n---\n", 4)
    if end < 0:
        raise ValueError(f"Missing closing YAML delimiter: {path}")
    try:
        data = yaml.safe_load(normal[4:end])
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Frontmatter must be a mapping: {path}")
    return data, normal[end + 5:]

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("staged", type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--original-name", required=True)
    args = parser.parse_args()
    staged_data, staged_body = split_frontmatter(read_utf8(args.staged), args.staged)
    _, source_body = split_frontmatter(read_utf8(args.source), args.source)
    missing = REQUIRED_KEYS - staged_data.keys()
    if missing:
        raise ValueError(f"Missing required frontmatter keys: {', '.join(sorted(missing))}")
    if not isinstance(staged_data["aliases"], list) or args.original_name not in staged_data["aliases"]:
        raise ValueError("aliases must include the complete original filename without .md")
    if not isinstance(staged_data["category"], str) or not staged_data["category"].strip():
        raise ValueError("category must be a non-empty string")
    if not isinstance(staged_data["quality"], int) or not 1 <= staged_data["quality"] <= 5:
        raise ValueError("quality must be an integer from 1 to 5")
    for key in ("tags", "key_points", "related_concepts"):
        if not isinstance(staged_data[key], list) or not all(isinstance(item, str) for item in staged_data[key]):
            raise ValueError(f"{key} must be a list of strings")
    if staged_body != source_body:
        before = hashlib.sha256(source_body.encode()).hexdigest()[:12]
        after = hashlib.sha256(staged_body.encode()).hexdigest()[:12]
        raise ValueError(f"Body changed (source {before}, staged {after})")
    print("OK: UTF-8, YAML, required fields, alias, and body integrity verified")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        raise SystemExit(1)
