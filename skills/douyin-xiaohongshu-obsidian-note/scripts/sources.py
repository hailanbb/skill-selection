"""Classify Douyin/Xiaohongshu links locally without resolving redirects."""
from __future__ import annotations

import argparse
import json
import re
import sys
from urllib.parse import parse_qs, urlsplit

XHS_ID = r"[0-9a-fA-F]{24}"
DOUYIN_ID = r"[0-9]{6,24}"
URL_RE = re.compile(r"https?://[^\s<>\"'，。！？）】]+", re.IGNORECASE)
XHS_HOSTS = {"xiaohongshu.com", "www.xiaohongshu.com", "m.xiaohongshu.com"}
XHS_SHORT_HOSTS = {"xhslink.com", "www.xhslink.com", "xhslink.cn", "www.xhslink.cn"}
DOUYIN_HOSTS = {"douyin.com", "www.douyin.com", "iesdouyin.com", "www.iesdouyin.com"}
DOUYIN_SHORT_HOSTS = {"v.douyin.com"}


def classify(url: str) -> dict[str, str]:
    try:
        parsed = urlsplit(url.strip())
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            return {"kind": "unsupported"}
        if parsed.port not in (None, 80, 443):
            return {"kind": "unsupported"}
        host = (parsed.hostname or "").lower()
        if host in XHS_SHORT_HOSTS:
            return {"kind": "short", "platform": "xiaohongshu", "action": "resolve_in_authorized_browser"}
        if host in DOUYIN_SHORT_HOSTS:
            return {"kind": "short", "platform": "douyin", "action": "resolve_in_authorized_browser"}
        path = parsed.path.rstrip("/")
        if host in XHS_HOSTS:
            match = re.fullmatch(rf"/(?:explore|discovery/item)/({XHS_ID})", path)
            if not match:
                match = re.fullmatch(rf"/user/profile/{XHS_ID}/({XHS_ID})", path)
            if match:
                note_id = match.group(1).lower()
                return {"kind": "note", "platform": "xiaohongshu", "note_id": note_id,
                        "canonical_url": f"https://www.xiaohongshu.com/explore/{note_id}"}
            if re.fullmatch(rf"/user/profile/{XHS_ID}", path):
                query = parse_qs(parsed.query)
                kind = "collection" if query.get("tab") == ["fav"] else "profile"
                return {"kind": kind, "platform": "xiaohongshu",
                        "action": "request_a_specific_note_link_do_not_collect_profile"}
            return {"kind": "unsupported"}
        if host in DOUYIN_HOSTS:
            match = re.fullmatch(rf"/(?:video|share/video)/({DOUYIN_ID})", path)
            if match:
                note_id = match.group(1)
                return {"kind": "note", "platform": "douyin", "note_id": note_id,
                        "canonical_url": f"https://www.douyin.com/video/{note_id}"}
            if path.startswith("/user/"):
                return {"kind": "profile", "platform": "douyin",
                        "action": "request_a_specific_video_link_do_not_collect_profile"}
        return {"kind": "unsupported"}
    except ValueError:
        return {"kind": "unsupported"}


def canonical_source(url: str) -> dict[str, str]:
    result = classify(url)
    if result["kind"] != "note":
        raise ValueError("Expected a resolved Douyin video or Xiaohongshu note URL")
    return result


def extract(text: str) -> list[dict[str, str]]:
    return [classify(match.group(0).rstrip(").,;!？；")) for match in URL_RE.finditer(text)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", help="Share text (prefer --stdin for signed/private links)")
    parser.add_argument("--stdin", action="store_true", help="Read UTF-8 share text from standard input")
    parser.add_argument("--check-existing", action="store_true", help="Check the configured note directory by platform and source ID")
    args = parser.parse_args()
    if args.stdin == (args.text is not None):
        parser.error("Choose exactly one of --text or --stdin")
    text = sys.stdin.buffer.read().decode("utf-8-sig") if args.stdin else args.text
    results = extract(text)
    if args.check_existing:
        from pathlib import Path
        from common import load_config
        from publish_note import existing_notes
        saved = existing_notes(Path(load_config()["note_dir"]).resolve())
        for result in results:
            if result["kind"] == "note":
                key = (result["platform"], result["note_id"])
                path = saved.get(key)
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
