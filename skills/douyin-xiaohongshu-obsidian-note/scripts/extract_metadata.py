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
from fetch_asset import CDN_SUFFIXES, download_single_asset
from manage_cookies import cookie_file_path, cookie_guidance_message, load_cookie_header
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
    "publish_date",
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
    "media_type",
    "image_count",
    "assets_manifest",
    "downloaded_assets",
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


def _pick_allowed_cdn_url(candidates: list[Any], platform: str) -> str | None:
    suffixes = CDN_SUFFIXES.get(platform, ())
    for item in candidates:
        if not isinstance(item, str):
            continue
        url = item.strip()
        if url.startswith("http://"):
            url = "https://" + url[len("http://"):]
        if not url.startswith("https://"):
            continue
        host = ( urllib.request.urlsplit(url).hostname or "" ).lower()
        if any(host.endswith(suf) for suf in suffixes):
            return url
    return None


def _extract_douyin_observed_assets(item: dict[str, Any]) -> list[dict[str, str]]:
    assets: list[dict[str, str]] = []
    images = item.get("images")
    if isinstance(images, list) and images:
        for idx, img in enumerate(images, start=1):
            if not isinstance(img, dict):
                continue
            url_list = img.get("url_list") or img.get("download_url_list") or []
            chosen = _pick_allowed_cdn_url(url_list if isinstance(url_list, list) else [], "douyin")
            if chosen:
                assets.append({
                    "url": chosen,
                    "platform": "douyin",
                    "kind": "image",
                    "filename": f"page-{idx:02d}.jpg",
                })
        return assets

    video = item.get("video")
    if isinstance(video, dict):
        play_addr = video.get("play_addr") or video.get("download_addr") or {}
        url_list = play_addr.get("url_list", []) if isinstance(play_addr, dict) else []
        cleaned_urls = [u.replace("/playwm/", "/play/") for u in url_list if isinstance(u, str)]
        chosen = _pick_allowed_cdn_url(cleaned_urls, "douyin")
        if chosen:
            assets.append({
                "url": chosen,
                "platform": "douyin",
                "kind": "video",
                "filename": "source.mp4",
            })
    return assets


def extract_metadata_via_html_ssr(source_url: str, cookies_file: Path | None = None) -> dict[str, Any]:
    match = re.search(r"(?:video|note)/([0-9]{6,24})", source_url)
    if not match:
        q_match = re.search(r"modal_id=([0-9]{6,24})", source_url)
        if not q_match:
            raise ValueError(f"Cannot extract Douyin note/video ID from URL: {source_url}")
        note_id = q_match.group(1)
    else:
        note_id = match.group(1)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    c_path = cookies_file if cookies_file is not None else cookie_file_path()
    cookie_header = load_cookie_header("douyin", explicit_file=c_path)
    if cookie_header:
        headers["Cookie"] = cookie_header
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
        publish_date = datetime.fromtimestamp(created).strftime("%Y-%m-%d") if created else ""
        images = item.get("images")
        is_gallery = isinstance(images, list) and len(images) > 0
        observed_assets = _extract_douyin_observed_assets(item)
        prefix = "note" if is_gallery else "video"
        raw: dict[str, Any] = {
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
            "publish_date": publish_date,
            "like_count": stats.get("digg_count") or item.get("digg_count") or 0,
            "comment_count": stats.get("comment_count") or 0,
            "webpage_url": f"https://www.douyin.com/{prefix}/{note_id}",
            "extractor": "douyin:html_ssr_fallback",
            "extractor_key": "Douyin",
            "media_type": "gallery" if is_gallery else "video",
        }
        if is_gallery:
            raw["image_count"] = len(images)
        result = safe_metadata(raw, source_url)
        if observed_assets:
            result["_observed_assets"] = observed_assets
        return result

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


def _find_xhs_note_detail(state: dict[str, Any], note_id: str) -> dict[str, Any] | None:
    note_section = state.get("note")
    if isinstance(note_section, dict):
        detail_map = note_section.get("noteDetailMap")
        if isinstance(detail_map, dict):
            for key, entry in detail_map.items():
                if isinstance(entry, dict) and isinstance(entry.get("note"), dict):
                    if key.lower() == note_id.lower() or entry["note"].get("noteId", "").lower() == note_id.lower():
                        return entry["note"]
            for entry in detail_map.values():
                if isinstance(entry, dict) and isinstance(entry.get("note"), dict):
                    return entry["note"]
        if isinstance(note_section.get("noteData"), dict):
            return note_section["noteData"]
    note_data = state.get("noteData")
    if isinstance(note_data, dict):
        if isinstance(note_data.get("data"), dict) and isinstance(note_data["data"].get("noteData"), dict):
            return note_data["data"]["noteData"]
        return note_data
    return None


def extract_xhs_metadata_via_html_ssr(source_url: str, cookies_file: Path | None = None) -> dict[str, Any]:
    match = re.search(r"(?:explore|discovery/item|user/profile/[0-9a-fA-F]{24})/([0-9a-fA-F]{24})", source_url)
    if not match:
        raise ValueError(f"Cannot extract Xiaohongshu note ID from URL: {source_url}")
    note_id = match.group(1).lower()
    canonical_url = f"https://www.xiaohongshu.com/explore/{note_id}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.xiaohongshu.com/",
    }
    c_path = cookies_file if cookies_file is not None else cookie_file_path("xiaohongshu")
    cookie_header = load_cookie_header("xiaohongshu", explicit_file=c_path)
    if cookie_header:
        headers["Cookie"] = cookie_header

    req = urllib.request.Request(source_url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as res:
        html = res.read().decode("utf-8", errors="ignore")

    state_match = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})(?:;\s*</script>|</script>)", html, re.S)
    note_obj = None
    if state_match:
        raw_state_str = re.sub(r"\bundefined\b", "null", state_match.group(1).strip().rstrip(";"))
        try:
            state_data = json.loads(raw_state_str)
            if isinstance(state_data, dict):
                note_obj = _find_xhs_note_detail(state_data, note_id)
        except Exception:
            note_obj = None

    if note_obj:
        title = (note_obj.get("title") or "").strip()
        desc = (note_obj.get("desc") or "").strip()
        user = note_obj.get("user") if isinstance(note_obj.get("user"), dict) else {}
        uploader = (user.get("nickname") or "").strip()
        uploader_id = str(user.get("userId") or "")
        time_ms = note_obj.get("time") or 0
        created_ts = int(time_ms / 1000) if isinstance(time_ms, (int, float)) and time_ms > 10_000_000_000 else int(time_ms or 0)
        upload_date = datetime.fromtimestamp(created_ts).strftime("%Y%m%d") if created_ts else ""
        publish_date = datetime.fromtimestamp(created_ts).strftime("%Y-%m-%d") if created_ts else ""
        note_type = note_obj.get("type") or "normal"
        image_list = note_obj.get("imageList") if isinstance(note_obj.get("imageList"), list) else []
        observed_assets: list[dict[str, str]] = []

        for idx, img in enumerate(image_list, start=1):
            if not isinstance(img, dict):
                continue
            candidates = [img.get("urlDefault"), img.get("urlPre"), img.get("url")]
            info_list = img.get("infoList")
            if isinstance(info_list, list):
                for info in reversed(info_list):
                    if isinstance(info, dict) and info.get("url"):
                        candidates.append(info["url"])
            chosen = _pick_allowed_cdn_url(candidates, "xiaohongshu")
            if chosen:
                observed_assets.append({
                    "url": chosen,
                    "platform": "xiaohongshu",
                    "kind": "image",
                    "filename": f"page-{idx:02d}.jpg",
                })

        video_obj = note_obj.get("video") if isinstance(note_obj.get("video"), dict) else {}
        media_stream = (
            video_obj.get("media", {}).get("stream", {})
            if isinstance(video_obj.get("media"), dict)
            else {}
        )
        video_candidates: list[str] = []
        if isinstance(media_stream, dict):
            for codec in ("h264", "h265", "av1"):
                streams = media_stream.get(codec)
                if isinstance(streams, list):
                    for s in streams:
                        if isinstance(s, dict):
                            if s.get("masterUrl"):
                                video_candidates.append(s["masterUrl"])
                            if isinstance(s.get("backupUrls"), list):
                                video_candidates.extend(s["backupUrls"])
        chosen_video = _pick_allowed_cdn_url(video_candidates, "xiaohongshu")
        if chosen_video:
            observed_assets.append({
                "url": chosen_video,
                "platform": "xiaohongshu",
                "kind": "video",
                "filename": "source.mp4",
            })

        dur_raw = (
            video_obj.get("capa", {}).get("duration")
            if isinstance(video_obj.get("capa"), dict)
            else 0
        ) or 0
        media_type = "video" if note_type == "video" else "gallery"
        raw = {
            "id": str(note_obj.get("noteId") or note_id).lower(),
            "title": title or (desc.splitlines()[0][:48] if desc else f"小红书笔记_{note_id}"),
            "description": desc,
            "uploader": uploader,
            "uploader_id": uploader_id,
            "channel": uploader,
            "channel_id": uploader_id,
            "duration": float(dur_raw) if dur_raw else 0.0,
            "timestamp": created_ts,
            "upload_date": upload_date,
            "publish_date": publish_date,
            "webpage_url": canonical_url,
            "extractor": "xiaohongshu:html_ssr",
            "extractor_key": "Xiaohongshu",
            "media_type": media_type,
            "image_count": len(image_list),
        }
        result = safe_metadata(raw, canonical_url)
        if observed_assets:
            result["_observed_assets"] = observed_assets
        return result

    # Fallback to OpenGraph meta tags if present
    og_title = re.search(r'<meta\s+name="og:title"\s+content="([^"]+)"', html) or re.search(
        r'<meta\s+property="og:title"\s+content="([^"]+)"', html
    )
    if og_title and og_title.group(1).strip():
        clean_title = re.sub(r"\s*-\s*小红书\s*$", "", og_title.group(1).strip())
        og_desc = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html)
        og_imgs = re.findall(r'<meta\s+(?:name|property)="og:image"\s+content="([^"]+)"', html)
        observed_assets = []
        for idx, img_url in enumerate(og_imgs, start=1):
            chosen = _pick_allowed_cdn_url([img_url], "xiaohongshu")
            if chosen:
                observed_assets.append({
                    "url": chosen,
                    "platform": "xiaohongshu",
                    "kind": "image",
                    "filename": f"page-{idx:02d}.jpg",
                })
        raw = {
            "id": note_id,
            "title": clean_title,
            "description": og_desc.group(1).strip() if og_desc else clean_title,
            "uploader": "",
            "webpage_url": canonical_url,
            "extractor": "xiaohongshu:og_meta_fallback",
            "extractor_key": "Xiaohongshu",
            "media_type": "gallery",
            "image_count": len(observed_assets),
        }
        result = safe_metadata(raw, canonical_url)
        if observed_assets:
            result["_observed_assets"] = observed_assets
        return result

    raise ValueError(f"Could not extract Xiaohongshu metadata from SSR HTML for ID {note_id}")


def _is_xiaohongshu_url(url: str) -> bool:
    host = (urllib.request.urlsplit(url.strip()).hostname or "").lower()
    return host.endswith("xiaohongshu.com") or host.endswith("xhslink.com") or host.endswith("xhslink.cn")


def _finalize_observed_assets(
    metadata: dict[str, Any],
    output_path: Path,
    run_dir: Path | None,
    download_media: bool,
) -> None:
    observed_assets = metadata.pop("_observed_assets", None)
    if not observed_assets or not isinstance(observed_assets, list):
        return
    platform = observed_assets[0].get("platform", "douyin")
    assets_manifest_path = output_path.with_suffix(".assets.json")
    write_json(assets_manifest_path, {"platform": platform, "assets": observed_assets})
    metadata["assets_manifest"] = str(assets_manifest_path)

    if download_media and run_dir is not None:
        downloaded_files: list[str] = []
        for asset in observed_assets:
            res = download_single_asset(asset, run_dir, default_platform=platform)
            downloaded_files.append(res["filename"])
        metadata["downloaded_assets"] = downloaded_files


def extract_metadata(
    source_url: str,
    output_path: Path,
    yt_dlp: str | None = None,
    cookies_from_browser: str | None = None,
    cookies_file: Path | None = None,
    *,
    run_dir: Path | None = None,
    download_media: bool = False,
) -> dict[str, Any]:
    resolved_output = output_path.expanduser().resolve()
    if _is_xiaohongshu_url(source_url):
        try:
            metadata = extract_xhs_metadata_via_html_ssr(source_url, cookies_file=cookies_file)
        except Exception as xhs_exc:
            guidance = f"\n\n{cookie_guidance_message('xiaohongshu')}"
            raise RuntimeError(f"Xiaohongshu SSR metadata extraction failed ({xhs_exc}){guidance}") from xhs_exc
        _finalize_observed_assets(metadata, resolved_output, run_dir, download_media)
        write_json(resolved_output, metadata)
        return metadata

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
            metadata = extract_metadata_via_html_ssr(source_url, cookies_file=resolved_cookies_file)
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
    elif download_media and "_observed_assets" not in metadata:
        try:
            ssr_meta = extract_metadata_via_html_ssr(source_url, cookies_file=resolved_cookies_file)
            if "_observed_assets" in ssr_meta:
                metadata["_observed_assets"] = ssr_meta["_observed_assets"]
            for k in ("media_type", "image_count", "publish_date"):
                if k in ssr_meta and k not in metadata:
                    metadata[k] = ssr_meta[k]
        except Exception:
            pass

    _finalize_observed_assets(metadata, resolved_output, run_dir, download_media)
    write_json(resolved_output, metadata)
    return metadata


def background_command(
    source_url: str,
    output_path: Path,
    status_path: Path,
    yt_dlp: str | None,
    run_dir: Path,
    cookies_from_browser: str | None = None,
    cookies_file: Path | None = None,
    download_media: bool = False,
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
    if download_media:
        command.append("--download-media")
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
    download_media: bool = False,
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = background_command(
        source_url, output_path, status_path, yt_dlp, run_dir, cookies_from_browser, cookies_file, download_media
    )
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
        description="Extract safe Douyin/Xiaohongshu metadata and optional CDN media assets in headless CLI mode"
    )
    parser.add_argument("--url", required=True, help="Source video, note, or share URL")
    parser.add_argument("--output", type=Path, required=True, help="UTF-8 JSON output path")
    parser.add_argument("--run-dir", type=Path, required=True, help="Marked workspace for all output/status/log files")
    parser.add_argument("--yt-dlp", help="Optional yt-dlp executable path")
    parser.add_argument("--cookies-from-browser",
                        help="Optional browser to extract cookies from (e.g. edge, chrome, firefox)")
    parser.add_argument("--cookies-file", type=Path, help="Optional local Netscape cookie file path")
    parser.add_argument("--download-media", action="store_true",
                        help="Automatically download discovered public CDN images/videos into --run-dir")
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
                args.download_media,
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
            run_dir=run_dir,
            download_media=args.download_media,
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
                "media_type": metadata.get("media_type", "video"),
                "assets_manifest": metadata.get("assets_manifest", ""),
                "downloaded_assets": metadata.get("downloaded_assets", []),
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
