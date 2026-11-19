#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram 频道 -> CloudDrive2 多 115 网盘定向云下载监控引擎"""

import os
import re
import sys
import json
import signal
import asyncio
import datetime
import grpc
from torrentool.api import Torrent
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import clouddrive_pb2
import clouddrive_pb2_grpc

CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
DATA_DIR = os.path.join(BASE_DIR, "data")
RECORD_DIR = os.path.join(BASE_DIR, "records")
LOG_DIR = os.path.join(BASE_DIR, "logs")
SESSION_PATH = os.path.join(BASE_DIR, "user_session")

CHECKPOINT_FILE = os.path.join(DATA_DIR, "checkpoint.json")
QUOTA_FILE = os.path.join(DATA_DIR, "quota_status.json")
HISTORY_HASH_FILE = os.path.join(DATA_DIR, "downloaded_hashes.txt")
PAUSED_FLAG = os.path.join(DATA_DIR, "paused.flag")

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


def normalize_path(path: str) -> str:
    p = (path or "").strip().replace("\\", "/")
    if not p:
        return ""
    if not p.startswith("/"):
        p = "/" + p
    return p.rstrip("/") or "/"


def normalize_targets(cfg: dict) -> list:
    """兼容新版多 targets 与旧版 base_folder 单目标配置"""
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
            try:
                daily_limit = max(1, int(item.get("daily_limit", 500)))
            except (TypeError, ValueError):
                daily_limit = 500
            enabled = bool(item.get("enabled", True))
            targets.append({
                "name": name,
                "mount_path": mount_path,
                "save_folder": save_folder,
                "daily_limit": daily_limit,
                "enabled": enabled,
            })
    else:
        legacy_folder = normalize_path(cd2.get("base_folder", ""))
        legacy_limit = int(cfg.get("limits", {}).get("daily_download_limit", 500))
        if legacy_folder:
            parts = [p for p in legacy_folder.split("/") if p]
            mount_path = f"/{parts[0]}" if parts else "/"
            targets.append({
                "name": mount_path.strip("/") or "115-1",
                "mount_path": mount_path,
                "save_folder": legacy_folder,
                "daily_limit": max(1, legacy_limit),
                "enabled": True,
            })
    return targets


# ==================== 运行时全局状态 ====================

config = {}
TG_CONF = {}
CD2_CONF = {}
TARGET_ACTORS = {}
TARGETS = []
_config_mtime = 0.0

_cd2_stub = None
_cd2_metadata = None
_cd2_stub_class_name = "unknown"
_cd2_server_connected = ""
_cd2_token_connected = ""
_known_folders = set()
_create_folder_rpc_name = None
_create_folder_req_cls = None

recent_actor_context = {"actors": [], "msg_id": 0}
_needs_catchup = False
_catchup_lock = asyncio.Lock()


def load_config(initial: bool = False):
    global config, TG_CONF, CD2_CONF, TARGET_ACTORS, TARGETS, _config_mtime
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
    _config_mtime = mtime

    if not initial:
        log(f"[配置热重载] 已加载最新配置，共 {len(TARGETS)} 个 115 目标，"
            f"{sum(1 for t in TARGETS if t['enabled'])} 个启用。")
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


# ==================== CD2 gRPC 连接与目录管理 ====================

def init_cd2():
    global _cd2_stub, _cd2_metadata, _cd2_stub_class_name
    global _create_folder_rpc_name, _create_folder_req_cls
    global _cd2_server_connected, _cd2_token_connected

    server = CD2_CONF["server"]
    token = CD2_CONF["api_token"]
    log(f"[CD2] 正在连接: {server}")
    channel = grpc.insecure_channel(server)
    _cd2_metadata = [("authorization", f"Bearer {token}")]

    stub_cls = None
    for candidate in ["CloudDriveFileSrvStub", "CloudDriveServiceStub"]:
        stub_cls = getattr(clouddrive_pb2_grpc, candidate, None)
        if stub_cls is not None:
            _cd2_stub_class_name = candidate
            break

    if stub_cls is None:
        for attr_name in dir(clouddrive_pb2_grpc):
            if attr_name.endswith("Stub"):
                stub_cls = getattr(clouddrive_pb2_grpc, attr_name)
                _cd2_stub_class_name = attr_name
                break

    if stub_cls is None:
        raise RuntimeError("[致命错误] 未在 clouddrive_pb2_grpc 中找到 gRPC Stub 类！")

    _cd2_stub = stub_cls(channel)
    _cd2_server_connected = server
    _cd2_token_connected = token
    _known_folders.clear()

    log(f"[CD2] Stub 类: {_cd2_stub_class_name}")

    for req_name, rpc_name in [
        ("CreateFolderRequest", "CreateFolder"),
        ("CreateDirectoryRequest", "CreateDirectory"),
        ("MkDirRequest", "MkDir"),
    ]:
        req_cls = getattr(clouddrive_pb2, req_name, None)
        rpc_method = getattr(_cd2_stub, rpc_name, None)
        if req_cls is not None and rpc_method is not None:
            _create_folder_req_cls = req_cls
            _create_folder_rpc_name = rpc_name
            log(f"[CD2] 文件夹创建接口: {rpc_name}({req_name})")
            break

    for idx, t in enumerate(TARGETS, 1):
        status_str = "启用" if t["enabled"] else "停用"
        log(f"[CD2] 115 目标 #{idx}: [{t['name']}] 路径名={t['mount_path']} | "
            f"保存目录={t['save_folder']} | 每日限额={t['daily_limit']} | 状态={status_str}")
    log("[CD2] 初始化完成。")


def try_create_folder(folder_path: str) -> bool:
    folder_path = normalize_path(folder_path)
    if folder_path in _known_folders:
        return True
    if _create_folder_rpc_name is None or _create_folder_req_cls is None:
        return False

    try:
        rpc_method = getattr(_cd2_stub, _create_folder_rpc_name)
        parent = folder_path.rsplit("/", 1)[0] if "/" in folder_path else "/"
        if not parent:
            parent = "/"
        name = folder_path.rsplit("/", 1)[-1]
        request = _create_folder_req_cls(parentPath=parent, folderName=name)
        rpc_method(request, metadata=_cd2_metadata)
        _known_folders.add(folder_path)
        log(f"-> [CD2] 成功创建目录: {folder_path}")
        return True
    except grpc.RpcError as e:
        code = e.code()
        details = (e.details() or "").lower()
        if code == grpc.StatusCode.ALREADY_EXISTS or "already exists" in details or "已存在" in details:
            _known_folders.add(folder_path)
            return True
        log(f"-> [CD2] 目录创建返回: {code} - {e.details()}")
        return False
    except Exception as e:
        log(f"-> [CD2] 目录创建异常: {e}")
        return False


def ensure_folder_chain(folder_path: str, mount_path: str):
    """确保从 mount_path 到 folder_path 的每一级子目录都存在"""
    folder_path = normalize_path(folder_path)
    mount_path = normalize_path(mount_path)
    if folder_path in _known_folders:
        return

    if mount_path and folder_path.startswith(mount_path + "/"):
        rel = folder_path[len(mount_path) + 1:]
        cur = mount_path
        for part in [p for p in rel.split("/") if p]:
            cur = f"{cur}/{part}"
            if cur not in _known_folders:
                try_create_folder(cur)
    else:
        try_create_folder(folder_path)


def is_quota_error_details(details: str) -> bool:
    d = (details or "").lower()
    keywords = ["配额", "quota", "上限", "limit", "exceeded", "次数", "已满"]
    return any(k in d for k in keywords)


def push_to_single_target(magnet_link: str, target: dict, primary_actor: str):
    """
    向单个 115 目标推送离线任务。
    返回: (status, actual_folder)
      status: "OK" | "QUOTA_ERROR" | "FAILED"
    """
    base_folder = target["save_folder"]
    mount_path = target["mount_path"]
    if CD2_CONF.get("split_by_actor", True) and primary_actor:
        target_folder = f"{base_folder}/{primary_actor}"
    else:
        target_folder = base_folder

    if target_folder not in _known_folders:
        ensure_folder_chain(target_folder, mount_path)

    try:
        request = clouddrive_pb2.AddOfflineFileRequest(
            urls=magnet_link,
            toFolder=target_folder,
        )
        _cd2_stub.AddOfflineFiles(request, metadata=_cd2_metadata)
        _known_folders.add(target_folder)
        return "OK", target_folder
    except grpc.RpcError as e:
        code = e.code()
        details = e.details() or ""
        if is_quota_error_details(details):
            log(f"[CD2 限额提示] 目标 [{target['name']}] 疑似触发 115 离线限额: {code} - {details}")
            return "QUOTA_ERROR", ""
        if code == grpc.StatusCode.NOT_FOUND and target_folder != base_folder:
            log(f"-> 目标 [{target['name']}] 子目录不可用，回退至保存目录: {base_folder}")
            ensure_folder_chain(base_folder, mount_path)
            try:
                request2 = clouddrive_pb2.AddOfflineFileRequest(
                    urls=magnet_link,
                    toFolder=base_folder,
                )
                _cd2_stub.AddOfflineFiles(request2, metadata=_cd2_metadata)
                _known_folders.add(base_folder)
                return "OK", base_folder
            except grpc.RpcError as e2:
                details2 = e2.details() or ""
                if is_quota_error_details(details2):
                    log(f"[CD2 限额提示] 目标 [{target['name']}] 疑似触发 115 离线限额: {e2.code()} - {details2}")
                    return "QUOTA_ERROR", ""
                log(f"[CD2 失败] 目标 [{target['name']}]: {e2.code()} - {details2}")
                return "FAILED", ""
        log(f"[CD2 失败] 目标 [{target['name']}]: {code} - {details}")
        return "FAILED", ""
    except Exception as e:
        log(f"[CD2 推送异常] 目标 [{target['name']}]: {e}")
        return "FAILED", ""


# ==================== 多 115 配额轮转与状态管理 ====================

def get_today_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d")


def load_quota_status() -> dict:
    today = get_today_str()
    default_status = {"date": today, "counts": {}}
    if not os.path.exists(QUOTA_FILE):
        return default_status
    try:
        with open(QUOTA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return default_status

    if raw.get("date") != today:
        return default_status

    # 兼容旧版单 count 结构
    if "counts" in raw and isinstance(raw["counts"], dict):
        return {"date": today, "counts": {normalize_path(k): int(v) for k, v in raw["counts"].items()}}
    if "count" in raw and TARGETS:
        first_key = TARGETS[0]["save_folder"]
        return {"date": today, "counts": {first_key: int(raw.get("count", 0))}}
    return default_status


def save_quota_status(status: dict):
    write_json_atomic(QUOTA_FILE, status)


def get_available_targets() -> list:
    """按配置顺序返回今天还有剩余限额的启用 115 目标列表"""
    status = load_quota_status()
    counts = status.get("counts", {})
    available = []
    for t in TARGETS:
        if not t.get("enabled", True):
            continue
        used = counts.get(t["save_folder"], 0)
        if used < t["daily_limit"]:
            available.append((t, used))
    return available


def increment_target_quota(target: dict, set_full: bool = False) -> int:
    status = load_quota_status()
    counts = status.setdefault("counts", {})
    key = target["save_folder"]
    if set_full:
        counts[key] = target["daily_limit"]
    else:
        counts[key] = counts.get(key, 0) + 1
    save_quota_status(status)
    return counts[key]


def load_hashes() -> set:
    if os.path.exists(HISTORY_HASH_FILE):
        with open(HISTORY_HASH_FILE, "r", encoding="utf-8") as f:
            return set(line.strip().lower() for line in f if line.strip())
    return set()


downloaded_hashes = load_hashes()


def save_hash(info_hash: str):
    with open(HISTORY_HASH_FILE, "a", encoding="utf-8") as f:
        f.write(f"{info_hash.lower()}\n")


def append_daily_record(account_name: str, actor: str, title: str, save_path: str, magnet_link: str):
    today = get_today_str()
    record_file = os.path.join(RECORD_DIR, f"{today}.md")
    time_str = datetime.datetime.now().strftime("%H:%M:%S")

    if not os.path.exists(record_file):
        with open(record_file, "w", encoding="utf-8") as f:
            f.write(f"# 115 云下载记录 - {today}\n\n")
            f.write("| 时间 | 115账号 | 出演者 | 资源标题 | 目标目录 | 磁力链接 |\n")
            f.write("| :--- | :--- | :--- | :--- | :--- | :--- |\n")

    clean_title = (title or "unknown").replace("\n", " ").replace("|", "-")[:50]
    with open(record_file, "a", encoding="utf-8") as f:
        f.write(f"| {time_str} | {account_name} | {actor} | {clean_title} | `{save_path}` | [Magnet]({magnet_link}) |\n")


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


async def wait_until_quota_available():
    """所有 115 达到当日上限后休眠；期间每隔 5 秒检测配置变更或跨天，支持动态唤醒"""
    status = load_quota_status()
    counts = status.get("counts", {})
    summary = ", ".join(
        f"{t['name']}({counts.get(t['save_folder'], 0)}/{t['daily_limit']})"
        for t in TARGETS
        if t.get("enabled", True)
    )
    now = datetime.datetime.now()
    tomorrow = (now + datetime.timedelta(days=1)).replace(hour=0, minute=1, second=0, microsecond=0)
    sleep_seconds = max(10, int((tomorrow - now).total_seconds()))
    hours = sleep_seconds // 3600
    minutes = (sleep_seconds % 3600) // 60

    log(f"[配额守护] 所有启用的 115 今日限额均已用尽: {summary}")
    log(f"[配额守护] 预计休眠 {hours} 小时 {minutes} 分钟至明日 00:01 自动唤醒（期间若修改配置扩容也会立即唤醒）...")

    while True:
        await asyncio.sleep(5)
        if is_paused():
            await wait_if_paused("配额休眠")
        reload_config_if_changed()
        if get_available_targets():
            log("[配额守护] 检测到可用 115 配额（已跨天或配置已扩容），立即唤醒恢复！")
            return


# ==================== 核心匹配与轮转推送 ====================

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


async def execute_push(actors: list, magnet_link: str, info_hash: str, torrent_name: str, is_history: bool = False):
    """去重 -> 顺序选择有额度的 115 账号 -> 推送 -> 失败自动切下一个账号"""
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

    for idx, (target, _used_before) in enumerate(available):
        status, actual_folder = push_to_single_target(magnet_link, target, primary_actor)
        if status == "OK":
            new_count = increment_target_quota(target, set_full=False)
            log(
                f"-> [{label}][115 推送成功!] 账号: {target['name']} ({new_count}/{target['daily_limit']}) | "
                f"演员: {', '.join(actors)} | 目录: {actual_folder} | 种子: {torrent_name}"
            )
            if new_count >= target["daily_limit"]:
                remaining = [t["name"] for t, _ in get_available_targets()]
                if remaining:
                    log(f"[配额轮转] 115 账号 [{target['name']}] 已达今日上限 {target['daily_limit']}，"
                        f"下一条任务将自动切换至 [{remaining[0]}]！")
                else:
                    log(f"[配额轮转] 115 账号 [{target['name']}] 已达今日上限 {target['daily_limit']}，"
                        f"全部启用账号今日配额已满。")

            downloaded_hashes.add(info_hash.lower())
            save_hash(info_hash.lower())
            append_daily_record(
                target["name"],
                ",".join(actors),
                torrent_name or "unknown",
                actual_folder,
                magnet_link,
            )
            return True

        if status == "QUOTA_ERROR":
            increment_target_quota(target, set_full=True)
            if idx + 1 < len(available):
                next_target = available[idx + 1][0]
                log(f"[配额轮转] 自动切换至下一个 115 账号: [{next_target['name']}] 重试当前种子...")
                continue
            return "QUOTA_REACHED"

        # 普通网络/接口错误，不误标限额
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
            res = await execute_push(target_actors, magnet_link, info_hash, torrent_name, is_history=False)
            if res == "QUOTA_REACHED":
                log(f"[配额熔断] 所有 115 今日限额均已满，实时新资源 [{torrent_name}] 已暂缓推送（断点保留，明日或扩容后自动补推）。")
                _needs_catchup = True
                # 不推进断点到当前消息，保留在本次资源之前
                rollback_id = min(msg.id, recent_actor_context["msg_id"] or msg.id) - 1
                cur_cp = load_checkpoint().get("last_scanned_id", 0)
                if rollback_id > cur_cp:
                    save_checkpoint(rollback_id)
                return

    # 正常处理完毕后推进断点
    if not _needs_catchup:
        save_checkpoint(msg.id)


async def catchup_and_scan_messages():
    """断点续传与历史追赶引擎（支持多 115 轮转、暂停恢复、满额跨天自动唤醒）"""
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
                            res = await execute_push(
                                active_actors, magnet_link, info_hash, torrent_name, is_history=True
                            )
                            if res == "QUOTA_REACHED":
                                quota_hit = True
                                # 回退到当前资源组合之前，避免明日重启漏掉本条种子
                                pair_start = pending_actor_msg_id if (pending_actor and msg.id - pending_actor_msg_id <= 3) else msg.id
                                rollback_id = max(last_id, pair_start - 1)
                                save_checkpoint(rollback_id)
                                break
                            # 推送处理完成后清理 pending
                            pending_actor = []
                            pending_actor_msg_id = 0

                    # 若当前不处于“刚命中演员等待紧邻种子”的悬空状态，则可安全推进断点
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
    """后台状态监控：处理配置热更新、暂停后恢复补扫、跨天配额恢复补扫"""
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
    log(" TG -> 115 多账号轮转定向云下载服务 (v4 多115 + 断点续传 + 热重载)")
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

    # 注册 POSIX SIGTERM 优雅退出
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
        await catchup_and_scan_messages()
        log(f"[实时监控中] 正在持续监听 @{TG_CONF['target_channel']} 的最新资源...")
        await client.run_until_disconnected()
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
