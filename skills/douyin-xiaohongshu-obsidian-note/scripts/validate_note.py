from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from common import load_config, split_frontmatter, validation_issues
from sources import classify


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate saved UTF-8 notes and local image links")
    parser.add_argument("--note", type=Path, required=True)
    args = parser.parse_args()
    config = load_config()
    text = args.note.read_text(encoding="utf-8-sig")
    issues = validation_issues(text, args.note, Path(config["vault_root"]))
    attrs, _ = split_frontmatter(text)
    source = classify(attrs.get("url", ""))
    if source.get("canonical_url") != attrs.get("url") or source["kind"] != "note":
        issues.append("source URL is not a canonical Douyin video or Xiaohongshu note URL")
    expected_origin = {"douyin": "抖音", "xiaohongshu": "小红书"}.get(source.get("platform"))
    if expected_origin and attrs.get("origin") != expected_origin:
        issues.append("origin does not match the canonical source platform")
    print(json.dumps({"valid": not issues, "issues": issues}, ensure_ascii=False))
    return 2 if issues else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
