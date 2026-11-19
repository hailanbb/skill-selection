#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram 频道 -> CloudDrive2 多 115 网盘定向云下载监控引擎 (v5 官方配额 + 自动跨云归并 + 断点续传)"""

import os
import re
import sys
import json
import signal
import asyncio
import datetime
from torrentool.api import Torrent
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from cd2_ops import CD2Client, run_merge, normalize_path

CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
DATA_DIR = os.path.join(BASE_DIR, "data")
RECORD_DIR = os.path.join(BASE_DIR, "records")
LOG_DIR = os.path.join(BASE_DIR, "logs")
SESSION_PATH = os.path.join(BASE_DIR, "user_session")

CHECKPOINT_FILE = os.path.join(DATA_DIR, "checkpoint.json")
QUOTA_FILE = os.path.join(DATA_DIR, "quota_status.json")
HISTORY_HASH_FILE = os.path.join(DATA_DIR, "downloaded_hashes.txt")
PAUSED_FLAG = os.path.join(DATA_DIR, "paused.flag")
MERGE_STATUS_FILE = os.path.join(DATA_DIR, "merge_status.json")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RECORD_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)


def log(msg: str):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def write_json_atomic(path: str, data: dict):
    tmp_path = f"{path}.tmp.{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def normalize_targets(cfg: dict) -> list:
    """兼容多 targets 结构，全面以官方配额自动感知驱动"""
    cd2 = cfg.get("clouddrive2", {})
    raw_targets = cd2.get("targets")
    targets = []

    if isinstance(raw_targets, list) and len(raw_targets) > 0:
        for idx, item in enumerate(raw_targets):
            if not isinstance(item, dict):
                continue
            save_folder = normalize_path(item.get("save_folder", ""))
            mount_path = normalize_path(item.get("mount_path", ""))
            if not mount_path and save_folder:
                parts = [p for p in save_folder.split("/") if p]
                mount_path = f"/{parts[0]}" if parts else "/"
            if not save_folder:
                save_folder = mount_path
            if not save_folder:
                continue
            name = (item.get("name") or "").strip() or mount_path.strip("/") or f"115-{idx + 1}"
            enabled = bool(item.get("enabled", True))
            targets.append({
                "name": name,
                "mount_path": mount_path,
                "save_folder": save_folder,
                "enabled": enabled,
            })
    else:
        legacy_folder = normalize_path(cd2.get("base_folder", ""))
        if legacy_folder:
            parts = [p for p in legacy_folder.split("/") if p]
            mount_path = f"/{parts[0]}" if parts else "/"
            targets.append({
                "name": mount_path.strip("/") or "115-1",
                "mount_path": mount_path,
                "save_folder": legacy_folder,
                "enabled": True,
            })
    return targets


# ==================== 全局状态与配置加载 ====================

config = {}
TG_CONF = {}
CD2_CONF = {}
TARGET_ACTORS = {}
TARGETS = []
MERGE_CONF = {}
QUOTA_PAUSE_PERCENT = 90
_config_mtime = 0.0

cd2_client = None
_cd2_server_connected = ""
_cd2_token_connected = ""

recent_actor_context = {"actors": [], "msg_id": 0}
_needs_catchup = False
_catchup_lock = asyncio.Lock()


def load_config(initial: bool = False):
    global config, TG_CONF, CD2_CONF, TARGET_ACTORS, TARGETS, MERGE_CONF, QUOTA_PAUSE_PERCENT, _config_mtime
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"未找到配置文件: {CONFIG_FILE}")
    mtime = os.path.getmtime(CONFIG_FILE)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        new_cfg = json.load(f)

    config = new_cfg
    TG_CONF = config.get("telegram", {})
    CD2_CONF = config.get("clouddrive2", {})
    TARGET_ACTORS = config.get("target_actors", {})
    TARGETS = normalize_targets(config)
    MERGE_CONF = CD2_CONF.get("merge", {"enabled": True, "wait_offline_max_minutes": 120})
    try:
        QUOTA_PAUSE_PERCENT = max(1, min(100, int(CD2_CONF.get("quota_pause_percent", 90))))
    except (TypeError, ValueError):
        QUOTA_PAUSE_PERCENT = 90

    _config_mtime = mtime

    if not initial:
        log(f"[配置热重载] 已加载最新配置，共 {len(TARGETS)} 个 115 目标 "
            f"({sum(1 for t in TARGETS if t['enabled'])} 个启用)，"
            f"官方配额停止阈值: {QUOTA_PAUSE_PERCENT}%，跨云归并: {'开启' if MERGE_CONF.get('enabled', True) else '关闭'}")
        if (
            CD2_CONF.get("server") != _cd2_server_connected
            or CD2_CONF.get("api_token") != _cd2_token_connected
        ):
            init_cd2()


def reload_config_if_changed():
    try:
        if os.path.exists(CONFIG_FILE):
            mtime = os.path.getmtime(CONFIG_FILE)
            if mtime != _config_mtime:
                load_config(initial=False)
                return True
    except Exception as e:
        log(f"[配置热重载失败] {e}")
    return False


def init_cd2():
    global cd2_client, _cd2_server_connected, _cd2_token_connected
    server = CD2_CONF.get("server", "127.0.0.1:19798")
    token = CD2_CONF.get("api_token", "")
    log(f"[CD2] 正在连接: {server}")
    cd2_client = CD2Client(server=server, token=token, logger=log)
    _cd2_server_connected = server
    _cd2_token_connected = token

    for idx, t in enumerate(TARGETS, 1):
        status_str = "启用" if t["enabled"] else "停用"
        log(f"[CD2] 115 目标 #{idx}: [{t['name']}] 挂载路径={t['mount_path']} | 保存目录={t['save_folder']} | 状态={status_str}")
        if t["enabled"]:
            cd2_client.ensure_folder_chain(t["save_folder"], t["mount_path"])
            q = cd2_client.get_quota(t["mount_path"])
            if q and q.get("total", 0) > 0:
                used_pct = round((q["used"] / q["total"] * 100), 1)
                log(f"      -> 官方配额自动感知: 总量 {q['total']} | 已用 {q['used']} | 剩余 {q['left']} "
                    f"(使用率 {used_pct}% | 达到 {QUOTA_PAUSE_PERCENT}% 停止换盘)")
            else:
                log("      -> 官方配额: 正在连接 CD2 实时探测中...")
    log("[CD2] 客户端初始化完成。")


# ==================== 配额检测与状态管理 ====================

def get_today_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d")


def format_msg_date(dt) -> str:
    """将 Telegram 消息的 UTC datetime 转为系统本地时间字符串"""
    if not dt:
        return ""
    try:
        local_dt = dt.astimezone()
        return local_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return dt.strftime("%Y-%m-%d %H:%M:%S")


def load_quota_status() -> dict:
    today = get_today_str()
    default_status = {"date": today, "counts": {}, "targets": {}, "updated_at": ""}
    if not os.path.exists(QUOTA_FILE):
        return default_status
    try:
        with open(QUOTA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return default_status

    if raw.get("date") != today:
        return default_status
    return raw


def check_target_quota(target: dict, counts: dict) -> dict:
    """
    检查单个目标的配额状态。优先读取 115 官方配额；若官方不可用则回退至本地下载计数。
    返回: {
        "available": bool,
        "official": bool,
        "total": int,
        "used": int,
        "left": int,
        "percent": float,
        "reason": str
    }
    """
    mount_path = target["mount_path"]
    save_folder = target["save_folder"]

    # 1. 尝试读取 115 官方离线配额
    if cd2_client is not None:
        try:
            off_q = cd2_client.get_quota(mount_path)
            if off_q and (off_q["total"] > 0 or off_q["left"] > 0):
                total = off_q["total"]
                used = off_q["used"]
                left = off_q["left"]
                pct = round((used / total * 100), 1) if total > 0 else 0.0
                paused = (pct >= QUOTA_PAUSE_PERCENT) or (left <= 0)
                reason = f"官方使用率 {pct}% >= {QUOTA_PAUSE_PERCENT}%" if (pct >= QUOTA_PAUSE_PERCENT) else ("官方剩余为 0" if left <= 0 else "正常")
                return {
                    "available": not paused,
                    "official": True,
                    "total": total,
                    "used": used,
                    "left": left,
                    "percent": pct,
                    "reason": reason,
                }
        except Exception as e:
            log(f"-> [CD2] 读取 {target['name']} 官方配额异常: {e}")

    # 2. 备用容错模式（仅在 CD2 接口临时未响应时使用）
    local_used = counts.get(save_folder, 0)
    return {
        "available": True,
        "official": False,
        "total": 0,
        "used": local_used,
        "left": 0,
        "percent": 0.0,
        "reason": "官方配额探测中",
    }


def get_available_targets() -> list:
    """
    按顺序检查启用的 115 目标，返回当前有可用配额的目标列表：
    [(target, quota_info), ...]
    同时更新 data/quota_status.json
    """
    status = load_quota_status()
    counts = status.get("counts", {})
    available = []
    targets_info = {}

    for t in TARGETS:
        if not t.get("enabled", True):
            continue
        q = check_target_quota(t, counts)
        targets_info[t["mount_path"]] = {
            "name": t["name"],
            "save_folder": t["save_folder"],
            "official": q["official"],
            "total": q["total"],
            "used": q["used"],
            "left": q["left"],
            "percent": q["percent"],
            "available": q["available"],
            "reason": q["reason"],
        }
        if q["available"]:
            available.append((t, q))

    status["date"] = get_today_str()
    status["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status["pause_percent_threshold"] = QUOTA_PAUSE_PERCENT
    status["targets"] = targets_info
    write_json_atomic(QUOTA_FILE, status)

    return available


def increment_local_target_count(target: dict):
    status = load_quota_status()
    counts = status.setdefault("counts", {})
    key = target["save_folder"]
    counts[key] = counts.get(key, 0) + 1
    write_json_atomic(QUOTA_FILE, status)
    return counts[key]


def mark_target_quota_full(target: dict):
    status = load_quota_status()
    counts = status.setdefault("counts", {})
    counts[target["save_folder"]] = target["daily_limit"]
    if "targets" in status and target["mount_path"] in status["targets"]:
        status["targets"][target["mount_path"]]["available"] = False
        status["targets"][target["mount_path"]]["reason"] = "推送返回配额耗尽"
    write_json_atomic(QUOTA_FILE, status)


def load_hashes() -> set:
    if os.path.exists(HISTORY_HASH_FILE):
        with open(HISTORY_HASH_FILE, "r", encoding="utf-8") as f:
            return set(line.strip().lower() for line in f if line.strip())
    return set()


downloaded_hashes = load_hashes()


def save_hash(info_hash: str):
    with open(HISTORY_HASH_FILE, "a", encoding="utf-8") as f:
        f.write(f"{info_hash.lower()}\n")


def append_daily_record(account_name: str, actor: str, title: str, save_path: str, magnet_link: str, post_time: str = ""):
    today = get_today_str()
    record_file = os.path.join(RECORD_DIR, f"{today}.md")
    time_str = datetime.datetime.now().strftime("%H:%M:%S")
    clean_post_time = post_time or "-"

    if not os.path.exists(record_file):
        with open(record_file, "w", encoding="utf-8") as f:
            f.write(f"# 115 云下载记录 - {today}\n\n")
            f.write("| 下载时间 | 消息发布时间 | 115账号 | 出演者 | 资源标题 | 目标目录 | 磁力链接 |\n")
            f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")

    clean_title = (title or "unknown").replace("\n", " ").replace("|", "-")[:50]
    with open(record_file, "a", encoding="utf-8") as f:
        f.write(f"| {time_str} | {clean_post_time} | {account_name} | {actor} | {clean_title} | `{save_path}` | [Magnet]({magnet_link}) |\n")


def load_checkpoint() -> dict:
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_scanned_id": 0}


def save_checkpoint(last_id: int):
    if last_id < 0:
        last_id = 0
    write_json_atomic(
        CHECKPOINT_FILE,
        {
            "last_scanned_id": last_id,
            "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    )


def is_paused() -> bool:
    return os.path.exists(PAUSED_FLAG)


async def wait_if_paused(context_label: str = "任务"):
    if not is_paused():
        return False
    log(f"[已暂停] {context_label} 检测到暂停指令，已挂起等待恢复...")
    while is_paused():
        reload_config_if_changed()
        await asyncio.sleep(1)
    reload_config_if_changed()
    log(f"[已恢复] {context_label} 收到恢复指令，继续执行！")
    return True


# ==================== 跨云归并与休眠恢复 ====================

async def trigger_auto_merge_if_needed():
    """
    当全部 115 账号配额均已用尽时触发跨云归并：
    将副盘 save_folder 下的全部内容移动至主盘 save_folder（允许覆盖），并刷新两边目录。
    """
    reload_config_if_changed()
    if not MERGE_CONF.get("enabled", True):
        log("[跨云归并] 当前配置已关闭自动归并，跳过。")
        return

    enabled_targets = [t for t in TARGETS if t.get("enabled", True)]
    if len(enabled_targets) < 2:
        log("[跨云归并] 启用的 115 账号少于 2 个，无需跨云归并。")
        return

    log("=" * 64)
    log("[跨云归并] 所有 115 账号配额均已达到上限，自动触发副盘向主盘归并流水线...")
    log("=" * 64)

    # 在单独线程中运行阻塞的 gRPC 归并调用，不阻塞 asyncio 事件循环
    loop = asyncio.get_running_loop()
    try:
        summary = await loop.run_in_executor(
            None,
            run_merge,
            cd2_client,
            TARGETS,
            MERGE_CONF,
            DATA_DIR,
            log,
        )
        log(f"[跨云归并] 归并流程结束：移动成功 {summary.get('moved', 0)} 项，失败 {summary.get('failed', 0)} 项。")
    except Exception as e:
        log(f"[跨云归并异常] {e}")


async def wait_until_quota_available():
    """
    所有账号无配额时先执行归并，然后休眠等待 115 配额恢复。
    期间定期轮询官方配额接口（恢复则立即自动唤醒继续下载），并支持配置热扩容与手动解除暂停。
    """
    await trigger_auto_merge_if_needed()

    log("[配额守护] 正在进入配额恢复守护模式（每 60 秒轮询官方配额，恢复后立即自动继续）...")
    check_interval = 60
    last_poll_ts = 0.0

    while True:
        await asyncio.sleep(5)
        if is_paused():
            await wait_if_paused("配额休眠")
        reload_config_if_changed()

        now = time.time()
        if now - last_poll_ts >= check_interval:
            last_poll_ts = now
            avail = get_available_targets()
            if avail:
                target_names = ", ".join(t["name"] for t, _ in avail)
                log(f"[配额守护] 发现可用 115 账号: {target_names}，立即唤醒继续任务！")
                return


# ==================== 核心匹配与推送 ====================

def match_actors(text: str) -> list:
    if not text:
        return []
    text_lower = text.lower()
    matched = []
    for main_name, aliases in TARGET_ACTORS.items():
        for alias in aliases:
            if alias and alias.lower() in text_lower:
                matched.append(main_name)
                break
    return matched


async def extract_torrent_info(message):
    magnet_link = None
    info_hash = None
    torrent_name = None

    is_torrent = False
    if message.file:
        file_name = getattr(message.file, "name", "") or ""
        mime_type = getattr(message.file, "mime_type", "") or ""
        if file_name.lower().endswith(".torrent") or mime_type == "application/x-bittorrent":
            is_torrent = True
            torrent_name = file_name or f"{message.id}.torrent"

    if is_torrent:
        temp_file = os.path.join(DATA_DIR, f"temp_{message.id}.torrent")
        try:
            await message.download_media(file=temp_file)
            torrent_obj = Torrent.from_file(temp_file)
            info_hash = torrent_obj.info_hash
            magnet_link = torrent_obj.magnet_link
        except Exception as err:
            log(f"-> 种子解析异常: {err}")
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)
    else:
        text = message.text or ""
        if "magnet:?xt=" in text:
            m = re.search(r"magnet:\?xt=urn:btih:[a-zA-Z0-9]+", text, re.IGNORECASE)
            if m:
                magnet_link = m.group(0)
                info_hash = magnet_link.split(":")[-1]
                torrent_name = text.strip().split("\n")[0][:40]

    return magnet_link, info_hash, torrent_name


def push_to_single_target(magnet_link: str, target: dict, primary_actor: str):
    """
    向单个 115 目标推送离线任务。
    返回: (status, actual_folder, err_msg)
      status: "OK" | "QUOTA" | "FAILED"
    """
    base_folder = target["save_folder"]
    mount_path = target["mount_path"]
    if CD2_CONF.get("split_by_actor", True) and primary_actor:
        target_folder = f"{base_folder}/{primary_actor}"
    else:
        target_folder = base_folder

    cd2_client.ensure_folder_chain(target_folder, mount_path)

    status, err_msg = cd2_client.add_offline(magnet_link, target_folder)
    if status == "OK":
        return "OK", target_folder, ""

    if status == "QUOTA":
        log(f"[CD2 限额提示] 目标 [{target['name']}] 触发 115 离线配额上限: {err_msg}")
        return "QUOTA", "", err_msg

    if status == "NOT_FOUND" and target_folder != base_folder:
        log(f"-> 目标 [{target['name']}] 出演者子目录不存在，回退至基础保存目录: {base_folder}")
        cd2_client.ensure_folder_chain(base_folder, mount_path)
        status2, err2 = cd2_client.add_offline(magnet_link, base_folder)
        if status2 == "OK":
            return "OK", base_folder, ""
        if status2 == "QUOTA":
            return "QUOTA", "", err2
        return "FAILED", "", err2

    return "FAILED", "", err_msg


async def execute_push(actors: list, magnet_link: str, info_hash: str, torrent_name: str, post_time: str = "", is_history: bool = False):
    """去重 -> 顺序选择有配额的 115 账号 -> 推送 -> 达到限额自动切换下一个账号"""
    reload_config_if_changed()

    if not (magnet_link and info_hash):
        return False

    if info_hash.lower() in downloaded_hashes:
        return False

    available = get_available_targets()
    if not available:
        return "QUOTA_REACHED"

    primary_actor = actors[0]
    label = "离线补课" if is_history else "实时新帖"

    for idx, (target, q_info) in enumerate(available):
        status, actual_folder, err_msg = push_to_single_target(magnet_link, target, primary_actor)
        if status == "OK":
            increment_local_target_count(target)
            q_mode = "官方" if q_info["official"] else "本地"
            log(
                f"-> [{label}][115 推送成功!] 账号: {target['name']} ({q_mode}已用: {q_info['percent']}%) | "
                f"发布时间: {post_time or '-'} | 演员: {', '.join(actors)} | 目录: {actual_folder} | 种子: {torrent_name}"
            )

            # 推送后更新配额状态，若该账号用尽且存在下一个账号，提示轮转
            new_avail = get_available_targets()
            still_avail = any(t["mount_path"] == target["mount_path"] for t, _ in new_avail)
            if not still_avail:
                remaining_names = [t["name"] for t, _ in new_avail]
                if remaining_names:
                    log(f"[配额轮转] 115 账号 [{target['name']}] 配额已达暂停阈值 ({QUOTA_PAUSE_PERCENT}%)，"
                        f"下条任务将自动轮转至 [{remaining_names[0]}]！")
                else:
                    log(f"[配额轮转] 115 账号 [{target['name']}] 配额已达阈值，所有启用账号配额均已用尽。")

            downloaded_hashes.add(info_hash.lower())
            save_hash(info_hash.lower())
            append_daily_record(
                target["name"],
                ",".join(actors),
                torrent_name or "unknown",
                actual_folder,
                magnet_link,
                post_time=post_time,
            )
            return True

        if status == "QUOTA":
            mark_target_quota_full(target)
            if idx + 1 < len(available):
                next_target = available[idx + 1][0]
                log(f"[配额轮转] 自动切换至下一个 115 账号: [{next_target['name']}] 重试当前种子...")
                continue
            return "QUOTA_REACHED"

        # 普通网络/接口临时错误，不标满额
        return False

    return "QUOTA_REACHED"


# ==================== Telegram 客户端与调度 ====================

client = None


async def handler_new_message(event):
    global _needs_catchup
    reload_config_if_changed()

    if is_paused():
        _needs_catchup = True
        return

    msg = event.message
    post_time_str = format_msg_date(msg.date)
    text_content = msg.text or msg.message or ""
    matched = match_actors(text_content)

    if matched:
        recent_actor_context["actors"] = matched
        recent_actor_context["msg_id"] = msg.id
        log(f"[实时新帖] 命中出演者: {', '.join(matched)} (消息 ID: {msg.id})")

    magnet_link, info_hash, torrent_name = await extract_torrent_info(msg)
    if magnet_link:
        target_actors = matched
        if not target_actors and recent_actor_context["actors"]:
            if msg.id - recent_actor_context["msg_id"] <= 3:
                target_actors = recent_actor_context["actors"]
        if target_actors:
            # 资源发布时间：严格取下载资源对应消息（含种子/磁链的本条消息）的发布时间
            resource_post_time = format_msg_date(msg.date)
            res = await execute_push(target_actors, magnet_link, info_hash, torrent_name, post_time=resource_post_time, is_history=False)
            if res == "QUOTA_REACHED":
                log(f"[配额熔断] 所有 115 账号配额均已满，实时新资源 [{torrent_name}] 已暂缓（断点保留，待配额恢复后自动补推）。")
                _needs_catchup = True
                rollback_id = min(msg.id, recent_actor_context["msg_id"] or msg.id) - 1
                cur_cp = load_checkpoint().get("last_scanned_id", 0)
                if rollback_id > cur_cp:
                    save_checkpoint(rollback_id)
                # 触发归并与休眠
                await wait_until_quota_available()
                return

    if not _needs_catchup:
        save_checkpoint(msg.id)


async def catchup_and_scan_messages():
    """断点续传与历史追赶引擎（支持官方配额轮转、满额自动归并、跨天自动唤醒）"""
    global _needs_catchup
    async with _catchup_lock:
        reload_config_if_changed()
        channel_name = TG_CONF["target_channel"]
        try:
            entity = await client.get_entity(channel_name)
        except Exception as e:
            log(f"[错误] 无法获取频道 @{channel_name}: {e}")
            return

        start_time_str = TG_CONF.get("history_start_time", "2025-01-01 00:00:00")
        start_dt = datetime.datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=datetime.timezone.utc
        )

        while True:
            await wait_if_paused("历史补扫")
            reload_config_if_changed()

            if not get_available_targets():
                await wait_until_quota_available()
                continue

            checkpoint = load_checkpoint()
            last_id = checkpoint.get("last_scanned_id", 0)

            if last_id > 0:
                log(f"[断点续传] 从消息断点 ID: {last_id} 之后开始补扫漏掉的消息...")
                msg_iterator = client.iter_messages(entity, min_id=last_id, reverse=True)
            else:
                log(f"[首次扫描] 未检测到断点，从 {start_dt} 开始正向扫描...")
                msg_iterator = client.iter_messages(entity, offset_date=start_dt, reverse=True)

            scanned_count = 0
            pending_actor = []
            pending_actor_msg_id = 0
            safe_checkpoint_id = last_id
            quota_hit = False
            has_new_messages = False

            try:
                async for msg in msg_iterator:
                    if is_paused():
                        save_checkpoint(safe_checkpoint_id)
                        await wait_if_paused("历史补扫")

                    has_new_messages = True
                    text_content = msg.text or msg.message or ""
                    matched = match_actors(text_content)

                    if matched:
                        pending_actor = matched
                        pending_actor_msg_id = msg.id

                    magnet_link, info_hash, torrent_name = await extract_torrent_info(msg)
                    if magnet_link:
                        active_actors = matched
                        if not active_actors and pending_actor:
                            if msg.id - pending_actor_msg_id <= 3:
                                active_actors = pending_actor
                        if active_actors:
                            # 资源发布时间：严格取下载资源对应消息（含种子/磁链的本条消息）的发布时间
                            resource_post_time = format_msg_date(msg.date)
                            res = await execute_push(
                                active_actors, magnet_link, info_hash, torrent_name, post_time=resource_post_time, is_history=True
                            )
                            if res == "QUOTA_REACHED":
                                quota_hit = True
                                pair_start = pending_actor_msg_id if (pending_actor and msg.id - pending_actor_msg_id <= 3) else msg.id
                                rollback_id = max(last_id, pair_start - 1)
                                save_checkpoint(rollback_id)
                                break
                            pending_actor = []
                            pending_actor_msg_id = 0

                    if not pending_actor or (msg.id - pending_actor_msg_id >= 3):
                        safe_checkpoint_id = msg.id

                    scanned_count += 1
                    if scanned_count % 20 == 0:
                        save_checkpoint(safe_checkpoint_id)
                    if scanned_count % 15 == 0:
                        await asyncio.sleep(0.3)

                if quota_hit:
                    await wait_until_quota_available()
                    continue

                if has_new_messages:
                    save_checkpoint(max(safe_checkpoint_id, msg.id))
                    log(f"[扫描完成] 已追齐 {scanned_count} 条消息，当前与频道最新动态完全同步！")
                else:
                    log("[扫描完成] 检查完毕，当前已处于最新状态！")
                _needs_catchup = False
                break

            except FloodWaitError as e:
                save_checkpoint(safe_checkpoint_id)
                log(f"[TG 限流] 需等待 {e.seconds} 秒，已保存断点，稍后自动续扫。")
                await asyncio.sleep(e.seconds + 2)
            except asyncio.CancelledError:
                save_checkpoint(safe_checkpoint_id)
                raise
            except Exception as e:
                save_checkpoint(safe_checkpoint_id)
                log(f"[扫描异常] {type(e).__name__}: {e}")
                break


async def state_watcher():
    """后台状态监控：配置热重载、暂停恢复补扫、跨天/恢复配额补扫"""
    global _needs_catchup
    was_paused = is_paused()
    while True:
        await asyncio.sleep(2)
        reload_config_if_changed()
        now_paused = is_paused()

        if now_paused and not was_paused:
            log("[状态变更] 任务已进入暂停状态（等待恢复指令）...")
        elif not now_paused and was_paused:
            log("[状态变更] 检测到恢复指令，正在检查暂停期间遗漏的消息...")
            _needs_catchup = True

        was_paused = now_paused

        if not now_paused and _needs_catchup and get_available_targets():
            await catchup_and_scan_messages()


async def main():
    global client
    load_config(initial=True)

    log("=" * 64)
    log(" TG -> 115 智能云下载服务 (v5 官方配额 + 自动跨云归并 + 断点续传)")
    log("=" * 64)

    if not TARGETS:
        log("[错误] config.json 中未配置任何 115 目标，请先通过管理菜单 [4 配置] 添加！")
        sys.exit(1)

    init_cd2()

    client = TelegramClient(SESSION_PATH, TG_CONF["api_id"], TG_CONF["api_hash"])
    client.add_event_handler(
        handler_new_message,
        events.NewMessage(chats=[TG_CONF["target_channel"]]),
    )

    await client.start()
    log("[Telegram] 登录认证成功！")

    loop = asyncio.get_running_loop()
    main_task = asyncio.current_task()
    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                loop.add_signal_handler(sig, main_task.cancel)
            except NotImplementedError:
                pass

    watcher_task = asyncio.create_task(state_watcher())
    try:
        while True:
            try:
                if not client.is_connected():
                    log("[Telegram] 正在连接服务器...")
                    await client.connect()
                    if not await client.is_user_authorized():
                        await client.start()
                    log("[Telegram] 登录认证成功！")

                # 每次连接或重连后，自动补扫期间遗漏的消息
                await catchup_and_scan_messages()
                log(f"[实时监控中] 正在持续监听 @{TG_CONF['target_channel']} 的最新资源...")

                await client.run_until_disconnected()
                log("[Telegram] 长连接已断开，3 秒后自动重连...")
                await asyncio.sleep(3)

            except (asyncio.CancelledError, KeyboardInterrupt):
                raise
            except Exception as conn_err:
                log(f"[网络抖动] Telegram 连接中断 ({conn_err})，5 秒后自动重连并同步断点...")
                await asyncio.sleep(5)
    except (asyncio.CancelledError, KeyboardInterrupt):
        cp = load_checkpoint()
        log(f"[安全退出] 任务已停止，当前断点消息 ID: {cp.get('last_scanned_id', 0)} 已保存，下次启动将从此处无缝继续。")
    finally:
        watcher_task.cancel()
        try:
            await watcher_task
        except asyncio.CancelledError:
            pass
        if client and client.is_connected():
            await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
