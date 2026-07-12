import os
import re
import sys
import json
import urllib.request
import urllib.parse
import shutil
import subprocess
from mimetypes import guess_extension

# 强迫 Windows 控制台输出统一使用 UTF-8 编码，防止因为 \xa0 等特殊字符导致 GBK 编码崩溃
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
CONFIG_FILE = os.path.join(SKILL_ROOT, "config.json")

# 用户全局的 AppData Roaming 路径
APPDATA_ROAMING = os.environ.get("APPDATA", r"C:\Users\HiWin11\AppData\Roaming")

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(vault_path, image_dir_name):
    config = {
        "vault_path": os.path.abspath(vault_path),
        "image_dir_name": image_dir_name.strip()
    }
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    return config

def get_mcp_config_path():
    target = r"C:\Users\HiWin11\.gemini\antigravity\mcp_config.json"
    if os.path.exists(target):
        return target
    home = os.path.expanduser("~")
    probe = os.path.join(home, ".gemini", "antigravity", "mcp_config.json")
    if os.path.exists(probe):
        return probe
    return None

def check_dependencies():
    missing = []
    try:
        import bs4
    except ImportError:
        missing.append("beautifulsoup4")
    try:
        import markdownify
    except ImportError:
        missing.append("markdownify")
    try:
        import lxml
    except ImportError:
        missing.append("lxml")
    return missing

def check_optional_mcp_status():
    status = {
        "node_installed": shutil.which("node") is not None,
        "npm_installed": shutil.which("npm") is not None,
        "enquire_mcp_installed": False,
        "enquire_mcp_registered": False,
        "firecrawl_mcp_registered": False,
        "anysearch_skill_installed": False
    }
    
    global_enquire_path = os.path.join(APPDATA_ROAMING, r"npm\node_modules\@oomkapwn\enquire-mcp\dist\index.js")
    if os.path.exists(global_enquire_path) or shutil.which("enquire-mcp"):
        status["enquire_mcp_installed"] = True
        
    mcp_config_path = get_mcp_config_path()
    if mcp_config_path and os.path.exists(mcp_config_path):
        try:
            with open(mcp_config_path, 'r', encoding='utf-8') as f:
                mcp_data = json.load(f)
            servers = mcp_data.get("mcpServers", {})
            status["enquire_mcp_registered"] = "enquire-mcp" in servers
            status["firecrawl_mcp_registered"] = "firecrawl-mcp" in servers
        except Exception:
            pass
            
    skills_parent = os.path.dirname(SKILL_ROOT)
    anysearch_probe_paths = [
        os.path.join(skills_parent, "anysearch-skill"),
        os.path.join(skills_parent, "anysearch")
    ]
    for p in anysearch_probe_paths:
        if os.path.exists(p):
            status["anysearch_skill_installed"] = True
            break
            
    return status

def sanitize_filename(filename):
    safe = re.sub(r'[\/\\:\*\?"<>\|]', '_', filename)
    return " ".join(safe.split()).strip()

def fetch_url(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://mp.weixin.qq.com/",
        "Connection": "keep-alive"
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as response:
        return response.read()

def localize_images(soup, vault_path, image_dir_name, title):
    safe_title = sanitize_filename(title)
    assets_abs_dir = os.path.join(vault_path, image_dir_name, safe_title)
    assets_rel_dir = f"{image_dir_name}/{safe_title}"
    
    if not os.path.exists(assets_abs_dir):
        os.makedirs(assets_abs_dir)
        
    js_content = soup.find('div', id='js_content') or soup.find('body') or soup
    img_tags = js_content.find_all('img')
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://mp.weixin.qq.com/"
    }
    
    img_count = 0
    for img in img_tags:
        img_url = img.get('data-src') or img.get('src')
        if not img_url or not img_url.startswith("http"):
            continue
            
        img_count += 1
        ext = ".png"
        
        parsed_url = urllib.parse.urlparse(img_url)
        params = urllib.parse.parse_qs(parsed_url.query)
        if 'wx_fmt' in params:
            ext_val = params['wx_fmt'][0]
            if ext_val in ['png', 'jpeg', 'jpg', 'gif', 'webp']:
                ext = f".{ext_val}"
                
        local_img_name = f"image_{img_count}{ext}"
        local_img_abs_path = os.path.join(assets_abs_dir, local_img_name)
        local_img_rel_path = f"{assets_rel_dir}/{local_img_name}"
        
        try:
            req = urllib.request.Request(img_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                content_type = response.info().get('Content-Type')
                if content_type:
                    guessed_ext = guess_extension(content_type)
                    if guessed_ext:
                        if guessed_ext == '.jpe':
                            guessed_ext = '.jpg'
                        ext = guessed_ext
                        local_img_name = f"image_{img_count}{ext}"
                        local_img_abs_path = os.path.join(assets_abs_dir, local_img_name)
                        local_img_rel_path = f"{assets_rel_dir}/{local_img_name}"
                
                with open(local_img_abs_path, 'wb') as out_f:
                    out_f.write(response.read())
            
            print(f"Downloaded: {local_img_name}", file=sys.stderr)
            img.replace_with(f"![[{local_img_rel_path}]]")
            
        except Exception as e:
            print(f"Failed to download image {img_count} ({img_url}): {e}", file=sys.stderr)
            if img.get('data-src'):
                img['src'] = img['data-src']

def update_enquire_mcp(vault_path):
    global_enquire_path = os.path.join(APPDATA_ROAMING, r"npm\node_modules\@oomkapwn\enquire-mcp\dist\index.js")
    mcp_js_path = global_enquire_path if os.path.exists(global_enquire_path) else shutil.which("enquire-mcp")
    
    if not mcp_js_path:
        print("Warning: enquire-mcp CLI not found globally. Skipping index sync.", file=sys.stderr)
        return False
        
    try:
        print("Refreshing enquire-mcp index...", file=sys.stderr)
        subprocess.run(
            ["node", mcp_js_path, "index", "--vault", vault_path, "--tokenize", "trigram"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        print("Building embeddings...", file=sys.stderr)
        subprocess.run(
            ["node", mcp_js_path, "build-embeddings", "--vault", vault_path],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        print("Enquire-MCP indices refreshed!", file=sys.stderr)
        return True
    except Exception as e:
        print(f"Error updating enquire-mcp: {e}", file=sys.stderr)
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python save_to_obsidian.py doctor")
        print("  python save_to_obsidian.py configure --vault <path> --image_dir <name>")
        print("  python save_to_obsidian.py fetch --url <url>")
        print("  python save_to_obsidian.py localize --title <title> --html <file_or_string>")
        print("  python save_to_obsidian.py index")
        sys.exit(1)
        
    cmd = sys.argv[1]
    
    # 1. doctor
    if cmd == "doctor":
        missing_py = check_dependencies()
        optional_status = check_optional_mcp_status()
        
        result = {
            "status": "success" if not missing_py else "missing_dependencies",
            "missing_python_packages": missing_py,
            "optional_mcp_status": optional_status,
            "python_executable": sys.executable,
            "help_message": {
                "python_install": "pip install beautifulsoup4 markdownify lxml" if missing_py else "Ready",
                "enquire_mcp_install": "npm install -g @oomkapwn/enquire-mcp" if not optional_status["enquire_mcp_installed"] else "Installed",
                "anysearch_skill_install": "Please install the 'anysearch-skill' in your config/skills/ directory." if not optional_status["anysearch_skill_installed"] else "Installed",
                "node_warning": "NodeJS/NPM is required to install enquire-mcp." if not optional_status["npm_installed"] else "Ready"
            }
        }
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)
        
    # 2. configure
    if cmd == "configure":
        v_idx = sys.argv.index("--vault") if "--vault" in sys.argv else -1
        i_idx = sys.argv.index("--image_dir") if "--image_dir" in sys.argv else -1
        if v_idx == -1 or v_idx + 1 >= len(sys.argv) or i_idx == -1 or i_idx + 1 >= len(sys.argv):
            print(json.dumps({"status": "error", "message": "Missing --vault or --image_dir arguments."}))
            sys.exit(1)
            
        v_path = sys.argv[v_idx + 1]
        i_dir = sys.argv[i_idx + 1]
        
        if not os.path.exists(v_path):
            print(json.dumps({"status": "error", "message": f"Vault path '{v_path}' does not exist on disk."}))
            sys.exit(1)
            
        save_config(v_path, i_dir)
        print(json.dumps({"status": "success", "message": "Configuration successfully saved!"}))
        sys.exit(0)
        
    # 3. 读取配置 (fetch, localize, index 共享)
    config = load_config()
    vault_path = config.get("vault_path")
    image_dir_name = config.get("image_dir_name")
    
    if not vault_path or not image_dir_name:
        result = {
            "status": "needs_config",
            "message": "Obsidian vault path or image directory is missing in config.json."
        }
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)
        
    if cmd == "fetch":
        missing_py = check_dependencies()
        if missing_py:
            result = {
                "status": "missing_dependencies",
                "message": f"Required Python packages are missing: {', '.join(missing_py)}."
            }
            print(json.dumps(result, ensure_ascii=False))
            sys.exit(0)
            
        url_idx = sys.argv.index("--url") if "--url" in sys.argv else -1
        if url_idx == -1 or url_idx + 1 >= len(sys.argv):
            print(json.dumps({"status": "error", "message": "Missing --url parameter."}))
            sys.exit(1)
        url = sys.argv[url_idx + 1]
        
        try:
            from bs4 import BeautifulSoup
            print(f"Fetching URL: {url}", file=sys.stderr)
            raw_html = fetch_url(url)
            soup = BeautifulSoup(raw_html, 'lxml')
            
            title = ""
            title_meta = soup.find('meta', property='og:title')
            if title_meta:
                title = title_meta.get('content', '').strip()
            if not title:
                title_h1 = soup.find('h1', id='activity-name')
                if title_h1:
                    title = title_h1.get_text().strip()
            if not title:
                title = "未命名微信文章"
                
            author = ""
            author_meta = soup.find('meta', property='og:article:author')
            if author_meta:
                author = author_meta.get('content', '').strip()
            if not author:
                author_span = soup.find('span', id='profileBt')
                if author_span:
                    author_a = author_span.find('a')
                    if author_a:
                        author = author_a.get_text().strip()
            if not author:
                author = "未知作者"
                
            localize_images(soup, vault_path, image_dir_name, title)
            
            js_content = soup.find('div', id='js_content') or soup.find('body') or soup
            for tag in js_content.find_all(['script', 'style', 'iframe', 'svg']):
                tag.decompose()
                
            result = {
                "status": "success",
                "title": title,
                "author": author,
                "vault_path": vault_path,
                "image_dir_name": image_dir_name,
                "cleaned_html_body": str(js_content)
            }
            print(json.dumps(result, ensure_ascii=False))
            
        except Exception as e:
            print(json.dumps({"status": "error", "message": str(e)}))
            sys.exit(1)
            
    elif cmd == "localize":
        # 4. localize: 用于为 external 抓回来的 HTML 数据执行图片本地化与重构
        missing_py = check_dependencies()
        if missing_py:
            print(json.dumps({"status": "missing_dependencies", "message": f"Required packages missing: {', '.join(missing_py)}"}))
            sys.exit(1)
            
        t_idx = sys.argv.index("--title") if "--title" in sys.argv else -1
        h_idx = sys.argv.index("--html") if "--html" in sys.argv else -1
        if t_idx == -1 or t_idx + 1 >= len(sys.argv) or h_idx == -1 or h_idx + 1 >= len(sys.argv):
            print(json.dumps({"status": "error", "message": "Missing --title or --html arguments."}))
            sys.exit(1)
            
        title = sys.argv[t_idx + 1]
        html_input = sys.argv[h_idx + 1]
        
        # 支持传入文件路径或者 HTML 字符串本身
        html_content = ""
        if os.path.exists(html_input):
            with open(html_input, 'r', encoding='utf-8') as f:
                html_content = f.read()
        else:
            html_content = html_input
            
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'lxml')
            localize_images(soup, vault_path, image_dir_name, title)
            
            result = {
                "status": "success",
                "title": title,
                "vault_path": vault_path,
                "image_dir_name": image_dir_name,
                "cleaned_html_body": str(soup)
            }
            print(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            print(json.dumps({"status": "error", "message": str(e)}))
            sys.exit(1)
            
    elif cmd == "index":
        success = update_enquire_mcp(vault_path)
        print(json.dumps({"status": "success" if success else "skipped", "vault_path": vault_path}))
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()
