"""Classify and resolve Douyin/Xiaohongshu links locally without requiring a browser."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import parse_qs, urlsplit
import urllib.request

XHS_ID = r"[0-9a-fA-F]{24}"
DOUYIN_ID = r"[0-9]{6,24}"
URL_RE = re.compile(r"https?://[^\s<>\"'，。！？）】]+", re.IGNORECASE)
XHS_HOSTS = {"xiaohongshu.com", "www.xiaohongshu.com", "m.xiaohongshu.com"}
XHS_SHORT_HOSTS = {"xhslink.com", "www.xhslink.com", "xhslink.cn", "www.xhslink.cn"}
DOUYIN_HOSTS = {"douyin.com", "www.douyin.com", "iesdouyin.com", "www.iesdouyin.com"}
DOUYIN_SHORT_HOSTS = {"v.douyin.com"}


def classify(url: str) -> dict[str, str]:
    try:
        raw_url = url.strip()
        parsed = urlsplit(raw_url)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            return {"kind": "unsupported"}
        if parsed.port not in (None, 80, 443):
            return {"kind": "unsupported"}
        host = (parsed.hostname or "").lower()
        path = parsed.path.rstrip("/")
        if host in XHS_SHORT_HOSTS:
            clean_short = f"{parsed.scheme}://{host}{path}"
            return {"kind": "short", "platform": "xiaohongshu", "short_url": clean_short,
                    "action": "resolve_redirect_via_http_or_provide_canonical_url"}
        if host in DOUYIN_SHORT_HOSTS:
            clean_short = f"{parsed.scheme}://{host}{path}"
            return {"kind": "short", "platform": "douyin", "short_url": clean_short,
                    "action": "resolve_redirect_via_http_or_provide_canonical_url"}
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
            query = parse_qs(parsed.query)
            if "modal_id" in query and query["modal_id"]:
                modal_id = query["modal_id"][0]
                if re.fullmatch(DOUYIN_ID, modal_id):
                    return {"kind": "note", "platform": "douyin", "note_id": modal_id,
                            "canonical_url": f"https://www.douyin.com/video/{modal_id}"}
            match = re.fullmatch(rf"/(?:video|note|share/video|share/note)/({DOUYIN_ID})", path)
            if match:
                note_id = match.group(1)
                prefix = "note" if "note" in path else "video"
                return {"kind": "note", "platform": "douyin", "note_id": note_id,
                        "canonical_url": f"https://www.douyin.com/{prefix}/{note_id}"}
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


def resolve_redirect_http(url: str, timeout: float = 8.0) -> dict[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            final_url = response.geturl()
            classified = classify(final_url)
            if classified.get("kind") == "note":
                classified["resolved_from"] = url
                return classified
    except Exception:
        pass
    return classify(url)


def extract(text: str) -> list[dict[str, str]]:
    return [classify(match.group(0).rstrip(").,;!？；")) for match in URL_RE.finditer(text)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", help="Share text (prefer --stdin for signed/private links)")
    parser.add_argument("--stdin", action="store_true", help="Read UTF-8 share text from standard input")
    parser.add_argument("--file", type=Path, help="Read URLs/share text from a local text or markdown file")
    parser.add_argument("--resolve", action="store_true",
                        help="Resolve short URLs via lightweight HTTP redirects locally without opening a browser")
    parser.add_argument("--check-existing", action="store_true",
                        help="Check the configured vault by platform and source ID")
    args = parser.parse_args()

    input_modes = [bool(args.text is not None), bool(args.stdin), bool(args.file is not None)]
    if sum(input_modes) != 1:
        parser.error("Choose exactly one of --text, --stdin, or --file")

    if args.stdin:
        text = sys.stdin.buffer.read().decode("utf-8-sig")
    elif args.file:
        file_path = args.file.expanduser().resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"Input file not found: {file_path}")
        text = file_path.read_text(encoding="utf-8-sig")
    else:
        text = args.text

    results = extract(text)

    if args.resolve:
        resolved_results: list[dict[str, str]] = []
        for item in results:
            if item.get("kind") == "short":
                resolved_results.append(resolve_redirect_http(item.get("short_url", "")))
            else:
                resolved_results.append(item)
        results = resolved_results

    if args.check_existing:
        from common import load_config
        from publish_note import existing_notes
        saved = existing_notes(Path(load_config()["vault_root"]).resolve())
        for result in results:
            if result["kind"] == "note":
                key = (result["platform"], result["note_id"])
                path = saved.get(key)
                result["status"] = "already_saved" if path else "not_saved"
                if path:
                    result["note"] = str(path)
    output = {"items": results, "count": len(results)}
    code = 0 if results and all(r["kind"] != "unsupported" for r in results) else 2
    if args.check_existing:
        duplicates = [r for r in results if r.get("status") == "already_saved"]
        if duplicates:
            code = 3
            output.update(status="duplicate", stop_task=True,
                          message="检测到重复链接：该内容之前已处理，重复存在，已停止本次任务。",
                          existing_notes=[r["note"] for r in duplicates])
        elif any(r["kind"] == "short" for r in results):
            code = 4
            output.update(status="needs_resolution", stop_task=True,
                          message="短链接尚未完成解析；请添加 --resolve 自动解析或提供展开后的地址，暂不处理内容。")
        else:
            code = 0 if results and all(r["kind"] == "note" for r in results) else 2
            output.update(status="ready" if code == 0 else "invalid", stop_task=code != 0)
    print(json.dumps(output, ensure_ascii=False))
    return code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
