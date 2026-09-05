from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from common import local_timestamp, read_json, write_json


PREFIX = "xiaohongshu-obsidian-note-"
MARKER = ".xiaohongshu-obsidian-note-run.json"


def create_workspace(base_dir: Path | None) -> Path:
    if base_dir is not None:
        base_dir.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix=PREFIX, dir=str(base_dir) if base_dir else None)).resolve()
    write_json(path / MARKER, {"tool": "xiaohongshu-obsidian-note", "path": str(path), "created_at": local_timestamp()})
    return path


def validate_workspace(path: Path) -> None:
    resolved = path.expanduser().resolve()
    forbidden = {Path(resolved.anchor).resolve(), Path.home().resolve(), Path.cwd().resolve()}
    if resolved in forbidden or not resolved.name.startswith(PREFIX):
        raise ValueError(f"Refusing unsafe cleanup target: {resolved}")
    marker_path = resolved / MARKER
    if not marker_path.is_file():
        raise ValueError(f"Missing workspace marker: {marker_path}")
    marker = read_json(marker_path)
    if marker.get("tool") != "xiaohongshu-obsidian-note" or Path(str(marker.get("path", ""))).resolve() != resolved:
        raise ValueError("Workspace marker does not match cleanup target")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or clean a guarded temporary workspace")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--base-dir", type=Path, help="Optional temporary root, mainly for controlled tests")
    cleanup_parser = subparsers.add_parser("cleanup")
    cleanup_parser.add_argument("--path", type=Path, required=True)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--path", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "create":
        path = create_workspace(args.base_dir.resolve() if args.base_dir else None)
        print(json.dumps({"created": True, "run_dir": str(path)}, ensure_ascii=False))
        return 0
    if args.command == "status":
        validate_workspace(args.path)
        print(json.dumps({"valid": True, "run_dir": str(args.path.resolve())}, ensure_ascii=False))
        return 0
    validate_workspace(args.path)
    target = args.path.resolve()
    shutil.rmtree(target)
    print(json.dumps({"cleaned": True, "run_dir": str(target)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
