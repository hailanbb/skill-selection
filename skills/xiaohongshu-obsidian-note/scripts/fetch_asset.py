"""Download one already-observed public XHS CDN asset; no cookies, scraping, or URL guessing."""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import socket
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.error import URLError

from common import is_within, read_json
from run_workspace import validate_workspace


def validate_url(url: str) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Only HTTPS CDN resources without embedded credentials are allowed")
    if not host.endswith(".xhscdn.com"):
        raise ValueError("Only observed *.xhscdn.com assets are supported; use authorized browser download for other hosts")
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("CDN hostname did not resolve exclusively to public addresses")
    return url


class SafeRedirects(HTTPRedirectHandler):
    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(request_path: Path, run_dir: Path) -> dict:
    validate_workspace(run_dir)
    run_dir = run_dir.resolve()
    if not is_within(request_path, run_dir):
        raise ValueError("Asset request must be inside the temporary workspace")
    settings = read_json(request_path)
    kind = settings.get("kind")
    filename = settings.get("filename", "")
    if kind not in {"image", "video"} or not isinstance(filename, str) or not filename:
        raise ValueError("Request requires kind image/video and a local filename")
    if Path(filename).name != filename or any(c in filename for c in '/\\:*?"<>|') or filename in {".", ".."}:
        raise ValueError("Use a simple filename without directories or Windows special characters")
    allowed_suffixes = {".jpg", ".jpeg", ".png", ".webp"} if kind == "image" else {".mp4", ".webm", ".mov"}
    if Path(filename).suffix.lower() not in allowed_suffixes:
        raise ValueError("Filename extension must match the expected media category")
    target = run_dir / filename
    if target.exists() or target.is_symlink():
        raise FileExistsError("Asset target already exists")
    url = validate_url(settings.get("url", ""))
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.xiaohongshu.com/"})
    limit = (50 if kind == "image" else 512) * 1024 * 1024
    fd, temp_name = tempfile.mkstemp(prefix=".asset-", suffix=".part", dir=run_dir)
    temp_path = Path(temp_name)
    size = 0
    try:
        with os.fdopen(fd, "wb") as output, build_opener(SafeRedirects()).open(request, timeout=30) as response:
            content_type = response.headers.get_content_type()
            if not content_type.startswith(kind + "/") and content_type != "application/octet-stream":
                raise ValueError("Resource is not the requested media type (possibly an error/login page)")
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise ValueError("Asset exceeds the per-file download limit")
                output.write(chunk)
        if not size:
            raise ValueError("Empty asset response")
        os.link(temp_path, target)
        return {"downloaded": True, "path": str(target), "bytes": size,
                "next": "visually inspect image / probe video; a downloaded file is not verified evidence"}
    finally:
        temp_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    result = fetch(args.request, args.run_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, TypeError, URLError):
        # Exception messages from networking libraries can contain signed URLs.
        print("Asset download stopped. Check the observed CDN URL, media type, access, and output path; use browser save on 403/login requirements. No cookies were exported.", file=sys.stderr)
        raise SystemExit(2)
