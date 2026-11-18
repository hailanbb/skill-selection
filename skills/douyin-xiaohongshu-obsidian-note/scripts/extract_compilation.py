"""Extract all video episodes from a Douyin compilation (Mix) without opening a visible browser."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time
from typing import Any
import urllib.error
import urllib.request

try:
    from .manage_cookies import cookie_file_path, load_cookie_header
except ImportError:
    from manage_cookies import cookie_file_path, load_cookie_header


DOUYIN_ID_RE = re.compile(r"^[0-9]{6,24}$")
COLLECTION_PATH_RE = re.compile(r"/(?:collection|mix)/([0-9]{6,24})(?:/([0-9]+))?", re.IGNORECASE)


def parse_mix_id_from_url(url: str) -> str | None:
    match = COLLECTION_PATH_RE.search(url)
    if match:
        return match.group(1)
    return None


def resolve_mix_from_user_page(
    user_url: str,
    target_name: str | None = None,
    cookies_file: Path | None = None,
) -> tuple[str, str]:
    """Resolve mix_id and mix_name from a Douyin user profile page using headless Playwright."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("Playwright is required to resolve compilations from user profile pages.")

    c_path = cookies_file if cookies_file is not None else cookie_file_path("douyin")
    playwright_cookies = []
    if c_path.is_file() and c_path.stat().st_size > 0:
        for line in c_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                playwright_cookies.append({
                    "name": parts[5],
                    "value": parts[6],
                    "domain": parts[0],
                    "path": parts[2],
                    "secure": parts[3].upper() == "TRUE",
                })

    with sync_playwright() as p:
        browser = None
        for channel in ("msedge", "chrome", None):
            try:
                browser = p.chromium.launch(
                    headless=True,
                    channel=channel,
                    args=["--no-proxy-server", "--disable-blink-features=AutomationControlled"],
                )
                break
            except Exception:
                continue
        if browser is None:
            raise RuntimeError("Could not launch headless browser (Edge/Chrome/Chromium).")

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
        )
        if playwright_cookies:
            context.add_cookies(playwright_cookies)

        page = context.new_page()
        page.goto(user_url, wait_until="domcontentloaded", timeout=25000)
        time.sleep(2.5)

        for btn_text in ("取消", "稍后再说", "关闭"):
            try:
                btn = page.locator(f"button:has-text('{btn_text}')").first
                if btn.is_visible(timeout=800):
                    btn.click()
                    break
            except Exception:
                pass
        page.keyboard.press("Escape")
        time.sleep(1)

        collections = page.evaluate("""() => {
            const results = [];
            const seen = new Set();
            document.querySelectorAll('a').forEach(a => {
                const href = a.href || '';
                const m = href.match(/\\/collection\\/(\\d+)/);
                if (m && !seen.has(m[1])) {
                    seen.add(m[1]);
                    const text = (a.innerText || '').replace(/\\s+/g, ' ').trim();
                    results.push({mix_id: m[1], text: text});
                }
            });
            return results;
        }""")

        browser.close()

    if not collections:
        raise ValueError(f"No compilation collections found on user page: {user_url}")

    if target_name:
        clean_target = target_name.replace("&", "").replace(" ", "").lower()
        for c in collections:
            t = c["text"].replace("&", "").replace(" ", "").lower()
            if clean_target in t or t in clean_target:
                name = c["text"].split()[0] if c["text"] else "compilation"
                return c["mix_id"], name

    # Default to first collection
    first = collections[0]
    name = first["text"].split()[0] if first["text"] else "compilation"
    return first["mix_id"], name


def _clean_text(raw_val: str) -> str:
    if not raw_val:
        return ""
    if r"\u" in raw_val or r"\n" in raw_val:
        try:
            return json.loads(f'"{raw_val}"')
        except Exception:
            pass
    return raw_val


def get_compilation_cache_path(mix_id: str, cookies_file: Path | None = None) -> Path:
    base = cookies_file.parent if cookies_file else cookie_file_path("douyin").parent
    return base / "compilations" / f"{mix_id}.json"


def load_cached_compilation(mix_id: str, cookies_file: Path | None = None) -> dict[str, Any] | None:
    cache_file = get_compilation_cache_path(mix_id, cookies_file)
    if cache_file.is_file():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("episodes"):
                return data
        except Exception:
            pass
    return None


def save_cached_compilation(data: dict[str, Any], mix_id: str, cookies_file: Path | None = None) -> None:
    if not data or not data.get("episodes"):
        return
    cache_file = get_compilation_cache_path(mix_id, cookies_file)
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def fetch_compilation_episodes(
    mix_id: str,
    cookies_file: Path | None = None,
    mix_name: str | None = None,
    limit: int | None = None,
    quiet: bool = False,
) -> dict[str, Any]:
    """Fetch all video episodes in a Douyin compilation via fast pure HTTP chunks."""
    c_path = cookies_file if cookies_file is not None else cookie_file_path("douyin")
    cookie_header = load_cookie_header("douyin", explicit_file=c_path)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if cookie_header:
        headers["Cookie"] = cookie_header

    ep = 1
    all_episodes: list[dict[str, Any]] = []
    seen_vids: set[str] = set()
    resolved_mix_name = mix_name

    if not quiet:
        print(f"[Douyin Compilation] Starting fast HTTP crawl for mix_id={mix_id}...", file=sys.stderr)

    while True:
        if limit is not None and len(all_episodes) >= limit:
            break

        url = f"https://www.douyin.com/collection/{mix_id}/{ep}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
        except Exception as exc:
            if not quiet:
                print(f"[Douyin Compilation] Warning: HTTP fetch error at ep {ep}: {exc}", file=sys.stderr)
            break

        # Attempt to resolve mix_name from HTML if not provided
        if not resolved_mix_name:
            m_mix = re.search(r'\\"mix_name\\":\\"(.*?)\\"', html)
            if m_mix:
                resolved_mix_name = _clean_text(m_mix.group(1))

        vids = list(dict.fromkeys(re.findall(r"/video/(\d+)", html)))
        new_vids = [v for v in vids if v not in seen_vids]
        if not new_vids:
            if "验证码" in html or "sec.douyin.com" in html or "_$jsvmprt" in html or "verify_center" in html:
                cached = load_cached_compilation(mix_id, cookies_file=cookies_file)
                if cached:
                    if not quiet:
                        print(
                            f"[Douyin Compilation] 提示: 访问合集触发了抖音真人验证码拦截，但成功命中本地合集快照缓存（共 {len(cached.get('episodes', []))} 集）！",
                            file=sys.stderr,
                        )
                    if limit is not None:
                        cached["episodes"] = cached["episodes"][:limit]
                        cached["total_episodes"] = len(cached["episodes"])
                    return cached
                raise RuntimeError(
                    "Douyin CAPTCHA triggered: 抖音合集访问触发滑块验证码拦截（验证码中间页）。"
                    "请在浏览器中打开合集页面并完成滑块验证后使用 Cookie-Editor 重新导出 Cookie。"
                )
            if not quiet:
                print(f"[Douyin Compilation] No further videos found at ep {ep}. Completed.", file=sys.stderr)
            break

        for v in new_vids:
            seen_vids.add(v)
            m_title = re.search(rf'\\"awemeId\\":\\"{v}\\".*?\\"itemTitle\\":\\"(.*?)\\"', html)
            title = _clean_text(m_title.group(1)) if m_title else ""
            if not title:
                m_desc = re.search(rf'\\"awemeId\\":\\"{v}\\".*?\\"caption\\":\\"(.*?)\\"', html)
                title = _clean_text(m_desc.group(1)) if m_desc else ""

            all_episodes.append({
                "episode": len(all_episodes) + 1,
                "vid": v,
                "url": f"https://www.douyin.com/video/{v}",
                "title": title,
                "mix_id": mix_id,
            })
            if limit is not None and len(all_episodes) >= limit:
                break

        if not quiet:
            print(f"[Douyin Compilation] Chunk ep={ep}: +{len(new_vids)} episodes (Total: {len(all_episodes)})", file=sys.stderr)

        ep += len(new_vids)
        time.sleep(0.2)

    res = {
        "platform": "douyin",
        "mix_id": mix_id,
        "mix_name": resolved_mix_name or "compilation",
        "total_episodes": len(all_episodes),
        "episodes": all_episodes,
    }
    if len(all_episodes) > 0:
        save_cached_compilation(res, mix_id, cookies_file=cookies_file)
    return res


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="Compilation URL or user compilation profile URL")
    parser.add_argument("--mix-id", help="Direct compilation/mix ID")
    parser.add_argument("--name", help="Optional compilation name keyword (for multi-compilation user profiles)")
    parser.add_argument("--cookies-file", type=Path, help="Explicit Netscape cookie file")
    parser.add_argument("--limit", type=int, help="Maximum number of episodes to fetch")
    parser.add_argument("--output", type=Path, help="Save structured compilation JSON to file")
    parser.add_argument("--urls-file", type=Path, help="Save canonical video URLs to a text file (one URL per line)")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress logs")
    parser.add_argument("--dump-json", action="store_true", help="Print JSON result to stdout")
    args = parser.parse_args()

    mix_id = args.mix_id
    mix_name = args.name

    if not mix_id and not args.url:
        parser.error("Must provide either --url or --mix-id")

    if not mix_id and args.url:
        parsed_id = parse_mix_id_from_url(args.url)
        if parsed_id:
            mix_id = parsed_id
        elif "/user/" in args.url and "showSubTab=compilation" in args.url:
            if not args.quiet:
                print(f"[Douyin Compilation] Resolving compilation from user profile page...", file=sys.stderr)
            mix_id, mix_name = resolve_mix_from_user_page(
                args.url,
                target_name=args.name,
                cookies_file=args.cookies_file,
            )
            if not args.quiet:
                print(f"[Douyin Compilation] Resolved mix_id={mix_id}, name='{mix_name}'", file=sys.stderr)
        else:
            parser.error(f"Cannot identify compilation or mix ID from URL: {args.url}")

    result = fetch_compilation_episodes(
        mix_id=mix_id,
        cookies_file=args.cookies_file,
        mix_name=mix_name,
        limit=args.limit,
        quiet=args.quiet,
    )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if not args.quiet:
            print(f"[Douyin Compilation] Saved JSON to: {args.output}", file=sys.stderr)

    if args.urls_file:
        args.urls_file.parent.mkdir(parents=True, exist_ok=True)
        lines = [ep["url"] for ep in result["episodes"]]
        args.urls_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if not args.quiet:
            print(f"[Douyin Compilation] Saved {len(lines)} URLs to: {args.urls_file}", file=sys.stderr)

    if args.dump_json or (not args.output and not args.urls_file):
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
