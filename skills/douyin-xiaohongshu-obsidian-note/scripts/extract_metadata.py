from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any
import urllib.request

from common import is_within, local_timestamp, write_json
from manage_cookies import cookie_file_path, cookie_guidance_message
from run_workspace import validate_workspace


SAFE_METADATA_KEYS = (
    "id",
    "title",
    "description",
    "uploader",
    "uploader_id",
    "channel",
    "channel_id",
    "timestamp",
    "release_timestamp",
    "upload_date",
    "release_date",
    "duration",
    "duration_string",
    "view_count",
    "like_count",
    "comment_count",
    "repost_count",
    "tags",
    "categories",
    "webpage_url",
    "extractor",
    "extractor_key",
    "cookie_status",
)


def resolve_yt_dlp(explicit: str | None) -> str:
    if explicit:
        return explicit
    executable = shutil.which("yt-dlp")
    if executable:
        return executable
    raise FileNotFoundError("yt-dlp was not found on PATH; install it or pass --yt-dlp <executable>")


def build_yt_dlp_command(
    executable: str,
    source_url: str,
    cookies_from_browser: str | None = None,
    cookies_file: Path | None = None,
) -> list[str]:
    command = [
        executable,
        "--dump-single-json",
        "--skip-download",
        "--no-playlist",
        "--no-warnings",
    ]
    if cookies_from_browser:
        command.extend(["--cookies-from-browser", cookies_from_browser])
    elif cookies_file and cookies_file.is_file() and cookies_file.stat().st_size > 0:
        command.extend(["--cookies", str(cookies_file)])
    command.extend(["--", source_url])
    return command


def child_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


def safe_metadata(raw: dict[str, Any], source_url: str) -> dict[str, Any]:
    metadata = {key: raw[key] for key in SAFE_METADATA_KEYS if key in raw}
    metadata["source_url"] = source_url
    metadata["extracted_at"] = local_timestamp()
    return metadata


def find_item_detail(obj: Any) -> dict[str, Any] | None:
    if isinstance(obj, dict):
        if "desc" in obj and ("aweme_id" in obj or "item_id" in obj or "author" in obj):
            return obj
        for v in obj.values():
            found = find_item_detail(v)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = find_item_detail(item)
            if found:
                return found
    return None


def extract_metadata_via_html_ssr(source_url: str) -> dict[str, Any]:
    match = re.search(r"(?:video|note)/([0-9]{6,24})", source_url)
    if not match:
        raise ValueError(f"Cannot extract Douyin note/video ID from URL: {source_url}")
    note_id = match.group(1)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    req = urllib.request.Request(f"https://www.iesdouyin.com/share/video/{note_id}/", headers=headers)
    with urllib.request.urlopen(req, timeout=15) as res:
        html = res.read().decode("utf-8", errors="ignore")

    raw_data = None
    for pattern in (
        r"window\._ROUTER_DATA\s*=\s*(.*?)(?:;\s*</script>|</script>)",
        r"window\._SSR_DATA\s*=\s*(.*?)(?:;\s*</script>|</script>)",
    ):
        m = re.search(pattern, html, re.S)
        if m:
            try:
                candidate_str = m.group(1).strip().rstrip(";")
                raw_data = json.loads(candidate_str)
                break
            except Exception:
                continue

    item = find_item_detail(raw_data) if raw_data else None
    if item:
        title = (item.get("desc") or "").strip()
        author = item.get("author") if isinstance(item.get("author"), dict) else {}
        uploader = author.get("nickname") or ""
        uploader_id = str(author.get("sec_uid") or author.get("uid") or "")
        dur_raw = item.get("duration") or (
            item.get("video", {}).get("duration") if isinstance(item.get("video"), dict) else 0
        ) or 0
        duration = round(dur_raw / 1000.0, 3) if dur_raw > 1000 else float(dur_raw)
        created = item.get("create_time") or 0
        stats = item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
        upload_date = datetime.fromtimestamp(created).strftime("%Y%m%d") if created else ""
        raw = {
            "id": str(item.get("aweme_id") or item.get("item_id") or note_id),
            "title": title or f"抖音作品_{note_id}",
            "description": title,
            "uploader": uploader,
            "uploader_id": uploader_id,
            "channel": uploader,
            "channel_id": uploader_id,
            "duration": duration,
            "timestamp": created,
            "upload_date": upload_date,
            "like_count": stats.get("digg_count") or item.get("digg_count") or 0,
            "comment_count": stats.get("comment_count") or 0,
            "webpage_url": f"https://www.douyin.com/video/{note_id}",
            "extractor": "douyin:html_ssr_fallback",
            "extractor_key": "Douyin",
        }
        return safe_metadata(raw, source_url)

    title_match = re.search(r"<title>(.*?)(?: - 抖音|\s*</title>)", html, re.S)
    if title_match and title_match.group(1).strip():
        title = title_match.group(1).strip()
        raw = {
            "id": note_id,
            "title": title,
            "description": title,
            "uploader": "",
            "duration": 0,
            "webpage_url": f"https://www.douyin.com/video/{note_id}",
            "extractor": "douyin:html_meta_fallback",
            "extractor_key": "Douyin",
        }
        return safe_metadata(raw, source_url)

    raise ValueError(f"Could not extract Douyin metadata from mobile SSR HTML for ID {note_id}")


def extract_metadata(
    source_url: str,
    output_path: Path,
    yt_dlp: str | None,
    cookies_from_browser: str | None = None,
    cookies_file: Path | None = None,
) -> dict[str, Any]:
    metadata = None
    yt_err = None
    cookie_issue = False

    resolved_cookies_file = cookies_file
    if resolved_cookies_file is None and not cookies_from_browser:
        default_file = cookie_file_path()
        if default_file.is_file() and default_file.stat().st_size > 0:
            resolved_cookies_file = default_file

    try:
        executable = resolve_yt_dlp(yt_dlp)
        command = build_yt_dlp_command(executable, source_url, cookies_from_browser, resolved_cookies_file)
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            shell=False,
            env=child_environment(),
            text=True,
            encoding="utf-8",
            errors="strict",
        )
        if completed.returncode == 0:
            raw = json.loads(completed.stdout)
            if isinstance(raw, dict):
                metadata = safe_metadata(raw, source_url)
            else:
                yt_err = "yt-dlp returned non-dict JSON"
        else:
            yt_err = completed.stderr.strip() or f"yt-dlp exited with code {completed.returncode}"
            err_lower = yt_err.lower()
            if any(cue in err_lower for cue in ("fresh cookies needed", "http error 403", "http error 401", "login", "cookie")):
                cookie_issue = True
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        yt_err = str(exc)

    if metadata is None:
        try:
            metadata = extract_metadata_via_html_ssr(source_url)
            if cookie_issue:
                metadata["cookie_status"] = "expired"
                print(
                    f"[提示] 本地抖音 Cookie 可能已失效，本次已自动通过移动端 SSR 回退成功。\n{cookie_guidance_message()}",
                    file=sys.stderr,
                )
        except Exception as ssr_exc:
            guidance = f"\n\n{cookie_guidance_message()}" if (cookie_issue or resolved_cookies_file) else ""
            detail = f"yt-dlp extraction failed ({yt_err}); mobile SSR fallback failed ({ssr_exc}){guidance}"
            raise RuntimeError(detail) from ssr_exc

    write_json(output_path.expanduser().resolve(), metadata)
    return metadata


def background_command(
    source_url: str,
    output_path: Path,
    status_path: Path,
    yt_dlp: str | None,
    run_dir: Path,
    cookies_from_browser: str | None = None,
    cookies_file: Path | None = None,
) -> list[str]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--url",
        source_url,
        "--output",
        str(output_path),
        "--status-file",
        str(status_path),
        "--run-dir",
        str(run_dir),
        "--worker",
    ]
    if yt_dlp:
        command.extend(["--yt-dlp", yt_dlp])
    if cookies_from_browser:
        command.extend(["--cookies-from-browser", cookies_from_browser])
    if cookies_file:
        command.extend(["--cookies-file", str(cookies_file)])
    return command


def start_background(
    source_url: str,
    output_path: Path,
    status_path: Path,
    log_path: Path,
    yt_dlp: str | None,
    run_dir: Path,
    cookies_from_browser: str | None = None,
    cookies_file: Path | None = None,
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = background_command(source_url, output_path, status_path, yt_dlp, run_dir, cookies_from_browser, cookies_file)
    popen_options: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stderr": subprocess.STDOUT,
        "close_fds": True,
        "shell": False,
        "env": child_environment(),
    }
    if os.name == "nt":
        popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        popen_options["start_new_session"] = True
    with log_path.open("ab") as log_file:
        process = subprocess.Popen(command, stdout=log_file, **popen_options)
    return process.pid


def status_payload(state: str, output_path: Path, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "state": state,
        "output": str(output_path),
        "updated_at": local_timestamp(),
    }
    payload.update(extra)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract safe Douyin yt-dlp metadata without nested PowerShell command strings"
    )
    parser.add_argument("--url", required=True, help="Source video or share URL")
    parser.add_argument("--output", type=Path, required=True, help="UTF-8 JSON output path")
    parser.add_argument("--run-dir", type=Path, required=True, help="Marked workspace for all output/status/log files")
    parser.add_argument("--yt-dlp", help="Optional yt-dlp executable path")
    parser.add_argument("--cookies-from-browser",
                        help="Optional browser to extract cookies from (e.g. edge, chrome, firefox)")
    parser.add_argument("--cookies-file", type=Path, help="Optional local Netscape cookie file path")
    parser.add_argument("--background", action="store_true", help="Run extraction in a detached child process")
    parser.add_argument("--status-file", type=Path, help="Background job status JSON path")
    parser.add_argument("--log-file", type=Path, help="Background job log path")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    run_dir = args.run_dir.expanduser().resolve()
    validate_workspace(run_dir)
    output_path = args.output.expanduser().resolve()
    status_path = (
        args.status_file.expanduser().resolve()
        if args.status_file
        else output_path.with_suffix(output_path.suffix + ".status.json")
    )

    if args.background and args.worker:
        parser.error("--background and --worker cannot be used together")
    checked_paths = [output_path, status_path]

    if args.background:
        log_path = (
            args.log_file.expanduser().resolve()
            if args.log_file
            else output_path.with_suffix(output_path.suffix + ".log")
        )
        checked_paths.append(log_path)
        if any(not is_within(path, run_dir) for path in checked_paths):
            raise SystemExit("Metadata output, status, and log must stay inside the marked run workspace")
        write_json(status_path, status_payload("starting", output_path))
        try:
            pid = start_background(
                args.url,
                output_path,
                status_path,
                log_path,
                args.yt_dlp,
                run_dir,
                args.cookies_from_browser,
                args.cookies_file,
            )
        except OSError as exc:
            write_json(status_path, status_payload("failed", output_path, error=str(exc)))
            print(str(exc), file=sys.stderr)
            return 2
        print(
            json.dumps(
                {
                    "started": True,
                    "pid": pid,
                    "output": str(output_path),
                    "status_file": str(status_path),
                    "log_file": str(log_path),
                },
                ensure_ascii=False,
            )
        )
        return 0

    if any(not is_within(path, run_dir) for path in checked_paths):
        raise SystemExit("Metadata output and status must stay inside the marked run workspace")

    if args.worker:
        write_json(status_path, status_payload("running", output_path, pid=os.getpid()))
    try:
        metadata = extract_metadata(
            args.url,
            output_path,
            args.yt_dlp,
            args.cookies_from_browser,
            args.cookies_file,
        )
    except (FileNotFoundError, OSError, RuntimeError, UnicodeError, ValueError) as exc:
        if args.worker:
            write_json(status_path, status_payload("failed", output_path, error=str(exc)))
        print(str(exc), file=sys.stderr)
        return 2
    if args.worker:
        write_json(status_path, status_payload("succeeded", output_path, pid=os.getpid()))
    print(
        json.dumps(
            {
                "extracted": True,
                "output": str(output_path),
                "id": metadata.get("id", ""),
                "title": metadata.get("title", ""),
                "extractor": metadata.get("extractor", ""),
                "cookie_status": metadata.get("cookie_status", "valid"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
