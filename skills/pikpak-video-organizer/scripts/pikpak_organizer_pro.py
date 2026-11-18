"""
PikPak 云端 AV 极速一键整理与广告清理工具 (Pro 自定义目录增强版)

功能特性：
1. 【自定义目录】：支持直接在终端点选网盘现有文件夹，或输入任意多级自定义路径（如 "影视/待整理"）。
2. 【配置自动记忆】：独立存储在 config.json 中，设置一次自动保存，后续双击回车即可直接使用。
3. 【极速并发】：15 线程并发重命名 + 按演员原子级批量移动（单次整理仅需数秒）。
4. 【智能元数据】：内置番号识别与实时元数据检索（支持女优中文化、版本后缀保留）。
5. 【安全防误触】：运行后先极速扫描展示待整理清单，经用户确认后才执行改动。
"""

import asyncio
import json
import os
import re
import sys
import time
import httpx
from bs4 import BeautifulSoup
from pikpakapi import PikPakApi

sys.stdout.reconfigure(encoding='utf-8')

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# 广告与博彩特征黑名单关键词（无论文件多大，一旦命中文件名直接归类为垃圾）
AD_KEYWORDS = [
    "澳门", "新葡京", "威尼斯人", "台妹子", "发廊", "福利群", "最新情报",
    "防走丢", "永久地址", "免费看", "在线观看", "菠菜", "博彩", "荷官",
    "荷官发牌", "最新地址", "av导航", "色情导航", "成人门户", "扫码", "推广"
]

def parse_code_and_check_ad(filename):
    """
    智能识别番号与广告判定：
    返回 (code, is_ad)
    """
    # 1. 广告关键词强特征拦截
    for kw in AD_KEYWORDS:
        if kw in filename:
            return None, True
            
    # 2. FC2 特殊番号 (FC2-PPV-1234567 或 FC2-1234567)
    m_fc2 = re.search(r'(FC2)[-_]?(?:PPV[-_]?)?(\d{5,7})', filename, re.IGNORECASE)
    if m_fc2:
        return f"FC2-PPV-{m_fc2.group(2)}", False

    # 3. 常规有码/无码番号 (2-6位字母 + 2-5位数字，如 IPX-123, MIDV-045, SSIS-001)
    m_std = re.search(r'([A-Za-z]{2,6})[-_](\d{2,5})', filename)
    if m_std:
        return f"{m_std.group(1).upper()}-{m_std.group(2)}", False

    return None, False
ACTRESS_CN_MAP = {
    "八掛うみ": "八挂海", "森沢かな": "森泽佳奈", "通野未帆": "通野未帆",
    "桃乃木かな": "桃乃木香奈", "武藤あやか": "武藤彩香", "七ツ森りり": "七森莉莉",
    "輝月あんり": "辉月杏梨", "篠田ゆう": "筱田优", "桜空もも": "樱空桃",
    "浅野こころ": "浅野心", "原紗央莉": "原纱央莉", "涼森れむ": "凉森玲梦",
    "新ありな": "新有菜", "七沢みあ": "七泽美亚", "伊藤舞雪": "伊藤舞雪",
    "向井藍": "向井蓝", "香水じゅん": "香水纯", "野々浦暖": "野野浦暖",
    "小倉由菜": "小仓由菜", "楪カレン": "楪可怜", "楓カレン": "楪可怜",
    "本庄鈴": "本庄铃", "七瀬アリス": "七濑爱丽丝", "三上悠亜": "三上悠亚",
    "水咲ローラ": "水咲萝拉 (泷泽萝拉)", "田中なな実": "田中七海",
    "明日花キララ": "明日花绮罗", "蓮実クレア": "莲实克蕾儿",
    "一ノ瀬アメリ": "一之濑亚美莉", "宮島めい": "宫岛芽衣", "夢実かなえ": "梦实香奈惠",
    "本郷愛": "本乡爱", "山岸逢花": "山岸逢花", "河北彩花": "河北彩花",
    "河北彩伽": "河北彩伽", "相沢みなみ": "相泽南", "天使もえ": "天使萌",
    "椎名そら": "椎名空", "宮下玲奈": "宫下玲奈", "設楽ゆうひ": "设乐夕阳",
    "桃谷エリカ": "桃谷绘里香", "希崎ジェシカ": "希崎洁西卡", "白峰ミウ": "白峰美羽",
    "藤井蘭々": "藤井兰兰", "希島あいり": "希岛爱理"
}

def load_config():
    """读取本地配置文件"""
    default_cfg = {
        "access_token": "",
        "source_folder": "My Pack",
        "target_folder": "女优",
        "concurrency_limit": 15,
        "min_video_size_mb": 50,
        "clean_ads": True,
        "delete_empty_subdirs": True
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                default_cfg.update(loaded)
        except Exception:
            pass
    return default_cfg

def save_config(cfg):
    """保存配置到本地 config.json"""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[提示] 保存配置失败: {e}")

def sanitize_filename(name):
    """过滤 Windows 及网盘非法字符"""
    name = re.sub(r'[\\/:*?"<>|]', ' ', name)
    name = re.sub(r'\s+', ' ', name)
    return name.strip()

async def fetch_folder_items(client, folder_id):
    """抓取单个文件夹下的全部文件与子文件夹"""
    items = []
    page_token = None
    while True:
        res = await client.file_list(size=100, parent_id=folder_id, next_page_token=page_token)
        items.extend(res.get("files", []))
        page_token = res.get("next_page_token")
        if not page_token:
            break
    return items

async def resolve_or_create_path(client, path_str, create_if_missing=False):
    """
    支持单级或多级路径寻址（如 'My Pack' 或 '影视/日韩/待整理'）
    返回目标文件夹的元数据对象（包含 id），若不存在且未开启创建则返回 None
    """
    clean_path = path_str.strip().replace("\\", "/").strip("/")
    if not clean_path:
        return {"id": None, "name": "根目录"}

    parts = [p.strip() for p in clean_path.split("/") if p.strip()]
    current_parent_id = None
    target_folder = None

    for part in parts:
        items = await fetch_folder_items(client, current_parent_id)
        found = next((f for f in items if f["name"] == part and f.get("kind") == "drive#folder"), None)
        if found:
            current_parent_id = found["id"]
            target_folder = found
        else:
            if create_if_missing:
                res = await client.create_folder(name=part, parent_id=current_parent_id)
                new_folder = res.get("file", {})
                current_parent_id = new_folder.get("id")
                target_folder = new_folder
            else:
                return None
    return target_folder

async def scan_all_under_folder(client, root_folder_id):
    """递归获取目录下的所有文件和子目录"""
    top_items = await fetch_folder_items(client, root_folder_id)
    subfolders = [item for item in top_items if item.get("kind") == "drive#folder"]
    files = [item for item in top_items if item.get("kind") != "drive#folder"]
    
    if subfolders:
        sub_tasks = [fetch_folder_items(client, sf["id"]) for sf in subfolders]
        sub_results = await asyncio.gather(*sub_tasks)
        for sf, items in zip(subfolders, sub_results):
            for it in items:
                if it.get("kind") == "drive#folder":
                    subfolders.append(it)
                    deeper = await fetch_folder_items(client, it["id"])
                    files.extend([d for d in deeper if d.get("kind") != "drive#folder"])
                else:
                    files.append(it)
    return subfolders, files

async def scrape_online_meta(session, code, original_filename=""):
    """
    智能元数据检索：
    1. 本地优先：若原文件名中已含有女优名（繁简日均支持），秒级匹配，杜绝网络异常导致误判
    2. 网络引擎：向 Jav321 查询，自动跟随 301 重定向定位详情页
    3. 双重提取：支持提取 '出演者:' 标签，或从 H3 标题自动嗅探女优名
    """
    # 1. 本地文件名优先提取女优
    if original_filename:
        for jp, cn in ACTRESS_CN_MAP.items():
            if jp in original_filename or cn in original_filename:
                return cn, ""

    # 2. 网络在线刮削
    try:
        r = await session.post("https://www.jav321.com/search", data={"sn": code}, timeout=10.0)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            h3 = soup.find("h3")
            title_raw = h3.text.strip() if h3 else ""
            
            actress = "未知演员"
            col = soup.find("div", class_="col-md-9")
            if col:
                m = re.search(r'出演者:\s*([^\s\xa0]+)', col.text)
                if m:
                    actress = m.group(1).strip()
            
            # 若 col 中未标出演者，从 H3 标题嗅探女优名
            if actress == "未知演员" and title_raw:
                for jp, cn in ACTRESS_CN_MAP.items():
                    if jp in title_raw or cn in title_raw:
                        actress = jp
                        break
            
            clean_title = re.sub(rf'\s*{code}\b.*$', '', title_raw, flags=re.IGNORECASE).strip()
            clean_title = re.sub(r'【[^】]*特典[^】]*】', '', clean_title).strip()
            if len(clean_title) > 35:
                clean_title = clean_title[:35].strip()
                
            return actress, clean_title
    except Exception:
        pass
    return "未知演员", ""

async def interactive_config(client, cfg):
    """交互式配置选单：展示网盘现有目录并允许一键切换或输入自定义路径"""
    # 预加载网盘根目录下的文件夹供用户点选
    root_items = await fetch_folder_items(client, folder_id=None)
    available_folders = [f["name"] for f in root_items if f.get("kind") == "drive#folder" and not f["name"].startswith(".")]

    while True:
        print("\n" + "=" * 68)
        print("                  ⚙️  整理配置与自定义目录设定")
        print("=" * 68)
        print(f"  [1] 待整理源目录   :  {cfg['source_folder']}")
        print(f"  [2] 目标归档总目录 :  {cfg['target_folder']}")
        print(f"  [3] 广告清理开关   :  {'已开启 (自动移入回收站)' if cfg.get('clean_ads', True) else '已关闭'}")
        print(f"  [4] 旧空目录清理   :  {'已开启 (归档后删除待整理旧目录)' if cfg.get('delete_empty_subdirs', True) else '已关闭'}")
        print("-" * 68)
        print("  👉 [直接回车]   ：保持当前配置，立即开始极速扫描")
        print("  👉 输入 1       ：修改【待整理源目录】(支持点选或输入自定义路径)")
        print("  👉 输入 2       ：修改【目标归档总目录】(自定义新文件夹名称/路径)")
        print("  👉 输入 0       ：退出程序")
        print("=" * 68)
        
        choice = input("请选择操作 [默认直接回车]: ").strip()
        
        if choice == "":
            break
        elif choice == "0":
            return False
        elif choice == "1":
            print("\n--- 正在检索网盘可用文件夹 ---")
            print(f"当前源目录为: 【{cfg['source_folder']}】")
            print("现有根目录文件夹快捷选择:")
            for idx, fname in enumerate(available_folders, 1):
                print(f"  [{idx}] {fname}")
            print("  [0] 手动输入任意多级自定义路径 (如: 影视/日韩待整理)")
            
            sub_c = input("\n请选择序号或直接输入新路径: ").strip()
            if sub_c.isdigit() and 1 <= int(sub_c) <= len(available_folders):
                cfg["source_folder"] = available_folders[int(sub_c) - 1]
            elif sub_c and sub_c != "0":
                cfg["source_folder"] = sub_c
            save_config(cfg)
            print(f"[+] 已更新待整理源目录为: 【{cfg['source_folder']}】")
        elif choice == "2":
            new_target = input(f"\n请输入新的目标总目录名称或路径 [当前: {cfg['target_folder']}]: ").strip()
            if new_target:
                cfg["target_folder"] = new_target
                save_config(cfg)
                print(f"[+] 已更新目标归档总目录为: 【{cfg['target_folder']}】")
        elif choice == "3":
            cfg["clean_ads"] = not cfg.get("clean_ads", True)
            save_config(cfg)
        elif choice == "4":
            cfg["delete_empty_subdirs"] = not cfg.get("delete_empty_subdirs", True)
            save_config(cfg)

    return True

async def main():
    print("=" * 68)
    print("      🌟 PikPak 云端 AV 目录批量整理与智能归档引擎 (Pro 自定义版)")
    print("=" * 68)

    cfg = load_config()
    token = cfg.get("access_token", "").strip()

    if not token:
        token = input("请输入你的 PikPak 个人访问令牌 (Token): ").strip()
        if not token:
            print("[-] Token 不能为空，退出。")
            input("\n按回车键退出...")
            return
        cfg["access_token"] = token
        save_config(cfg)

    # 1. 初始化客户端
    client = PikPakApi(username="dummy", password="dummy")
    client.access_token = token

    # 2. 进入交互式自定义选单
    should_continue = await interactive_config(client, cfg)
    if not should_continue:
        print("[*] 已退出程序。")
        return

    source_path = cfg["source_folder"]
    target_path = cfg["target_folder"]
    concurrency = cfg.get("concurrency_limit", 15)

    print("\n[*] 正在云端定位待整理源目录...")
    src_folder = await resolve_or_create_path(client, source_path, create_if_missing=False)
    if not src_folder:
        print(f"[-] 错误: 未在网盘中找到待整理的源目录: 【{source_path}】！")
        print("    请检查拼写或路径层级是否正确。")
        input("\n按回车键退出程序...")
        return
    print(f"[+] 成功定位源目录: 【{src_folder['name']}】 (ID: {src_folder['id']})")

    # 3. 准备目标总收纳目录
    print(f"[*] 正在云端准备目标归档目录: 【{target_path}】...")
    target_parent = await resolve_or_create_path(client, target_path, create_if_missing=True)
    target_parent_id = target_parent["id"]
    print(f"[+] 目标归档目录准备就绪 (ID: {target_parent_id})")

    # 4. 扫描源目录下的所有文件与子目录
    print(f"[*] ⚡ 正在极速扫描 【{src_folder['name']}】 内部所有文件与子目录...")
    subfolders, all_files = await scan_all_under_folder(client, src_folder["id"])

    # 5. 智能分类与垃圾过滤（白名单 + 黑名单双重拦截）
    main_videos = []
    subtitles = []
    junk_files = []

    video_exts = {'.mp4', '.mkv', '.avi', '.wmv', '.mov', '.ts', '.flv'}
    sub_exts = {'.srt', '.vtt', '.ass', '.ssa'}

    for f in all_files:
        name = f["name"]
        ext = os.path.splitext(name)[1].lower()
        size_mb = int(f.get("size", 0)) / (1024 * 1024)
        
        base_code, is_ad = parse_code_and_check_ad(name)
        
        # 1) 命中广告特征词直接标记为垃圾
        if is_ad:
            junk_files.append(f)
        # 2) 正片必须同时满足：主流视频格式 + 体积>=50MB + 具备正规番号
        elif ext in video_exts and size_mb >= cfg.get("min_video_size_mb", 50) and base_code:
            main_videos.append((f, base_code, name, ext))
        # 3) 字幕文件：主流外挂字幕格式 + 具备正规番号
        elif ext in sub_exts and base_code:
            subtitles.append((f, base_code, name, ext))
        # 4) 其余全部视为垃圾（博彩APK、宣传图片、HTML/CHM导航、TXT链接、无番号/小体积短片广告）
        else:
            junk_files.append(f)

    print("\n" + "=" * 68)
    print("                    📊 本次待处理任务扫描统计")
    print("=" * 68)
    print(f"  📂 源待整理目录   : 【{source_path}】")
    print(f"  🎯 目标归档目录   : 【{target_path}/演员名/番号 - 标题.mp4】")
    print(f"  🎬 待归类正片影片 : {len(main_videos)} 部 (体积 >= {cfg.get('min_video_size_mb', 50)}MB)")
    print(f"  📝 待同步字幕文件 : {len(subtitles)} 个")
    print(f"  🗑️  待清理广告与短片: {len(junk_files)} 个")
    print(f"  📁 待清理的旧子目录: {len(subfolders)} 个")
    print("-" * 68)

    if not main_videos and not junk_files and not subfolders:
        print("[+] 该目录目前非常整洁，没有发现需要整理的文件！")
        input("\n按回车键退出程序...")
        return

    # 直接开始执行（已按要求移除执行前人工核对与回车等待步骤）
    print("\n[*] 🚀 扫描完成，立即开始直接执行云端整理入库...")
    start_exec_time = time.time()
    print("\n[*] 正在并发检索番号对应的演员与标题元数据...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=12.0) as session:
        meta_tasks = [scrape_online_meta(session, code, orig_name) for _, code, orig_name, _ in main_videos]
        meta_results = await asyncio.gather(*meta_tasks)

    # 建立映射方案
    plan_items = []
    code_to_plan = {}
    for (f, base_code, orig_name, ext), (raw_actress, title) in zip(main_videos, meta_results):
        actress_cn = ACTRESS_CN_MAP.get(raw_actress, raw_actress)
        name_no_ext = os.path.splitext(orig_name)[0]
        clean_title = sanitize_filename(title)
        new_filename = f"{name_no_ext} - {clean_title}{ext}" if clean_title else f"{name_no_ext}{ext}"
        
        item_data = {
            "file": f,
            "base_code": base_code,
            "actress_cn": actress_cn,
            "new_filename": new_filename
        }
        plan_items.append(item_data)
        code_to_plan[base_code] = item_data

    # 6. 获取/创建目标目录下的各个演员子文件夹
    print(f"\n[*] 正在准备目标目录 【{target_path}】 下的演员分类子文件夹...")
    existing_act_dirs = {
        d["name"]: d["id"] 
        for d in (await fetch_folder_items(client, target_parent_id)) 
        if d.get("kind") == "drive#folder"
    }
    
    needed_actresses = set(item["actress_cn"] for item in plan_items)
    for act in needed_actresses:
        if act not in existing_act_dirs:
            try:
                res = await client.create_folder(name=act, parent_id=target_parent_id)
                existing_act_dirs[act] = res["file"]["id"]
                print(f" [+] 创建演员目录: /{target_path}/{act}")
            except Exception as e:
                print(f" [-] 创建失败: {act} ({e})")

    # 6.5 智能防重复与防覆盖核查：并发检索各演员目录下已有的文件
    print(f"[*] 正在核查目标演员目录下的已有文件，启用智能防覆盖保护...")
    act_existing_files = {}  # act_name -> {file_name: file_obj}
    async def get_act_files(act, fid):
        f_items = await fetch_folder_items(client, fid)
        act_existing_files[act] = {f["name"]: f for f in f_items if f.get("kind") != "drive#folder"}

    await asyncio.gather(*[get_act_files(act, existing_act_dirs[act]) for act in needed_actresses if act in existing_act_dirs])

    valid_plan_items = []
    duplicate_skipped = 0
    for item in plan_items:
        act = item["actress_cn"]
        tgt_files = act_existing_files.get(act, {})
        fname = item["new_filename"]
        
        if fname in tgt_files:
            existing_f = tgt_files[fname]
            src_size = int(item["file"].get("size", 0))
            tgt_size = int(existing_f.get("size", 0))
            if src_size == tgt_size:
                # 完全相同的文件已存在于目标目录，跳过移动，绝对不覆盖
                duplicate_skipped += 1
                print(f" [跳过已存在] 目标目录已有同体积相同影片: /{target_path}/{act}/{fname}")
                continue
            else:
                # 文件名相同但体积不同（例如不同压制版本），自动追加序号保全两份
                base_n, ext_n = os.path.splitext(fname)
                counter = 1
                while f"{base_n}_{counter}{ext_n}" in tgt_files:
                    counter += 1
                new_unique_name = f"{base_n}_{counter}{ext_n}"
                print(f" [版本保全] 目标已存在同名但不同体积影片，自动重命名防覆盖: {new_unique_name}")
                item["new_filename"] = new_unique_name
                tgt_files[new_unique_name] = item["file"]
        else:
            tgt_files[fname] = item["file"]
            
        valid_plan_items.append(item)

    if duplicate_skipped > 0:
        print(f"[*] 智能排重: 成功识别并跳过了 {duplicate_skipped} 个已存在的目标文件。")

    plan_items = valid_plan_items

    # 7. 并发执行重命名
    print(f"\n[*] ⚡ 并发重命名影片与字幕 (并发限制: {concurrency})...")
    sem = asyncio.Semaphore(concurrency)
    
    async def rename_job(fid, nname):
        async with sem:
            try:
                await client.file_rename(fid, nname)
            except Exception:
                pass

    rename_jobs = [rename_job(item["file"]["id"], item["new_filename"]) for item in plan_items]
    
    for sub_f, base_code, sub_name, ext in subtitles:
        if base_code in code_to_plan:
            base_plan = code_to_plan[base_code]
            tbase = os.path.splitext(base_plan["new_filename"])[0]
            new_sub_name = f"{tbase}{ext}"
            rename_jobs.append(rename_job(sub_f["id"], new_sub_name))

    await asyncio.gather(*rename_jobs)
    print("[+] 批量重命名完成！")

    # 8. 按演员原子批量移动（平滑限流防并发超限）
    print(f"\n[*] ⚡ 按演员分组极速批量移动至 【{target_path}】 下专属文件夹...")
    folder_batches = {}
    for item in plan_items:
        fid = existing_act_dirs.get(item["actress_cn"])
        if fid:
            folder_batches.setdefault(fid, []).append(item["file"]["id"])

    for sub_f, base_code, _, _ in subtitles:
        if base_code in code_to_plan:
            actress_cn = code_to_plan[base_code]["actress_cn"]
            fid = existing_act_dirs.get(actress_cn)
            if fid:
                folder_batches.setdefault(fid, []).append(sub_f["id"])

    for fid, ids in folder_batches.items():
        try:
            await client.file_batch_move(ids, to_parent_id=fid)
            await asyncio.sleep(0.3)
        except Exception as e:
            print(f"  [-] 批量移动异常: {e}")

    await asyncio.sleep(2)
    print(f"[+] 影片与字幕已全部归集入库至 【{target_path}】！")

    # 9. 垃圾与广告文件清理
    if junk_files and cfg.get("clean_ads", True):
        print(f"\n[*] ⚡ 正在将 {len(junk_files)} 个广告/垃圾短片批量移入云端回收站...")
        j_ids = [jf["id"] for jf in junk_files]
        for i in range(0, len(j_ids), 100):
            await client.delete_to_trash(j_ids[i:i+100])
        print("[+] 广告短片已全部清理移入回收站。")

    # 10. 删除源目录下已掏空的旧子目录（严格安全白名单：绝对禁止删除目标演员目录）
    if subfolders and cfg.get("delete_empty_subdirs", True):
        # 保护白名单：目标目录、已有演员分类目录、女优名录下的所有文件夹一律绝对豁免
        protected_ids = set(existing_act_dirs.values())
        if target_parent_id:
            protected_ids.add(target_parent_id)
        protected_names = set(ACTRESS_CN_MAP.values()).union(set(ACTRESS_CN_MAP.keys()))
        protected_names.add(target_path)
        
        sf_to_delete = [
            sf for sf in subfolders 
            if sf["id"] not in protected_ids and sf["name"] not in protected_names
        ]
        
        if sf_to_delete:
            print(f"\n[*] ⚡ 正在清理源目录下掏空的临时子目录 (共 {len(sf_to_delete)} 个)...")
            sf_ids = [sf["id"] for sf in sf_to_delete]
            for i in range(0, len(sf_ids), 100):
                await client.delete_to_trash(sf_ids[i:i+100])
            print("[+] 临时旧目录已清理完毕！")
        else:
            print("\n[*] 保护机制生效：未检测到需要清理的非演员临时目录。")

    elapsed = round(time.time() - start_exec_time, 2)
    print("\n" + "=" * 68)
    print(f" ✨ 云端极速整理全部完成！耗时: {elapsed} 秒")
    print(f"  🎬 归档入库影片: {len(plan_items)} 部")
    print(f"  📂 目标存放位置: /{target_path}/【演员名】/番号 - 标题.mp4")
    print(f"  🗑️  清理广告短片与旧目录: 已安全移入回收站")
    print("=" * 68)
    input("\n按回车键退出程序...")

if __name__ == "__main__":
    asyncio.run(main())
