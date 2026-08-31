from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import load_config, validation_issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a published douyin-obsidian-note Markdown file")
    parser.add_argument("note", type=Path)
    args = parser.parse_args()
    note = args.note.expanduser().resolve()
    raw = note.read_bytes()
    issues: list[str] = []
    if raw.startswith(b"\xef\xbb\xbf"):
        issues.append("file has a UTF-8 BOM")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        print(json.dumps({"ok": False, "note": str(note), "issues": [f"not valid UTF-8: {exc}"]}, ensure_ascii=False, indent=2))
        return 1
    config = load_config(required=True)
    assert config is not None
    issues.extend(validation_issues(text, note, Path(config["vault_root"])))
    payload = {"ok": not issues, "note": str(note), "issues": issues}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
