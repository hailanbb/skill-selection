#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TG -> 115 多账号云下载交互式管理面板 (Ubuntu CLI v5 官方配额 + 跨云归并)"""

import os
import sys
import json
import time
import shutil
import signal
import getpass
import datetime
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from cd2_ops import CD2Client, run_merge, normalize_path as cd2_norm_path
except ImportError:
    CD2Client = None
    run_merge = None
    cd2_norm_path = None

try:
    from update_top_actors import update_actors_file
except ImportError:
    update_actors_file = None

CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
CONFIG_EXAMPLE = os.path.join(BASE_DIR, "config.example.json")
ACTORS_FILE = os.path.join(BASE_DIR, "actors.json")
ACTORS_TXT_FILE = os.path.join(BASE_DIR, "actors.txt")
ACTORS_EXAMPLE = os.path.join(BASE_DIR, "actors.example.json")
MONITOR_SCRIPT = os.path.join(BASE_DIR, "monitor.py")
DATA_DIR = os.path.join(BASE_DIR, "data")
RECORD_DIR = os.path.join(BASE_DIR, "records")
LOG_DIR = os.path.join(BASE_DIR, "logs")

PID_FILE = os.path.join(DATA_DIR, "monitor.pid")
PAUSED_FLAG = os.path.join(DATA_DIR, "paused.flag")
QUOTA_FILE = os.path.join(DATA_DIR, "quota_status.json")
CHECKPOINT_FILE = os.path.join(DATA_DIR, "checkpoint.json")
MERGE_STATUS_FILE = os.path.join(DATA_DIR, "merge_status.json")
LOG_FILE = os.path.join(LOG_DIR, "monitor.log")
SESSION_FILE = os.path.join(BASE_DIR, "user_session.session")

SERVICE_NAME = "tg115"
SERVICE_PATH = f"/etc/systemd/system/{SERVICE_NAME}.service"

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RECORD_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)


# ==================== 工具函数 ====================

def normalize_path(path: str) -> str:
    p = (path or "").strip().replace("\\", "/")
    if not p:
        return ""
    if not p.startswith("/"):
        p = "/" + p
    return p.rstrip("/") or "/"


def get_python_bin() -> str:
    venv_py = os.path.join(BASE_DIR, "venv", "bin", "python3")
    if os.path.isfile(venv_py) and os.access(venv_py, os.X_OK):
        return venv_py
    return sys.executable


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def run_cmd(cmd: list, use_sudo: bool = False, capture: bool = True, input_text: str = None):
    full_cmd = list(cmd)
    if use_sudo and is_linux() and not is_root():
        full_cmd = ["sudo"] + full_cmd
    try:
        return subprocess.run(
            full_cmd,
            input=input_text,
            capture_output=capture,
            text=True,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(full_cmd, 127, "", f"命令不存在: {full_cmd[0]}")


def write_json_atomic(path: str, data: dict):
    tmp_path = f"{path}.tmp.{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def pause_prompt(msg: str = "按回车键继续..."):
    try:
        input(f"\n{msg}")
    except (EOFError, KeyboardInterrupt):
        pass


# ==================== 配置读写与规范化 ====================

def ensure_config_exists() -> bool:
    if os.path.exists(CONFIG_FILE):
        return True
    if os.path.exists(CONFIG_EXAMPLE):
        shutil.copyfile(CONFIG_EXAMPLE, CONFIG_FILE)
        print(f"[提示] 已从模板初始化配置文件: {CONFIG_FILE}")
        return True
    print(f"[错误] 缺少 {CONFIG_FILE} 与 {CONFIG_EXAMPLE}")
    return False


def load_config() -> dict:
    if not ensure_config_exists():
        return {"telegram": {}, "clouddrive2": {"targets": []}, "target_actors": {}}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    cd2 = cfg.setdefault("clouddrive2", {})
    if "targets" not in cd2 or not isinstance(cd2["targets"], list):
        targets = []
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
        cd2["targets"] = targets

    if "quota_pause_percent" not in cd2:
        cd2["quota_pause_percent"] = 90
    if "merge" not in cd2 or not isinstance(cd2["merge"], dict):
        cd2["merge"] = {"enabled": True, "wait_offline_max_minutes": 120}

    return cfg


def save_config(cfg: dict):
    cfg.get("clouddrive2", {}).pop("base_folder", None)
    cfg.pop("limits", None)
    write_json_atomic(CONFIG_FILE, cfg)


# ==================== 进程与 Systemd 状态检测 ====================

def systemd_available() -> bool:
    return is_linux() and shutil.which("systemctl") is not None


def is_systemd_installed() -> bool:
    return systemd_available() and os.path.exists(SERVICE_PATH)


def is_systemd_active() -> bool:
    if not systemd_available():
        return False
    res = run_cmd(["systemctl", "is-active", SERVICE_NAME])
    return res.returncode == 0 and res.stdout.strip() == "active"


def is_systemd_enabled() -> bool:
    if not systemd_available():
        return False
    res = run_cmd(["systemctl", "is-enabled", SERVICE_NAME])
    return res.returncode == 0 and res.stdout.strip() == "enabled"


def get_systemd_main_pid() -> int:
    if not is_systemd_active():
        return 0
    res = run_cmd(["systemctl", "show", "-p", "MainPID", "--value", SERVICE_NAME])
    try:
        return int(res.stdout.strip())
    except Exception:
        return 0


def is_monitor_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if is_linux():
        cmdline_file = f"/proc/{pid}/cmdline"
        if not os.path.exists(cmdline_file):
            return False
        try:
            with open(cmdline_file, "rb") as f:
                raw = f.read().decode("utf-8", errors="ignore")
            return "monitor.py" in raw
        except Exception:
            pass
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def get_standalone_pid() -> int:
    if not os.path.exists(PID_FILE):
        return 0
    try:
        with open(PID_FILE, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
    except Exception:
        return 0
    if is_monitor_pid_alive(pid):
        return pid
    try:
        os.remove(PID_FILE)
    except OSError:
        pass
    return 0


def get_runtime_state() -> dict:
    sys_active = is_systemd_active()
    sys_enabled = is_systemd_enabled()
    standalone_pid = get_standalone_pid()
    paused = os.path.exists(PAUSED_FLAG)

    if sys_active:
        mode = "systemd"
        pid = get_systemd_main_pid()
        running = True
    elif standalone_pid > 0:
        mode = "standalone"
        pid = standalone_pid
        running = True
    else:
        mode = "stopped"
        pid = 0
        running = False

    return {
        "running": running,
        "paused": running and paused,
        "mode": mode,
        "pid": pid,
        "systemd_installed": is_systemd_installed(),
        "systemd_enabled": sys_enabled,
        "systemd_active": sys_active,
    }


def load_quota_info() -> dict:
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(QUOTA_FILE):
        try:
            with open(QUOTA_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if raw.get("date") == today:
                return raw
        except Exception:
            pass
    return {"date": today, "counts": {}, "targets": {}, "updated_at": ""}


def load_checkpoint() -> dict:
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_scanned_id": 0, "updated_at": "-"}


def load_merge_status() -> dict:
    if os.path.exists(MERGE_STATUS_FILE):
        try:
            with open(MERGE_STATUS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def render_progress_bar(used: int, limit: int, width: int = 16) -> str:
    if limit <= 0:
        return "[" + "-" * width + "] 0%"
    ratio = min(1.0, max(0.0, used / limit))
    filled = int(round(ratio * width))
    pct = int(round(ratio * 100))
    return f"[{'#' * filled}{'.' * (width - filled)}] {pct:3d}%"


# ==================== 核心动作: 1 启动 / 2 暂停 / 3 停止 ====================

def stop_standalone_process() -> bool:
    pid = get_standalone_pid()
    if pid <= 0:
        return True
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    for _ in range(20):
        if not is_monitor_pid_alive(pid):
            break
        time.sleep(0.5)
    if is_monitor_pid_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
    return True


def ensure_telegram_session() -> bool:
    if os.path.exists(SESSION_FILE):
        return True
    print("\n[首次运行提示] 未检测到 Telegram 登录凭证 (user_session.session)。")
    print("首次启动需要在前台输入手机号与验证码完成登录认证。")
    ans = input("是否现在进入前台登录认证？(Y/n): ").strip().lower()
    if ans == "n":
        return False
    print("\n>>> 正在启动前台登录（认证成功并看到开始扫描后，按 Ctrl+C 返回菜单即可转后台运行）...\n")
    try:
        subprocess.run([get_python_bin(), MONITOR_SCRIPT], cwd=BASE_DIR)
    except KeyboardInterrupt:
        print("\n[提示] 已退出前台运行。")
    return os.path.exists(SESSION_FILE)


def action_start():
    if not ensure_config_exists():
        pause_prompt()
        return

    cfg = load_config()
    targets = cfg.get("clouddrive2", {}).get("targets", [])
    if not targets or not any(t.get("enabled", True) for t in targets):
        print("\n[错误] 没有已启用的 115 目标，请先进入 [4 配置] 添加或启用至少一个 115 目标！")
        pause_prompt()
        return

    state = get_runtime_state()
    if state["running"]:
        if state["paused"]:
            try:
                os.remove(PAUSED_FLAG)
            except OSError:
                pass
            print(f"\n[成功] 已解除暂停，任务已恢复运行！（模式: {state['mode']}, PID: {state['pid']}）")
        else:
            print(f"\n[提示] 任务当前已在运行中（模式: {state['mode']}, PID: {state['pid']}），无需重复启动。")
        pause_prompt()
        return

    if os.path.exists(PAUSED_FLAG):
        try:
            os.remove(PAUSED_FLAG)
        except OSError:
            pass

    if not ensure_telegram_session():
        print("\n[提示] 尚未完成 Telegram 登录认证，取消后台启动。")
        pause_prompt()
        return

    if state["systemd_installed"] and state["systemd_enabled"]:
        print("\n[*] 检测到已开启守护进程，正在通过 systemd 启动...")
        res = run_cmd(["systemctl", "start", SERVICE_NAME], use_sudo=True)
        if res.returncode == 0:
            time.sleep(1)
            new_state = get_runtime_state()
            print(f"[成功] 守护进程已启动！（PID: {new_state['pid']}）")
        else:
            print(f"[失败] systemd 启动失败: {res.stderr.strip()}")
        pause_prompt()
        return

    print("\n[*] 正在后台启动监控引擎...")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["LANG"] = "C.UTF-8"

    log_fp = open(LOG_FILE, "a", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            [get_python_bin(), MONITOR_SCRIPT],
            cwd=BASE_DIR,
            stdin=subprocess.DEVNULL,
            stdout=log_fp,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
        )
    finally:
        log_fp.close()

    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(proc.pid))

    time.sleep(1.5)
    if proc.poll() is None and is_monitor_pid_alive(proc.pid):
        print(f"[成功] 任务已在后台启动！（PID: {proc.pid}）")
        print(f"[提示] 日志文件: {LOG_FILE}，可选择主菜单 [5 实时任务查看] 观察实时输出。")
    else:
        print("[失败] 进程启动后异常退出，请查看最近日志：")
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-20:]
            print("".join(lines))
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    pause_prompt()


def action_pause():
    state = get_runtime_state()
    if not state["running"]:
        print("\n[提示] 任务当前未运行，无需暂停。")
        pause_prompt()
        return
    if state["paused"]:
        print("\n[提示] 任务已处于暂停状态。选择 [1 启动] 可立即恢复运行。")
        pause_prompt()
        return

    with open(PAUSED_FLAG, "w", encoding="utf-8") as f:
        f.write(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print(f"\n[成功] 已发送暂停指令！（模式: {state['mode']}, PID: {state['pid']}）")
    print("[说明] 任务会保留当前断点并挂起推送；暂停期间产生的新消息将在选择 [1 启动] 恢复后自动补扫。")
    pause_prompt()


def action_stop():
    state = get_runtime_state()
    if os.path.exists(PAUSED_FLAG):
        try:
            os.remove(PAUSED_FLAG)
        except OSError:
            pass

    if not state["running"]:
        print("\n[提示] 任务当前未运行。")
        pause_prompt()
        return

    print(f"\n[*] 正在安全停止任务（模式: {state['mode']}, PID: {state['pid']}），等待断点保存...")
    if state["systemd_active"]:
        res = run_cmd(["systemctl", "stop", SERVICE_NAME], use_sudo=True)
        if res.returncode != 0:
            print(f"[警告] systemctl stop 返回异常: {res.stderr.strip()}")
    stop_standalone_process()

    cp = load_checkpoint()
    print(f"[成功] 任务已安全停止！当前断点消息 ID: {cp.get('last_scanned_id', 0)}（下次启动将从此断点无缝续传）。")
    pause_prompt()


# ==================== 核心动作: 4 配置管理 ====================

def print_targets_table(cfg: dict):
    targets = cfg.get("clouddrive2", {}).get("targets", [])
    print("\n当前已配置的 115 云存储目标（按顺序自动轮转，配额由 115 官方自动感知）：")
    if not targets:
        print("  (暂无配置，请选择 1 新增)")
        return
    for idx, t in enumerate(targets, 1):
        status = "启用" if t.get("enabled", True) else "停用"
        role = "主盘" if idx == 1 else "副盘"
        print(
            f"  [{idx}] {t.get('name', '-')} ({role}) | 路径名: {t.get('mount_path', '-')} | "
            f"保存目录: {t.get('save_folder', '-')} | 配额: 官方自动获取 | 状态: {status}"
        )


def config_add_target(cfg: dict):
    print("\n--- 新增 115 云存储目标 ---")
    mount_raw = input("请输入 CD2 中的 115 路径名（如 /115 或 /老盘，留空取消）: ").strip()
    if not mount_raw:
        return
    mount_path = normalize_path(mount_raw)
    default_save = f"{mount_path}/云下载/hpls/tg"
    save_raw = input(f"请输入保存目录 [默认 {default_save}]: ").strip()
    save_folder = normalize_path(save_raw) if save_raw else default_save

    default_name = mount_path.strip("/") or f"115-{len(cfg['clouddrive2']['targets']) + 1}"
    name_raw = input(f"请输入显示名称 [默认 {default_name}]: ").strip()
    name = name_raw or default_name

    cfg["clouddrive2"]["targets"].append({
        "name": name,
        "mount_path": mount_path,
        "save_folder": save_folder,
        "enabled": True,
    })
    save_config(cfg)
    print(f"[成功] 已新增 115 目标 [{name}] -> {save_folder} (配额由官方自动获取)！运行中的服务将在 2 秒内热重载生效。")


def config_edit_target(cfg: dict):
    targets = cfg.get("clouddrive2", {}).get("targets", [])
    if not targets:
        print("\n[提示] 暂无可修改的 115 目标。")
        return
    print_targets_table(cfg)
    raw = input("\n请输入要修改的目标序号（留空取消）: ").strip()
    if not raw:
        return
    try:
        idx = int(raw) - 1
        if idx < 0 or idx >= len(targets):
            raise IndexError
    except (ValueError, IndexError):
        print("[错误] 无效序号。")
        return

    t = targets[idx]
    old_mount = t.get("mount_path", "")
    old_save = t.get("save_folder", "")
    old_name = t.get("name", "")
    old_enabled = t.get("enabled", True)

    print(f"\n正在修改目标 [{idx + 1}]（直接回车保持原值）：")
    new_mount_raw = input(f"  路径名 [{old_mount}]: ").strip()
    new_mount = normalize_path(new_mount_raw) if new_mount_raw else old_mount

    suggested_save = old_save
    if new_mount != old_mount and old_mount and old_save.startswith(old_mount + "/"):
        suggested_save = new_mount + old_save[len(old_mount):]
    new_save_raw = input(f"  保存目录 [{suggested_save}]: ").strip()
    new_save = normalize_path(new_save_raw) if new_save_raw else suggested_save

    suggested_name = new_mount.strip("/") if (new_mount != old_mount and old_name == old_mount.strip("/")) else old_name
    new_name_raw = input(f"  显示名称 [{suggested_name}]: ").strip()
    new_name = new_name_raw or suggested_name

    cur_en_str = "y" if old_enabled else "n"
    en_raw = input(f"  是否启用 (y/n) [{cur_en_str}]: ").strip().lower()
    if en_raw in ("y", "yes", "1"):
        new_enabled = True
    elif en_raw in ("n", "no", "0"):
        new_enabled = False
    else:
        new_enabled = old_enabled

    t["name"] = new_name
    t["mount_path"] = new_mount
    t["save_folder"] = new_save
    t["enabled"] = new_enabled
    t.pop("daily_limit", None)

    save_config(cfg)
    print(f"[成功] 已更新目标 [{idx + 1}]！运行中的服务会自动热重载生效。")


def config_delete_target(cfg: dict):
    targets = cfg.get("clouddrive2", {}).get("targets", [])
    if not targets:
        print("\n[提示] 暂无可删除的 115 目标。")
        return
    print_targets_table(cfg)
    raw = input("\n请输入要删除的目标序号（留空取消）: ").strip()
    if not raw:
        return
    try:
        idx = int(raw) - 1
        if idx < 0 or idx >= len(targets):
            raise IndexError
    except (ValueError, IndexError):
        print("[错误] 无效序号。")
        return

    t = targets[idx]
    confirm = input(f"确认删除 115 目标 [{t['name']}] ({t['save_folder']})？(y/N): ").strip().lower()
    if confirm != "y":
        print("已取消删除。")
        return

    targets.pop(idx)
    save_config(cfg)
    print(f"[成功] 已删除目标 [{t['name']}]！运行中的服务会自动热重载生效。")


def config_reorder_targets(cfg: dict):
    targets = cfg.get("clouddrive2", {}).get("targets", [])
    if len(targets) < 2:
        print("\n[提示] 当前目标数量少于 2 个，无需调整顺序。")
        return
    print_targets_table(cfg)
    src_raw = input("\n请输入要移动的目标序号（留空取消）: ").strip()
    if not src_raw:
        return
    dst_raw = input(f"请输入目标新位置 (1~{len(targets)}): ").strip()
    try:
        src = int(src_raw) - 1
        dst = int(dst_raw) - 1
        if not (0 <= src < len(targets) and 0 <= dst < len(targets)):
            raise IndexError
    except (ValueError, IndexError):
        print("[错误] 无效序号。")
        return

    item = targets.pop(src)
    targets.insert(dst, item)
    save_config(cfg)
    print(f"[成功] 已将 [{item['name']}] 移动到第 {dst + 1} 顺位！第 1 顺位将作为跨云归并的主盘。")


def config_edit_basic(cfg: dict):
    tg = cfg.setdefault("telegram", {})
    cd2 = cfg.setdefault("clouddrive2", {})
    print("\n--- 修改基础设置（直接回车保持原值） ---")

    cur_server = cd2.get("server", "127.0.0.1:19798")
    new_server = input(f"  CD2 gRPC 地址 [{cur_server}]: ").strip() or cur_server

    cur_token = cd2.get("api_token", "")
    masked = (cur_token[:6] + "..." + cur_token[-4:]) if len(cur_token) > 12 else cur_token
    new_token = input(f"  CD2 API Token [{masked}]: ").strip() or cur_token

    cur_split = cd2.get("split_by_actor", True)
    split_raw = input(f"  按出演者自动建子文件夹 (y/n) [{'y' if cur_split else 'n'}]: ").strip().lower()
    if split_raw in ("y", "yes"):
        new_split = True
    elif split_raw in ("n", "no"):
        new_split = False
    else:
        new_split = cur_split

    cur_channel = tg.get("target_channel", "")
    new_channel = input(f"  监听 TG 频道用户名 [{cur_channel}]: ").strip().lstrip("@") or cur_channel

    cur_start = tg.get("history_start_time", "2025-01-01 00:00:00")
    new_start = input(f"  首次回溯起点时间 [{cur_start}]: ").strip() or cur_start

    cd2["server"] = new_server
    cd2["api_token"] = new_token
    cd2["split_by_actor"] = new_split
    tg["target_channel"] = new_channel
    tg["history_start_time"] = new_start
    save_config(cfg)
    print("[成功] 基础设置已保存！（注意：若修改了 TG 频道，请停止后重新启动以使监听事件生效。）")


def config_manage_merge_and_quota(cfg: dict):
    cd2 = cfg.setdefault("clouddrive2", {})
    merge = cd2.setdefault("merge", {})
    print("\n--- 官方配额停止阈值与跨云归并设置 ---")

    cur_pct = cd2.get("quota_pause_percent", 90)
    print(f"当前官方配额停止阈值: {cur_pct}%（配额由 115 官方接口自动感知，使用率达到 {cur_pct}% 时自动停止换盘或归并休眠）")
    pct_raw = input(f"请输入新的停止阈值百分比 (1~100) [{cur_pct}]: ").strip()
    if pct_raw:
        try:
            val = int(pct_raw)
            if 1 <= val <= 100:
                cd2["quota_pause_percent"] = val
            else:
                print("[错误] 百分比必须在 1~100 之间，保持原值。")
        except ValueError:
            print("[错误] 输入无效，保持原值。")

    cur_merge_en = merge.get("enabled", True)
    en_raw = input(f"全部盘满额后是否自动跨云归并副盘到主盘？(y/n) [{'y' if cur_merge_en else 'n'}]: ").strip().lower()
    if en_raw in ("y", "yes"):
        merge["enabled"] = True
    elif en_raw in ("n", "no"):
        merge["enabled"] = False

    cur_wait = merge.get("wait_offline_max_minutes", 120)
    wait_raw = input(f"归并前等待副盘未完成离线任务的最长超时(分钟) [{cur_wait}]: ").strip()
    if wait_raw:
        try:
            w_val = max(1, int(wait_raw))
            merge["wait_offline_max_minutes"] = w_val
        except ValueError:
            print("[错误] 超时必须是正整数，保持原值。")

    save_config(cfg)
    print("[成功] 配额阈值与跨云归并配置已保存！后台服务会自动热重载。")


def load_target_actors() -> tuple:
    if os.path.exists(ACTORS_TXT_FILE):
        actors = {}
        try:
            with open(ACTORS_TXT_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if ":" in line or "：" in line:
                        sep = ":" if ":" in line else "："
                        parts = line.split(sep, 1)
                        main_name = parts[0].strip()
                        aliases = [a.strip() for a in parts[1].replace("，", ",").split(",") if a.strip()]
                    else:
                        main_name = line
                        aliases = [line]
                    if main_name:
                        if main_name not in aliases:
                            aliases.insert(0, main_name)
                        actors[main_name] = aliases
            if actors:
                return actors, ACTORS_TXT_FILE
        except Exception:
            pass

    if os.path.exists(ACTORS_FILE):
        try:
            with open(ACTORS_FILE, "r", encoding="utf-8") as f:
                actors = json.load(f)
            if isinstance(actors, dict) and actors:
                return actors, ACTORS_FILE
        except Exception:
            pass

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            actors = cfg.get("target_actors")
            if isinstance(actors, dict) and actors:
                return actors, CONFIG_FILE
        except Exception:
            pass

    if os.path.exists(ACTORS_EXAMPLE):
        try:
            shutil.copyfile(ACTORS_EXAMPLE, ACTORS_FILE)
            with open(ACTORS_FILE, "r", encoding="utf-8") as f:
                return json.load(f), ACTORS_FILE
        except Exception:
            pass

    return {}, ACTORS_FILE


def save_target_actors(actors: dict, target_path: str = None):
    out_path = target_path or ACTORS_FILE
    if out_path.endswith(".txt"):
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("# 出演者白名单配置 (每行格式: 主名称: 别名1, 别名2, ...)\n\n")
            for name, aliases in actors.items():
                f.write(f"{name}: {', '.join(aliases)}\n")
    else:
        write_json_atomic(ACTORS_FILE, actors)


def config_manage_actors(cfg: dict):
    while True:
        actors, file_used = load_target_actors()
        file_name = os.path.basename(file_used)
        print(f"\n--- 出演者白名单管理（当前共 {len(actors)} 位，存储于: {file_name}） ---")
        print(f"[提示] 你也可以随时用文本编辑器直接打开 {file_name} 编辑，保存后后台 2 秒内热重载！")
        print("1. 查看全部出演者")
        print("2. 新增出演者（含多别名）")
        print("3. 删除出演者")
        print("4. 一键智能导入/更新 Top 100+ 热门女优（自动补齐中/日/繁/英多语言别名）")
        print("0. 返回上一级")
        choice = input("请选择: ").strip()
        if choice == "0":
            return
        elif choice == "1":
            for i, (name, aliases) in enumerate(actors.items(), 1):
                print(f"  {i:2d}. {name}: {', '.join(aliases)}")
        elif choice == "2":
            main_name = input("请输入主名称（用作文件夹名，如 河北彩花，留空取消）: ").strip()
            if not main_name:
                continue
            alias_raw = input("请输入所有别名（英文逗号隔开，含日文/繁体/英文，留空则仅用主名称）: ").strip()
            aliases = [a.strip() for a in alias_raw.replace("，", ",").split(",") if a.strip()]
            if main_name not in aliases:
                aliases.insert(0, main_name)
            actors[main_name] = aliases
            save_target_actors(actors, file_used)
            print(f"[成功] 已添加出演者 [{main_name}] 并保存至 {file_name}！后台服务将自动热重载。")
        elif choice == "3":
            names = list(actors.keys())
            for i, name in enumerate(names, 1):
                print(f"  {i:2d}. {name}")
            raw = input("请输入要删除的序号或准确主名称（留空取消）: ").strip()
            if not raw:
                continue
            target_key = None
            if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(names):
                    target_key = names[idx]
            elif raw in actors:
                target_key = raw
            if target_key:
                actors.pop(target_key, None)
                save_target_actors(actors, file_used)
                print(f"[成功] 已删除出演者 [{target_key}] 并保存至 {file_name}！")
            else:
                print("[错误] 未找到对应出演者。")
        elif choice == "4":
            if update_actors_file is not None:
                print("\n[*] 正在执行智能更新并合并最新权威榜单...")
                res = update_actors_file(backup=True)
                print(f"[成功] 智能更新完成！当前总收录: {res['total']} 位（本次新增: {res['added']} 位，扩充别名: {res['updated_aliases']} 个）。")
                print(f"[*] 配置文件: {ACTORS_FILE}，后台监控引擎将在 2 秒内自动热重载生效！")
            else:
                print("[错误] 未找到 update_top_actors 模块。")
            pause_prompt()


def action_config():
    while True:
        cfg = load_config()
        print("\n" + "=" * 62)
        print("                    4. 配置管理中心")
        print("=" * 62)
        print_targets_table(cfg)
        print("-" * 62)
        print("  1. 新增 115 目标")
        print("  2. 修改 115 目标（路径名 / 保存目录 / 限额 / 启停）")
        print("  3. 删除 115 目标")
        print("  4. 调整 115 轮转顺序（首位即主盘）")
        print("  5. 修改基础设置（CD2 地址 / Token / 频道 / 按演员分类）")
        print("  6. 管理官方配额暂停阈值与跨云归并设置")
        print("  7. 管理出演者白名单")
        print("  0. 返回主菜单")
        print("=" * 62)
        choice = input("请输入数字选项: ").strip()
        if choice == "0":
            return
        elif choice == "1":
            config_add_target(cfg)
        elif choice == "2":
            config_edit_target(cfg)
        elif choice == "3":
            config_delete_target(cfg)
        elif choice == "4":
            config_reorder_targets(cfg)
        elif choice == "5":
            config_edit_basic(cfg)
        elif choice == "6":
            config_manage_merge_and_quota(cfg)
        elif choice == "7":
            config_manage_actors(cfg)
        else:
            print("[提示] 无效选项，请重新输入。")


# ==================== 核心动作: 5 实时任务查看 ====================

def print_live_dashboard():
    cfg = load_config()
    state = get_runtime_state()
    cp = load_checkpoint()
    quota_raw = load_quota_info()
    today = quota_raw.get("date", datetime.datetime.now().strftime("%Y-%m-%d"))
    targets_q = quota_raw.get("targets", {})
    counts = quota_raw.get("counts", {})
    pause_thresh = quota_raw.get("pause_percent_threshold", cfg.get("clouddrive2", {}).get("quota_pause_percent", 95))
    targets = cfg.get("clouddrive2", {}).get("targets", [])
    merge_st = load_merge_status()

    if state["paused"]:
        run_label = f"已暂停 (模式: {state['mode']}, PID: {state['pid']})"
    elif state["running"]:
        run_label = f"运行中 (模式: {state['mode']}, PID: {state['pid']})"
    else:
        run_label = "已停止"

    daemon_label = "已开启 (开机自启)" if state["systemd_enabled"] else "未开启"

    print("\n" + "=" * 70)
    print(f"                  实时任务状态看板 ({today})")
    print("=" * 70)
    print(f"  运行状态   : {run_label}")
    print(f"  守护进程   : {daemon_label}")
    print(f"  监听频道   : @{cfg.get('telegram', {}).get('target_channel', '-')}")
    print(f"  当前断点   : 消息 ID {cp.get('last_scanned_id', 0)} (更新于 {cp.get('updated_at', '-')})")
    print(f"  暂停阈值   : 使用率达到 {pause_thresh}% 自动换盘/暂停休眠")
    print("-" * 70)
    print("  多 115 配额状态（第 1 顺位为主盘）：")

    active_assigned = False
    for idx, t in enumerate(targets, 1):
        m_path = normalize_path(t.get("mount_path", ""))
        s_folder = normalize_path(t.get("save_folder", ""))
        enabled = t.get("enabled", True)

        t_info = targets_q.get(m_path)
        if t_info and t_info.get("official"):
            used = t_info.get("used", 0)
            total = t_info.get("total", 0)
            left = t_info.get("left", 0)
            pct = t_info.get("percent", 0.0)
            bar = render_progress_bar(used, total)
            mode_tag = "官方"
        else:
            used = counts.get(s_folder, 0)
            total = 0
            left = 0
            pct = 0.0
            bar = "[" + "." * 16 + "]  --%"
            mode_tag = "探测中"

        if not enabled:
            tag = "停用"
        elif pct >= pause_thresh or (total > 0 and left <= 0):
            tag = "达到阈值/停止"
        elif not active_assigned:
            tag = "推送中"
            active_assigned = True
        else:
            tag = "排队候补"

        role = "主盘" if idx == 1 else "副盘"
        quota_display = f"官方已用:{used}/{total}(剩{left})" if total > 0 else f"官方同步中(已推{used}项)"
        print(f"  [{idx}] {t.get('name', '-'):<6}({role}) {bar} {quota_display:<20} | {tag:<8} | {s_folder}")

    # 跨云归并状态展示
    if merge_st:
        print("-" * 70)
        p_name = merge_st.get("primary", "-")
        fin_at = merge_st.get("finished_at", "-")
        moved = merge_st.get("moved", 0)
        failed = merge_st.get("failed", 0)
        st_label = "成功" if merge_st.get("ok", False) else "部分失败"
        print(f"  跨云归并状态: 最近一次归并至 [{p_name}] - {st_label} (已搬移 {moved} 项, 失败 {failed} 项 | {fin_at})")

    print("-" * 70)
    record_file = os.path.join(RECORD_DIR, f"{today}.md")
    if os.path.exists(record_file):
        with open(record_file, "r", encoding="utf-8", errors="ignore") as f:
            rows = [line.strip() for line in f if line.startswith("| ") and not line.startswith("| 时间") and not line.startswith("| 下载时间") and not line.startswith("| :---")]
        print(f"  今日已归档记录 ({len(rows)} 条)，最近 5 条：")
        for row in rows[-5:]:
            print(f"    {row[:98]}")
    else:
        print("  今日暂无下载记录。")
    print("=" * 70)


def follow_live_logs():
    state = get_runtime_state()
    print("\n>>> 正在进入实时日志流（按 Ctrl+C 安全返回菜单，不会中断后台任务）...\n")
    try:
        if state["systemd_active"] or (state["systemd_installed"] and not os.path.exists(LOG_FILE)):
            cmd = ["journalctl", "-u", SERVICE_NAME, "-n", "50", "-f"]
            if is_linux() and not is_root():
                cmd = ["sudo"] + cmd
            subprocess.run(cmd)
        else:
            if not os.path.exists(LOG_FILE):
                open(LOG_FILE, "a", encoding="utf-8").close()
            subprocess.run(["tail", "-n", "50", "-f", LOG_FILE])
    except KeyboardInterrupt:
        print("\n>>> 已退出实时日志查看，后台任务不受影响。")


def action_manual_merge():
    if CD2Client is None or run_merge is None:
        print("\n[错误] cd2_ops 模块加载失败，请检查依赖。")
        pause_prompt()
        return

    cfg = load_config()
    targets = cfg.get("clouddrive2", {}).get("targets", [])
    enabled = [t for t in targets if t.get("enabled", True)]
    if len(enabled) < 2:
        print("\n[提示] 启用的 115 目标少于 2 个，无需执行跨云归并。")
        pause_prompt()
        return

    primary = enabled[0]
    sources = enabled[1:]
    print("\n" + "=" * 62)
    print("              手动执行跨云归并流水线")
    print("=" * 62)
    print(f"  主盘（归并目的地）: [{primary['name']}] -> {primary['save_folder']}")
    sources_desc = ", ".join(f"[{s['name']}]" for s in sources)
    print(f"  副盘（待搬迁来源）: {sources_desc}")
    print("  操作说明: 将副盘保存目录中的所有内容跨云移动到主盘保存目录，")
    print("            支持覆盖同名文件与文件夹递归合并，搬完后刷新 CD2 两边目录。")
    print("=" * 62)
    confirm = input("确认立即执行归并？(y/N): ").strip().lower()
    if confirm != "y":
        print("已取消归并。")
        pause_prompt()
        return

    cd2_server = cfg.get("clouddrive2", {}).get("server", "127.0.0.1:19798")
    cd2_token = cfg.get("clouddrive2", {}).get("api_token", "")
    merge_conf = cfg.get("clouddrive2", {}).get("merge", {"wait_offline_max_minutes": 120})

    print("\n[*] 正在连接 CD2 并执行归并，请稍候...\n")
    client = CD2Client(server=cd2_server, token=cd2_token, logger=print)
    summary = run_merge(client, targets, merge_conf, DATA_DIR, logger=print)
    print("\n" + "-" * 62)
    print(f"归并执行完成！结果: {'全部成功' if summary.get('ok') else '部分失败'}")
    print(f"  总搬移成功: {summary.get('moved', 0)} 项")
    print(f"  失败项目数: {summary.get('failed', 0)} 项")
    print("-" * 62)
    pause_prompt()


def action_live_view():
    while True:
        print_live_dashboard()
        print("  1. 查看实时滚动日志（Ctrl+C 返回）")
        print("  2. 查看今日完整下载记录文件")
        print("  3. 立即手动执行跨云归并 (副盘全部内容 -> 主盘，并刷新 CD2)")
        print("  4. 刷新状态看板")
        print("  0. 返回主菜单")
        choice = input("请选择: ").strip()
        if choice == "0":
            return
        elif choice == "1":
            follow_live_logs()
        elif choice == "2":
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            record_file = os.path.join(RECORD_DIR, f"{today}.md")
            if os.path.exists(record_file):
                print("")
                with open(record_file, "r", encoding="utf-8", errors="ignore") as f:
                    print(f.read())
            else:
                print(f"\n[提示] 今日记录文件不存在: {record_file}")
            pause_prompt()
        elif choice == "3":
            action_manual_merge()
        elif choice == "4":
            continue


# ==================== 核心动作: 6 守护进程管理 ====================

def enable_systemd_daemon():
    if not systemd_available():
        print("\n[错误] 当前环境未检测到 systemd (systemctl)，无法配置守护进程。")
        return

    if not ensure_telegram_session():
        print("\n[提示] 开启守护进程前需先完成一次 Telegram 登录认证。")
        return

    if get_standalone_pid() > 0:
        print("[*] 正在停止当前独立后台进程以移交给 systemd 守护...")
        stop_standalone_process()

    cur_user = getpass.getuser()
    py_bin = get_python_bin()
    service_content = f"""[Unit]
Description=Telegram to 115 CloudDrive2 Auto Offline Downloader
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={cur_user}
WorkingDirectory={BASE_DIR}
ExecStart={py_bin} {MONITOR_SCRIPT}
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1
Environment=LANG=C.UTF-8

[Install]
WantedBy=multi-user.target
"""

    print(f"[*] 正在写入守护服务配置: {SERVICE_PATH} (运行用户: {cur_user})...")
    write_res = run_cmd(["tee", SERVICE_PATH], use_sudo=True, input_text=service_content)
    if write_res.returncode != 0:
        print(f"[失败] 写入服务文件失败: {write_res.stderr.strip()}")
        return

    run_cmd(["systemctl", "daemon-reload"], use_sudo=True)
    res = run_cmd(["systemctl", "enable", "--now", SERVICE_NAME], use_sudo=True)
    if res.returncode == 0:
        print("[成功] 守护进程已开启并启动！服务器重启后将自动拉起，异常退出将自动复活。")
    else:
        print(f"[失败] 开启守护进程失败: {res.stderr.strip()}")


def disable_systemd_daemon():
    if not systemd_available():
        print("\n[错误] 当前环境未检测到 systemd。")
        return
    print("[*] 正在关闭守护进程并取消开机自启...")
    res = run_cmd(["systemctl", "disable", "--now", SERVICE_NAME], use_sudo=True)
    if res.returncode == 0:
        print("[成功] 守护进程已关闭，开机自启已取消。")
    else:
        print(f"[提示] 执行返回: {res.stderr.strip() or '服务可能尚未开启'}")


def action_daemon():
    while True:
        state = get_runtime_state()
        print("\n" + "=" * 58)
        print("                6. 守护进程管理 (systemd)")
        print("=" * 58)
        print(f"  服务文件 : {'已安装' if state['systemd_installed'] else '未安装'} ({SERVICE_PATH})")
        print(f"  开机自启 : {'已开启' if state['systemd_enabled'] else '未开启'}")
        print(f"  运行状态 : {'运行中 (PID ' + str(state['pid']) + ')' if state['systemd_active'] else '未运行'}")
        print("-" * 58)
        print("  1. 开启守护进程（写入服务 + 开机自启 + 立即启动）")
        print("  2. 关闭守护进程（立即停止 + 取消开机自启）")
        print("  3. 重启守护进程")
        print("  4. 查看 systemd 详细状态")
        print("  0. 返回主菜单")
        print("=" * 58)
        choice = input("请选择: ").strip()
        if choice == "0":
            return
        elif choice == "1":
            enable_systemd_daemon()
            pause_prompt()
        elif choice == "2":
            disable_systemd_daemon()
            pause_prompt()
        elif choice == "3":
            res = run_cmd(["systemctl", "restart", SERVICE_NAME], use_sudo=True)
            print("[成功] 守护进程已重启。" if res.returncode == 0 else f"[失败] {res.stderr.strip()}")
            pause_prompt()
        elif choice == "4":
            res = run_cmd(["systemctl", "status", SERVICE_NAME, "--no-pager"], use_sudo=True)
            print("\n" + (res.stdout or res.stderr))
            pause_prompt()


# ==================== 主菜单 ====================

def print_main_menu():
    cfg = load_config()
    state = get_runtime_state()
    quota_raw = load_quota_info()
    today = quota_raw.get("date", datetime.datetime.now().strftime("%Y-%m-%d"))
    targets_q = quota_raw.get("targets", {})
    counts = quota_raw.get("counts", {})
    targets = cfg.get("clouddrive2", {}).get("targets", [])
    cp = load_checkpoint()

    if state["paused"]:
        status_str = f"已暂停 (PID: {state['pid']})"
    elif state["running"]:
        mode_zh = "守护进程" if state["mode"] == "systemd" else "后台进程"
        status_str = f"运行中 ({mode_zh}, PID: {state['pid']})"
    else:
        status_str = "已停止"

    quota_parts = []
    for t in targets:
        if t.get("enabled", True):
            m_path = normalize_path(t.get("mount_path", ""))
            s_folder = normalize_path(t.get("save_folder", ""))
            t_info = targets_q.get(m_path)
            if t_info and t_info.get("official") and t_info.get("total", 0) > 0:
                quota_parts.append(f"{t.get('name', '-')}:已用{t_info.get('used', 0)}/剩{t_info.get('left', 0)}({t_info.get('percent', 0)}%)")
            else:
                c = counts.get(s_folder, 0)
                quota_parts.append(f"{t.get('name', '-')}:官方同步中(已推{c})")

    quota_str = " | ".join(quota_parts) if quota_parts else "未配置启用目标"

    print("\n" + "=" * 64)
    print("       TG -> 115 智能云下载管理面板 (Ubuntu CLI)")
    print("=" * 64)
    print(f"  当前状态 : {status_str}")
    print(f"  守护进程 : {'已开启' if state['systemd_enabled'] else '未开启'}")
    print(f"  今日配额 : {quota_str} ({today})")
    print(f"  最新断点 : 消息 ID {cp.get('last_scanned_id', 0)}")
    print("-" * 64)
    print("  1. 启动（启动或恢复任务）")
    print("  2. 暂停（挂起推送，保留断点）")
    print("  3. 停止（安全停止任务并保存断点）")
    print("  4. 配置（管理多 115 路径名 / 保存目录 / 限额 / 阈值与归并）")
    print("  5. 实时任务查看（配额进度 / 实时日志 / 今日记录 / 手动归并）")
    print("  6. 守护进程（开启和关闭 systemd 开机自启）")
    print("  7. 退出")
    print("=" * 64)


def main():
    while True:
        try:
            print_main_menu()
            choice = input("请输入数字选项 (1-7): ").strip()
            if choice == "1":
                action_start()
            elif choice == "2":
                action_pause()
            elif choice == "3":
                action_stop()
            elif choice == "4":
                action_config()
            elif choice == "5":
                action_live_view()
            elif choice == "6":
                action_daemon()
            elif choice == "7":
                state = get_runtime_state()
                if state["running"]:
                    print(f"\n[再见] 已退出管理面板（后台任务仍在运行中，PID: {state['pid']}）。")
                else:
                    print("\n[再见] 已退出管理面板。")
                sys.exit(0)
            else:
                print("[提示] 请输入 1~7 之间的数字。")
        except KeyboardInterrupt:
            print("\n[提示] 检测到 Ctrl+C，请选择 7 退出面板。")


if __name__ == "__main__":
    main()
