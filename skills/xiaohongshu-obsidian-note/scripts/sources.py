"""Classify supplied links locally. Never resolve redirects or expose access tokens."""
from __future__ import annotations

import argparse
import json
import re
import sys
from urllib.parse import parse_qs, urlsplit

NOTE_ID = r"[0-9a-fA-F]{24}"
URL_RE = re.compile(r"https?://[^\s<>\"'，。！？）】]+", re.IGNORECASE)
HOSTS = {"xiaohongshu.com", "www.xiaohongshu.com", "m.xiaohongshu.com"}
SHORT_HOSTS = {"xhslink.com", "www.xhslink.com", "xhslink.cn", "www.xhslink.cn"}


def classify(url: str) -> dict[str, str]:
    try:
        parsed = urlsplit(url.strip())
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            return {"kind": "unsupported"}
        if parsed.port not in (None, 80, 443):
            return {"kind": "unsupported"}
        host = (parsed.hostname or "").lower()
        if host in SHORT_HOSTS:
            return {"kind": "short", "action": "resolve_in_authorized_browser"}
        if host not in HOSTS:
            return {"kind": "unsupported"}
        path = parsed.path.rstrip("/")
        match = re.fullmatch(rf"/(?:explore|discovery/item)/({NOTE_ID})", path)
        if not match:
            match = re.fullmatch(rf"/user/profile/{NOTE_ID}/({NOTE_ID})", path)
        if match:
            note_id = match.group(1).lower()
            return {"kind": "note", "note_id": note_id,
                    "canonical_url": f"https://www.xiaohongshu.com/explore/{note_id}"}
        if re.fullmatch(rf"/user/profile/{NOTE_ID}", path):
            query = parse_qs(parsed.query)
            kind = "collection" if query.get("tab") == ["fav"] else "profile"
            return {"kind": kind, "action": "request_a_specific_note_link_do_not_collect_profile"}
        return {"kind": "unsupported"}
    except ValueError:
        return {"kind": "unsupported"}


def canonical_note(url: str) -> dict[str, str]:
    result = classify(url)
    if result["kind"] != "note":
        raise ValueError("Expected a resolved Xiaohongshu note URL, not a profile or short link")
    return result


def extract(text: str) -> list[dict[str, str]]:
    return [classify(match.group(0).rstrip(").,;!？；")) for match in URL_RE.finditer(text)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", help="Share text (prefer --stdin for signed/private links)")
    parser.add_argument("--stdin", action="store_true", help="Read UTF-8 share text from standard input")
    parser.add_argument("--check-existing", action="store_true", help="Also check the configured note directory by canonical note ID")
    args = parser.parse_args()
    if args.stdin == (args.text is not None):
        parser.error("Choose exactly one of --text or --stdin")
    text = sys.stdin.buffer.read().decode("utf-8-sig") if args.stdin else args.text
    results = extract(text)
    if args.check_existing:
        from pathlib import Path
        from common import load_config
        from publish_note import existing_notes
        saved = existing_notes(Path(load_config()["note_dir"]))
        for result in results:
            if result["kind"] == "note":
                path = saved.get(result["note_id"])
                result["status"] = "already_saved" if path else "not_saved"
                if path:
                    result["note"] = str(path)
    print(json.dumps({"items": results, "count": len(results)}, ensure_ascii=False))
    return 0 if results and all(r["kind"] != "unsupported" for r in results) else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
