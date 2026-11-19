#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TG -> 115 多账号云下载交互式管理面板 (Ubuntu CLI)"""

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
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
CONFIG_EXAMPLE = os.path.join(BASE_DIR, "config.example.json")
MONITOR_SCRIPT = os.path.join(BASE_DIR, "monitor.py")
DATA_DIR = os.path.join(BASE_DIR, "data")
RECORD_DIR = os.path.join(BASE_DIR, "records")
LOG_DIR = os.path.join(BASE_DIR, "logs")

PID_FILE = os.path.join(DATA_DIR, "monitor.pid")
PAUSED_FLAG = os.path.join(DATA_DIR, "paused.flag")
QUOTA_FILE = os.path.join(DATA_DIR, "quota_status.json")
CHECKPOINT_FILE = os.path.join(DATA_DIR, "checkpoint.json")
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
    return cfg


def save_config(cfg: dict):
    # 清理旧版冗余字段，保持配置整洁
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


def load_quota_counts(cfg: dict) -> tuple:
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    counts = {}
    if os.path.exists(QUOTA_FILE):
        try:
            with open(QUOTA_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if raw.get("date") == today:
                if isinstance(raw.get("counts"), dict):
                    counts = {normalize_path(k): int(v) for k, v in raw["counts"].items()}
                elif "count" in raw and cfg.get("clouddrive2", {}).get("targets"):
                    first_folder = normalize_path(cfg["clouddrive2"]["targets"][0]["save_folder"])
                    counts = {first_folder: int(raw.get("count", 0))}
        except Exception:
            pass
    return today, counts


def load_checkpoint() -> dict:
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_scanned_id": 0, "updated_at": "-"}


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

    # 清除残留暂停标记
    if os.path.exists(PAUSED_FLAG):
        try:
            os.remove(PAUSED_FLAG)
        except OSError:
            pass

    if not ensure_telegram_session():
        print("\n[提示] 尚未完成 Telegram 登录认证，取消后台启动。")
        pause_prompt()
        return

    # 如果已开启 systemd 守护进程，优先通过 systemd 启动以保持单一实例
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

    # 独立后台进程启动（脱离 SSH 会话，关闭终端不会中断）
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
    print("[说明] 任务会保留当前断点并挂起推送；暂停期间产生的新消息将在你选择 [1 启动] 恢复后自动补扫，绝不漏抓。")
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
    print("\n当前已配置的 115 云存储目标（按顺序自动轮转）：")
    if not targets:
        print("  (暂无配置，请选择 1 新增)")
        return
    for idx, t in enumerate(targets, 1):
        status = "启用" if t.get("enabled", True) else "停用"
        print(
            f"  [{idx}] {t.get('name', '-')} | 路径名: {t.get('mount_path', '-')} | "
            f"保存目录: {t.get('save_folder', '-')} | 每日限额: {t.get('daily_limit', 500)} | 状态: {status}"
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

    limit_raw = input("请输入该 115 的每日限额 [默认 500]: ").strip()
    try:
        daily_limit = max(1, int(limit_raw)) if limit_raw else 500
    except ValueError:
        print("[错误] 限额必须是正整数，已取消。")
        return

    default_name = mount_path.strip("/") or f"115-{len(cfg['clouddrive2']['targets']) + 1}"
    name_raw = input(f"请输入显示名称 [默认 {default_name}]: ").strip()
    name = name_raw or default_name

    cfg["clouddrive2"]["targets"].append({
        "name": name,
        "mount_path": mount_path,
        "save_folder": save_folder,
        "daily_limit": daily_limit,
        "enabled": True,
    })
    save_config(cfg)
    print(f"[成功] 已新增 115 目标 [{name}] -> {save_folder} (每日限额 {daily_limit})！运行中的服务将在 2 秒内热重载生效。")


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
    old_limit = t.get("daily_limit", 500)
    old_name = t.get("name", "")
    old_enabled = t.get("enabled", True)

    print(f"\n正在修改目标 [{idx + 1}]（直接回车保持原值）：")
    new_mount_raw = input(f"  路径名 [{old_mount}]: ").strip()
    new_mount = normalize_path(new_mount_raw) if new_mount_raw else old_mount

    # 若路径名变了且旧保存目录以旧路径名开头，智能推荐替换前缀
    suggested_save = old_save
    if new_mount != old_mount and old_mount and old_save.startswith(old_mount + "/"):
        suggested_save = new_mount + old_save[len(old_mount):]
    new_save_raw = input(f"  保存目录 [{suggested_save}]: ").strip()
    new_save = normalize_path(new_save_raw) if new_save_raw else suggested_save

    new_limit_raw = input(f"  每日限额 [{old_limit}]: ").strip()
    if new_limit_raw:
        try:
            new_limit = max(1, int(new_limit_raw))
        except ValueError:
            print("[错误] 限额必须是正整数，保持原值。")
            new_limit = old_limit
    else:
        new_limit = old_limit

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
    t["daily_limit"] = new_limit
    t["enabled"] = new_enabled

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
    print(f"[成功] 已将 [{item['name']}] 移动到第 {dst + 1} 顺位！")


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


def config_manage_actors(cfg: dict):
    actors = cfg.setdefault("target_actors", {})
    while True:
        print(f"\n--- 出演者白名单管理（当前共 {len(actors)} 位） ---")
        print("1. 查看全部出演者")
        print("2. 新增出演者（含多别名）")
        print("3. 删除出演者")
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
            save_config(cfg)
            print(f"[成功] 已添加出演者 [{main_name}]（{len(aliases)} 个匹配别名）！")
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
                save_config(cfg)
                print(f"[成功] 已删除出演者 [{target_key}]。")
            else:
                print("[错误] 未找到对应出演者。")


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
        print("  4. 调整 115 轮转顺序")
        print("  5. 修改基础设置（CD2 地址 / Token / 频道 / 按演员分类）")
        print("  6. 管理出演者白名单")
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
            config_manage_actors(cfg)
        else:
            print("[提示] 无效选项，请重新输入。")


# ==================== 核心动作: 5 实时任务查看 ====================

def print_live_dashboard():
    cfg = load_config()
    state = get_runtime_state()
    cp = load_checkpoint()
    today, counts = load_quota_counts(cfg)
    targets = cfg.get("clouddrive2", {}).get("targets", [])

    if state["paused"]:
        run_label = f"已暂停 (模式: {state['mode']}, PID: {state['pid']})"
    elif state["running"]:
        run_label = f"运行中 (模式: {state['mode']}, PID: {state['pid']})"
    else:
        run_label = "已停止"

    daemon_label = "已开启 (开机自启)" if state["systemd_enabled"] else "未开启"

    print("\n" + "=" * 66)
    print(f"                  实时任务状态看板 ({today})")
    print("=" * 66)
    print(f"  运行状态   : {run_label}")
    print(f"  守护进程   : {daemon_label}")
    print(f"  监听频道   : @{cfg.get('telegram', {}).get('target_channel', '-')}")
    print(f"  当前断点   : 消息 ID {cp.get('last_scanned_id', 0)} (更新于 {cp.get('updated_at', '-')})")
    print("-" * 66)
    print("  多 115 今日配额进度（按轮转顺序）：")

    total_used = 0
    total_limit = 0
    active_assigned = False
    for idx, t in enumerate(targets, 1):
        folder = normalize_path(t.get("save_folder", ""))
        limit = int(t.get("daily_limit", 500))
        used = counts.get(folder, 0)
        enabled = t.get("enabled", True)
        if enabled:
            total_used += used
            total_limit += limit

        if not enabled:
            tag = "停用"
        elif used >= limit:
            tag = "已满"
        elif not active_assigned:
            tag = "当前推送中"
            active_assigned = True
        else:
            tag = "排队候补"

        bar = render_progress_bar(used, limit)
        print(f"  [{idx}] {t.get('name', '-'):<8} {bar} {used:4d}/{limit:<4d} | {tag:<6} | {folder}")

    print(f"  总计启用配额: {total_used} / {total_limit}")
    print("-" * 66)

    record_file = os.path.join(RECORD_DIR, f"{today}.md")
    if os.path.exists(record_file):
        with open(record_file, "r", encoding="utf-8", errors="ignore") as f:
            rows = [line.strip() for line in f if line.startswith("| ") and not line.startswith("| 时间") and not line.startswith("| :---")]
        print(f"  今日已归档记录 ({len(rows)} 条)，最近 5 条：")
        for row in rows[-5:]:
            print(f"    {row[:95]}")
    else:
        print("  今日暂无下载记录。")
    print("=" * 66)


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


def action_live_view():
    while True:
        print_live_dashboard()
        print("  1. 查看实时滚动日志（Ctrl+C 返回）")
        print("  2. 查看今日完整下载记录文件")
        print("  3. 刷新状态看板")
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
            continue


# ==================== 核心动作: 6 守护进程管理 ====================

def enable_systemd_daemon():
    if not systemd_available():
        print("\n[错误] 当前环境未检测到 systemd (systemctl)，无法配置守护进程。")
        return

    if not ensure_telegram_session():
        print("\n[提示] 开启守护进程前需先完成一次 Telegram 登录认证。")
        return

    # 停止独立后台进程，防止双实例锁冲突
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
    today, counts = load_quota_counts(cfg)
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
            used = counts.get(normalize_path(t.get("save_folder", "")), 0)
            quota_parts.append(f"{t.get('name', '-')}:{used}/{t.get('daily_limit', 500)}")
    quota_str = " | ".join(quota_parts) if quota_parts else "未配置启用目标"

    print("\n" + "=" * 62)
    print("       TG -> 115 多账号云下载管理面板 (Ubuntu CLI)")
    print("=" * 62)
    print(f"  当前状态 : {status_str}")
    print(f"  守护进程 : {'已开启' if state['systemd_enabled'] else '未开启'}")
    print(f"  今日配额 : {quota_str} ({today})")
    print(f"  最新断点 : 消息 ID {cp.get('last_scanned_id', 0)}")
    print("-" * 62)
    print("  1. 启动（启动或恢复任务）")
    print("  2. 暂停（挂起推送，保留断点）")
    print("  3. 停止（安全停止任务并保存断点）")
    print("  4. 配置（管理多 115 路径名 / 保存目录 / 限额）")
    print("  5. 实时任务查看（配额进度 / 实时日志 / 今日记录）")
    print("  6. 守护进程（开启和关闭 systemd 开机自启）")
    print("  7. 退出")
    print("=" * 62)


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
