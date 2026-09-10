"""Read-only metadata recall scoped to the configured archive."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys

import yaml

from configure import load
from save_notes import Invalid, UniqueLoader, reject_links


def header(path):
    with path.open(encoding="utf-8-sig") as stream:
        if stream.readline().strip() != "---":
            raise Invalid("Missing metadata header")
        lines, size = [], 0
        for line in stream:
            size += len(line.encode("utf-8"))
            if size > 65536:
                raise Invalid("Metadata header exceeds 64 KiB")
            if line.strip() == "---":
                value = yaml.load("".join(lines), Loader=UniqueLoader)
                if not isinstance(value, dict):
                    raise Invalid("Metadata is not a mapping")
                return value
            lines.append(line)
    raise Invalid("Metadata header never closed")


def search(config_file=None, query="", task_id=None, note_type=None, limit=5):
    config = load(config_file)
    archive = Path(config["vault_root"]) / config["archive_root"]
    if not 1 <= limit <= 50:
        raise Invalid("limit must be between 1 and 50")
    tokens = [x.casefold() for x in re.split(r"\s+", query.strip()) if x]
    candidates, issues, count = [], [], 0
    if not archive.exists():
        return {"candidates": [], "scanned_headers": 0, "issues": []}
    reject_links(archive)

    def add_issue(path, error):
        issues.append({"path": str(path), "error": str(error)})

    for directory, dirs, files in os.walk(archive, followlinks=False, onerror=lambda e: add_issue(e.filename, e)):
        safe_dirs = []
        for name in dirs:
            if name.startswith("."):
                continue
            try:
                reject_links(Path(directory) / name)
                safe_dirs.append(name)
            except Invalid as error:
                add_issue(Path(directory) / name, error)
        dirs[:] = safe_dirs
        for name in files:
            if not name.endswith(".md") or name.startswith("."):
                continue
            path = Path(directory) / name
            try:
                reject_links(path)
                count += 1
                data = header(path)
                for key in ("id", "task_id", "type", "created", "summary"):
                    if not isinstance(data.get(key), str):
                        raise Invalid(f"Missing/non-string metadata: {key}")
                timestamp = datetime.fromisoformat(data["created"])
                if timestamp.tzinfo is None:
                    raise Invalid("Timestamp lacks timezone")
                if task_id and data["task_id"] != task_id:
                    continue
                if note_type and data["type"] != note_type:
                    continue
                haystack = json.dumps({k: data.get(k) for k in ("summary", "tags", "project", "domain", "task_id")}, ensure_ascii=False).casefold() + " " + path.stem.casefold()
                score = sum(1 for token in tokens if token in haystack)
                if tokens and not score:
                    continue
                item = {k: data.get(k) for k in ("id", "task_id", "type", "created", "status", "summary", "previous", "supersedes") if k in data}
                item.update(path=str(path), score=score)
                candidates.append((score, timestamp.timestamp(), str(path), item))
            except (OSError, ValueError, TypeError, yaml.YAMLError) as error:
                add_issue(path, error)
    candidates.sort(key=lambda x: x[:3], reverse=True)
    return {"candidates": [x[3] for x in candidates[:limit]], "scanned_headers": count, "issues": issues[:20], "issue_count": len(issues)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--query", default="")
    parser.add_argument("--task-id")
    parser.add_argument("--type", choices=("session", "decision", "prompt", "code", "lesson"))
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    try:
        result = search(args.config, args.query, args.task_id, args.type, args.limit)
    except (OSError, ValueError, TypeError) as error:
        result = {"error": str(error)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if "error" in result or result.get("issue_count", 0) else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
