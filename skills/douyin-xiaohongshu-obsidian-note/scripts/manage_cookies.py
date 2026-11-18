"""Manage local Douyin/Xiaohongshu cookies for headless metadata extraction without syncing to git."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

DEFAULT_COOKIE_NAME = "douyin.txt"
PLATFORM_FILES = {
    "douyin": "douyin.txt",
    "xiaohongshu": "xiaohongshu.txt",
}
PLATFORM_DOMAINS = {
    "douyin": ".douyin.com",
    "xiaohongshu": ".xiaohongshu.com",
}


def skill_cookie_dir() -> Path:
    skill_root = Path(__file__).resolve().parents[1]
    cookie_dir = skill_root / "cookies"
    cookie_dir.mkdir(parents=True, exist_ok=True)
    return cookie_dir


def cookie_file_path(platform: str = "douyin") -> Path:
    filename = PLATFORM_FILES.get(platform, DEFAULT_COOKIE_NAME)
    return skill_cookie_dir() / filename


def load_cookie_header(platform: str = "douyin", explicit_file: Path | None = None) -> str:
    """Read a Netscape or raw cookie file and return a Cookie HTTP header string."""
    c_path = explicit_file if explicit_file is not None else cookie_file_path(platform)
    if not c_path.is_file() or c_path.stat().st_size == 0:
        return ""
    text = c_path.read_text(encoding="utf-8", errors="ignore")
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    cookies_list: list[str] = []
    for line in lines:
        if "\t" in line:
            parts = line.split("\t")
            if len(parts) >= 7:
                cookies_list.append(f"{parts[5]}={parts[6]}")
        elif "=" in line:
            for item in line.split(";"):
                if "=" in item:
                    k, v = item.strip().split("=", 1)
                    if k.strip():
                        cookies_list.append(f"{k.strip()}={v.strip()}")
    return "; ".join(cookies_list)


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


def normalize_cookie_to_netscape(raw_content: str, platform: str = "douyin") -> str:
    """Normalize any cookie format (Cookie-Editor JSON, Header string, Netscape) to Netscape HTTP format."""
    raw = raw_content.strip()
    if not raw:
        raise ValueError("Cookie 内容不能为空")
    default_domain = PLATFORM_DOMAINS.get(platform, ".douyin.com")

    # 1. Detect JSON array format (Cookie-Editor export as JSON)
    if raw.startswith("[") or raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                parsed = [parsed]
            if isinstance(parsed, list):
                lines = [
                    "# Netscape HTTP Cookie File",
                    "# Created locally by douyin-xiaohongshu-obsidian-note manage_cookies.py",
                    "# Do not commit this file to git repository",
                    "",
                ]
                count = 0
                for item in parsed:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name", "")).strip()
                    val = str(item.get("value", "")).strip()
                    if not name:
                        continue
                    domain = str(item.get("domain") or default_domain).strip()
                    flag = "TRUE" if domain.startswith(".") else "FALSE"
                    path = str(item.get("path") or "/").strip()
                    secure = "TRUE" if item.get("secure") else "FALSE"
                    exp = item.get("expirationDate")
                    if exp is not None:
                        try:
                            expires = str(int(float(exp)))
                        except (ValueError, TypeError):
                            expires = "2147483647"
                    else:
                        expires = "2147483647"
                    lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{val}")
                    count += 1
                if count > 0:
                    return "\n".join(lines) + "\n"
        except json.JSONDecodeError:
            pass

    # 2. Detect Netscape format
    if "# Netscape HTTP Cookie File" in raw or any("\t" in line and len(line.split("\t")) >= 6 for line in raw.splitlines()):
        lines = [
            "# Netscape HTTP Cookie File",
            "# Created locally by douyin-xiaohongshu-obsidian-note manage_cookies.py",
            "# Do not commit this file to git repository",
            "",
        ]
        for line in raw.splitlines():
            line_str = line.strip()
            if not line_str or line_str.startswith("#"):
                continue
            if "\t" in line_str:
                parts = line_str.split("\t")
                if len(parts) >= 6:
                    lines.append(line_str)
        return "\n".join(lines) + "\n"

    # 3. Detect Header String format (e.g. name=val; name2=val2 or newline separated)
    return cookie_string_to_netscape(raw, domain=default_domain)


def inspect_cookies(platform: str = "douyin") -> dict[str, Any]:
    path = cookie_file_path(platform)
    if not path.is_file():
        return {
            "platform": platform,
            "exists": False,
            "path": str(path),
            "message": f"未发现本地 {platform} Cookie 文件。若遇 403 阻断，请使用 --from-browser、--set 或 --stdin 更新。"
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
        "platform": platform,
        "exists": True,
        "path": str(path),
        "size_bytes": size,
        "updated_at": mtime,
        "cookie_count": len(lines),
        "key_names": keys_found[:12],
    }


def save_cookie_text(content: str, platform: str = "douyin") -> dict[str, Any]:
    path = cookie_file_path(platform)
    formatted = normalize_cookie_to_netscape(content, platform=platform)
    path.write_text(formatted, encoding="utf-8", newline="\n")
    return {"saved": True, "platform": platform, "path": str(path), "bytes": len(formatted.encode("utf-8"))}


def import_from_browser(browser_name: str, platform: str = "douyin") -> dict[str, Any]:
    try:
        from yt_dlp.cookies import extract_cookies_from_browser
        jar = extract_cookies_from_browser(browser_name)
        path = cookie_file_path(platform)
        jar.save(str(path), ignore_discard=True, ignore_expires=True)
        return {
            "imported": True,
            "platform": platform,
            "browser": browser_name,
            "path": str(path),
            "cookie_count": len(jar),
        }
    except Exception as exc:
        raise RuntimeError(
            f"从 {browser_name} 提取 Cookie 失败: {exc}。\n"
            f"提示：若 {browser_name} 正在运行，可能独占锁定了 Cookie 数据库，请先短暂关闭浏览器后重试；\n"
            f"或者在浏览器使用 Cookie-Editor 导出后，使用 --set 或 --stdin 粘贴更新。"
        ) from exc


def clear_cookies(platform: str = "douyin") -> dict[str, Any]:
    path = cookie_file_path(platform)
    existed = path.is_file()
    path.unlink(missing_ok=True)
    return {"cleared": existed, "platform": platform, "path": str(path)}


def cookie_guidance_message(platform: str = "douyin") -> str:
    label = "抖音" if platform == "douyin" else "小红书"
    flag = "" if platform == "douyin" else f" --platform {platform}"
    return (
        f"【{label} Cookie 主动更新引导】\n"
        f"检测到本地保存的 {label} Cookie 尚未配置或已失效（HTTP 403 / 需登录验证）。\n"
        f"本技能绝不打开任何内置浏览器，完全在无头环境运行。请选择以下任一方式在本地更新 Cookie（此文件保存在本地，绝不同步到 GitHub）：\n\n"
        f"推荐方案：使用 Chrome 扩展 Cookie-Editor（全自动识别 JSON / Header / Netscape 格式）：\n"
        f"  1. 安装扩展：https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm\n"
        f"  2. 在浏览器打开并登录 {label} 网页，点击 Cookie-Editor 插件图标；\n"
        f"  3. 点击下方【Export】按钮，选择【Export as JSON】（或 Header String / Netscape）；\n"
        f"  4. 将复制的内容直接在对话中发送给 Agent，或通过命令行更新：\n"
        f"     python scripts/manage_cookies.py{flag} --set \"<Cookie文本>\"\n"
        f"     （或从文件导入：python scripts/manage_cookies.py{flag} --from-file \"cookies.txt\"）\n\n"
        f"备用方案（若浏览器未运行）：\n"
        f"  python scripts/manage_cookies.py{flag} --from-browser edge"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=["douyin", "xiaohongshu"], default="douyin",
                        help="Target platform cookie file (default: douyin)")
    parser.add_argument("--status", action="store_true", help="Inspect status of local cookie file")
    parser.add_argument("--set", dest="cookie_string", help="Save a raw cookie string (JSON array, Header string, or Netscape)")
    parser.add_argument("--stdin", action="store_true", help="Read UTF-8 cookie content from standard input")
    parser.add_argument("--from-file", type=Path, help="Import a local JSON, Netscape or text cookie file")
    parser.add_argument("--from-browser", choices=["edge", "chrome", "firefox", "brave", "opera", "vivaldi"],
                        help="Extract and save cookies from a desktop browser into local cookies/<platform>.txt")
    parser.add_argument("--clear", action="store_true", help="Delete the local cookie file")
    parser.add_argument("--guidance", action="store_true", help="Print user guidance message for expired cookies")
    args = parser.parse_args()

    if args.guidance:
        print(cookie_guidance_message(args.platform))
        return 0

    if args.clear:
        result = clear_cookies(args.platform)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.stdin:
        content = sys.stdin.buffer.read().decode("utf-8-sig")
        result = save_cookie_text(content, args.platform)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.cookie_string:
        result = save_cookie_text(args.cookie_string, args.platform)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.from_file:
        file_path = args.from_file.expanduser().resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"Cookie 文件未找到: {file_path}")
        content = file_path.read_text(encoding="utf-8-sig")
        result = save_cookie_text(content, args.platform)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.from_browser:
        try:
            result = import_from_browser(args.from_browser, args.platform)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    result = inspect_cookies(args.platform)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
