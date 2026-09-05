from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common import CONFIG_VERSION, config_path, discover_vault_root, is_within, load_config, local_timestamp, write_json


def status() -> int:
    path = config_path()
    try:
        config = load_config(required=False)
        payload = {"configured": config is not None, "config_path": str(path), "config": config}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"configured": False, "config_path": str(path), "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure Obsidian output paths for xiaohongshu-obsidian-note")
    parser.add_argument("--status", action="store_true", help="Print configuration status as JSON")
    parser.add_argument("--note-dir", help="Absolute directory for Markdown notes")
    parser.add_argument("--image-dir", help="Absolute directory for note images")
    parser.add_argument("--vault-root", help="Optional explicit Obsidian vault root")
    parser.add_argument("--create-dirs", action="store_true", help="Create note and image directories if absent")
    args = parser.parse_args()
    if args.status:
        return status()
    if not args.note_dir or not args.image_dir:
        raise SystemExit("--note-dir and --image-dir are required when saving configuration")

    note_dir = Path(args.note_dir).expanduser()
    image_dir = Path(args.image_dir).expanduser()
    if not note_dir.is_absolute() or not image_dir.is_absolute():
        raise SystemExit("Both paths must be absolute")
    note_dir = note_dir.resolve()
    image_dir = image_dir.resolve()
    explicit_root = Path(args.vault_root).expanduser().resolve() if args.vault_root else None
    vault_root = explicit_root or discover_vault_root(note_dir)
    if vault_root is None or not (vault_root / ".obsidian").is_dir():
        raise SystemExit("Could not find an Obsidian vault root containing .obsidian")
    image_vault = discover_vault_root(image_dir)
    if image_vault is not None and image_vault != vault_root:
        raise SystemExit("The image directory belongs to a different Obsidian vault")
    if not is_within(note_dir, vault_root) or not is_within(image_dir, vault_root):
        raise SystemExit("Both output directories must be inside the configured vault")
    for output in (note_dir, image_dir):
        if any(char in output.relative_to(vault_root).as_posix() for char in "[]|#\n\r"):
            raise SystemExit("Output paths cannot contain Obsidian embed delimiters: []|# or newlines")
    if args.create_dirs:
        note_dir.mkdir(parents=True, exist_ok=True)
        image_dir.mkdir(parents=True, exist_ok=True)
    if not note_dir.is_dir() or not image_dir.is_dir():
        raise SystemExit("Both directories must exist, or pass --create-dirs")

    config = {
        "version": CONFIG_VERSION,
        "vault_root": str(vault_root),
        "note_dir": str(note_dir),
        "image_dir": str(image_dir),
        "configured_at": local_timestamp(),
    }
    write_json(config_path(), config)
    print(json.dumps({"configured": True, "config_path": str(config_path()), "config": config}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
