"""Manage local Douyin cookies for headless metadata extraction without syncing to git."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from typing import Any

DEFAULT_COOKIE_NAME = "douyin.txt"


def skill_cookie_dir() -> Path:
    skill_root = Path(__file__).resolve().parents[1]
    cookie_dir = skill_root / "cookies"
    cookie_dir.mkdir(parents=True, exist_ok=True)
    return cookie_dir


def cookie_file_path() -> Path:
    return skill_cookie_dir() / DEFAULT_COOKIE_NAME


def cookie_string_to_netscape(cookie_str: str, domain: str = ".douyin.com") -> str:
    lines = [
        "# Netscape HTTP Cookie File",
        "# Created locally by douyin-xiaohongshu-obsidian-note manage_cookies.py",
        "# Do not commit this file to git repository",
        "",
    ]
    expires = 2147483647
    for item in cookie_str.split(";"):
        if "=" in item:
            name, val = item.strip().split("=", 1)
            name, val = name.strip(), val.strip()
            if name:
                lines.append(f"{domain}\tTRUE\t/\tFALSE\t{expires}\t{name}\t{val}")
    return "\n".join(lines) + "\n"


def inspect_cookies() -> dict[str, Any]:
    path = cookie_file_path()
    if not path.is_file():
        return {
            "exists": False,
            "path": str(path),
            "message": "未发现本地 Cookie 文件。若遇 403 阻断，请使用 --from-browser 或 --set 更新。"
        }
    size = path.stat().st_size
    mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    keys_found = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) >= 6:
            keys_found.append(parts[5])
    return {
        "exists": True,
        "path": str(path),
        "size_bytes": size,
        "updated_at": mtime,
        "cookie_count": len(lines),
        "key_names": keys_found[:12],
    }


def save_cookie_text(content: str) -> dict[str, Any]:
    path = cookie_file_path()
    raw = content.strip()
    if not raw:
        raise ValueError("Cookie 内容不能为空")
    if "# Netscape HTTP Cookie File" not in raw and "\t" not in raw:
        formatted = cookie_string_to_netscape(raw)
    else:
        formatted = raw + "\n"
    path.write_text(formatted, encoding="utf-8", newline="\n")
    return {"saved": True, "path": str(path), "bytes": len(formatted.encode("utf-8"))}


def import_from_browser(browser_name: str) -> dict[str, Any]:
    try:
        from yt_dlp.cookies import extract_cookies_from_browser
        jar = extract_cookies_from_browser(browser_name)
        path = cookie_file_path()
        jar.save(str(path), ignore_discard=True, ignore_expires=True)
        return {
            "imported": True,
            "browser": browser_name,
            "path": str(path),
            "cookie_count": len(jar),
        }
    except Exception as exc:
        raise RuntimeError(
            f"从 {browser_name} 提取 Cookie 失败: {exc}。\n"
            f"提示：若 {browser_name} 正在运行，可能独占锁定了 Cookie 数据库，请先短暂关闭浏览器后重试；\n"
            f"或者在浏览器 F12 网络请求中复制 Cookie 标头，使用 --set 粘贴更新。"
        ) from exc


def clear_cookies() -> dict[str, Any]:
    path = cookie_file_path()
    existed = path.is_file()
    path.unlink(missing_ok=True)
    return {"cleared": existed, "path": str(path)}


def cookie_guidance_message() -> str:
    return (
        "【抖音 Cookie 刷新引导】\n"
        "检测到本地保存的抖音 Cookie 已失效或已过期（平台返回 HTTP 403 / Fresh cookies needed）。\n"
        "请选择以下任一方式在本地更新 Cookie（此文件保存在本地，绝不同步到 GitHub）：\n"
        "  1. 浏览器一键更新（请先短暂关闭浏览器避免文件锁）：\n"
        "     python scripts/manage_cookies.py --from-browser edge\n"
        "  2. 直接粘贴 Cookie 标头（在浏览器 F12 中复制 Cookie 文本）：\n"
        "     python scripts/manage_cookies.py --set \"粘贴你的Cookie字符串\"\n"
        "  3. 导入已有 cookies.txt 文件：\n"
        "     python scripts/manage_cookies.py --from-file \"D:\\path\\to\\cookies.txt\""
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="Inspect status of local cookie file")
    parser.add_argument("--set", dest="cookie_string", help="Save a raw cookie string (name1=val1; name2=val2)")
    parser.add_argument("--from-file", type=Path, help="Import a local Netscape or text cookie file")
    parser.add_argument("--from-browser", choices=["edge", "chrome", "firefox", "brave", "opera", "vivaldi"],
                        help="Extract and save cookies from a desktop browser into local cookies/douyin.txt")
    parser.add_argument("--clear", action="store_true", help="Delete the local cookie file")
    parser.add_argument("--guidance", action="store_true", help="Print user guidance message for expired cookies")
    args = parser.parse_args()

    if args.guidance:
        print(cookie_guidance_message())
        return 0

    if args.clear:
        result = clear_cookies()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.cookie_string:
        result = save_cookie_text(args.cookie_string)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.from_file:
        file_path = args.from_file.expanduser().resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"Cookie 文件未找到: {file_path}")
        content = file_path.read_text(encoding="utf-8-sig")
        result = save_cookie_text(content)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.from_browser:
        try:
            result = import_from_browser(args.from_browser)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    result = inspect_cookies()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
