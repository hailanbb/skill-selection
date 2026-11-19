#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CloudDrive2 gRPC 操作封装：离线推送 / 官方配额 / 离线任务状态 / 跨云归并 / 目录刷新"""

import os
import sys
import json
import time
import datetime

import grpc
from google.protobuf import empty_pb2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import clouddrive_pb2 as pb
import clouddrive_pb2_grpc as pbg

RPC_TIMEOUT = 20          # 普通调用超时（秒）
MOVE_TIMEOUT = 600        # 跨云移动调用超时（秒）
QUOTA_KEYWORDS = ["配额", "quota", "上限", "exceeded", "次数", "已满", "limit"]


def normalize_path(path: str) -> str:
    p = (path or "").strip().replace("\\", "/")
    if not p:
        return ""
    if not p.startswith("/"):
        p = "/" + p
    return p.rstrip("/") or "/"


def is_quota_message(msg: str) -> bool:
    m = (msg or "").lower()
    return any(k in m for k in QUOTA_KEYWORDS)


class CD2Client:
    def __init__(self, server: str, token: str, logger=print):
        self.server = server
        self.token = token
        self.log = logger
        self.channel = grpc.insecure_channel(server)
        self.md = [("authorization", f"Bearer {token}")]

        stub_cls = getattr(pbg, "CloudDriveFileSrvStub", None)
        if stub_cls is None:
            for name in dir(pbg):
                if name.endswith("Stub"):
                    stub_cls = getattr(pbg, name)
                    break
        if stub_cls is None:
            raise RuntimeError("未在 clouddrive_pb2_grpc 中找到 gRPC Stub 类")
        self.stub = stub_cls(self.channel)
        self._apis_cache = None
        self._apis_ts = 0.0
        self.known_folders = set()

    # ---------------- 目录 ----------------

    def create_folder(self, folder_path: str) -> bool:
        folder_path = normalize_path(folder_path)
        if folder_path in self.known_folders:
            return True
        parent, name = folder_path.rsplit("/", 1)
        parent = parent or "/"
        try:
            res = self.stub.CreateFolder(
                pb.CreateFolderRequest(parentPath=parent, folderName=name),
                metadata=self.md, timeout=RPC_TIMEOUT,
            )
            r = getattr(res, "result", None)
            if r is not None and r.ListFields() and not r.success:
                msg = r.errorMessage or ""
                if "exist" in msg.lower() or "已存在" in msg:
                    self.known_folders.add(folder_path)
                    return True
                self.log(f"-> [CD2] 目录创建失败: {folder_path} - {msg}")
                return False
            self.known_folders.add(folder_path)
            return True
        except grpc.RpcError as e:
            details = (e.details() or "").lower()
            if e.code() == grpc.StatusCode.ALREADY_EXISTS or "exist" in details or "已存在" in details:
                self.known_folders.add(folder_path)
                return True
            self.log(f"-> [CD2] 目录创建返回: {folder_path} - {e.code()} {e.details()}")
            return False

    def ensure_folder_chain(self, folder_path: str, mount_path: str):
        folder_path = normalize_path(folder_path)
        mount_path = normalize_path(mount_path)
        if folder_path in self.known_folders:
            return
        if mount_path and folder_path.startswith(mount_path + "/"):
            cur = mount_path
            for part in [p for p in folder_path[len(mount_path) + 1:].split("/") if p]:
                cur = f"{cur}/{part}"
                if cur not in self.known_folders:
                    self.create_folder(cur)
        else:
            self.create_folder(folder_path)

    def forget_folders_under(self, prefix: str):
        prefix = normalize_path(prefix)
        self.known_folders = {f for f in self.known_folders if not f.startswith(prefix + "/")}

    def list_sub(self, path: str, force_refresh: bool = False) -> list:
        items = []
        stream = self.stub.GetSubFiles(
            pb.ListSubFileRequest(path=normalize_path(path), forceRefresh=force_refresh),
            metadata=self.md, timeout=MOVE_TIMEOUT,
        )
        for reply in stream:
            items.extend(reply.subFiles)
        return items

    def refresh(self, path: str) -> int:
        """强制刷新目录缓存，返回子项数量；失败返回 -1"""
        try:
            return len(self.list_sub(path, force_refresh=True))
        except grpc.RpcError as e:
            self.log(f"-> [CD2] 刷新目录失败: {path} - {e.code()} {e.details()}")
            return -1

    # ---------------- 离线推送 ----------------

    def add_offline(self, magnet: str, to_folder: str):
        """返回 (status, message)；status: OK / QUOTA / NOT_FOUND / FAILED"""
        try:
            res = self.stub.AddOfflineFiles(
                pb.AddOfflineFileRequest(urls=magnet, toFolder=normalize_path(to_folder)),
                metadata=self.md, timeout=RPC_TIMEOUT,
            )
            if res.ListFields() and not res.success:
                msg = res.errorMessage or "未知错误"
                return ("QUOTA" if is_quota_message(msg) else "FAILED"), msg
            return "OK", ""
        except grpc.RpcError as e:
            details = e.details() or ""
            if is_quota_message(details):
                return "QUOTA", details
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return "NOT_FOUND", details
            return "FAILED", f"{e.code()} {details}"

    # ---------------- 官方配额 ----------------

    def _cloud_apis(self) -> list:
        if self._apis_cache is not None and time.time() - self._apis_ts < 600:
            return self._apis_cache
        try:
            res = self.stub.GetAllCloudApis(empty_pb2.Empty(), metadata=self.md, timeout=RPC_TIMEOUT)
            self._apis_cache = list(res.apis)
            self._apis_ts = time.time()
        except grpc.RpcError as e:
            self.log(f"-> [CD2] 获取云存储列表失败: {e.code()} {e.details()}")
            self._apis_cache = []
        return self._apis_cache

    def resolve_account(self, mount_path: str):
        mount_path = normalize_path(mount_path)
        for api in self._cloud_apis():
            api_path = normalize_path(getattr(api, "path", "") or "")
            if api_path and api_path == mount_path:
                return api.name, api.userName
        name = mount_path.strip("/")
        for api in self._cloud_apis():
            if name and name in (api.nickName, api.userName):
                return api.name, api.userName
        return None

    def get_quota(self, mount_path: str):
        """读取 115 官方离线配额，返回 {'total','used','left'}；失败返回 None"""
        mount_path = normalize_path(mount_path)
        if not hasattr(self, "_quota_cache"):
            self._quota_cache = {}
        now = time.time()
        cached = self._quota_cache.get(mount_path)
        if cached and (now - cached[0] < 5):
            return cached[1]

        attempts = [pb.OfflineQuotaRequest(path=mount_path)]
        acc = self.resolve_account(mount_path)
        if acc:
            attempts.insert(0, pb.OfflineQuotaRequest(cloudName=acc[0], cloudAccountId=acc[1], path=mount_path))
            attempts.append(pb.OfflineQuotaRequest(cloudName=acc[0], cloudAccountId=acc[1]))
        last_err = ""
        for req in attempts:
            try:
                info = self.stub.GetOfflineQuotaInfo(req, metadata=self.md, timeout=RPC_TIMEOUT)
                if info.total > 0 or info.left > 0 or info.used > 0:
                    res = {"total": int(info.total), "used": int(info.used), "left": int(info.left)}
                    self._quota_cache[mount_path] = (now, res)
                    return res
                last_err = "接口返回全 0"
            except grpc.RpcError as e:
                last_err = f"{e.code()} {e.details()}"
        self.log(f"-> [CD2] 读取 {mount_path} 官方配额失败: {last_err}")
        return None

    # ---------------- 离线任务状态 ----------------

    def active_offline_count(self, mount_path: str) -> int:
        """统计未完成（初始化/下载中）的离线任务数；失败返回 -1"""
        active_codes = {getattr(pb, "OFFLINE_INIT", 0), getattr(pb, "OFFLINE_DOWNLOADING", 1)}
        try:
            res = self.stub.ListOfflineFilesByPath(
                pb.FileRequest(path=normalize_path(mount_path)),
                metadata=self.md, timeout=RPC_TIMEOUT,
            )
            return sum(1 for f in res.offlineFiles if int(f.status) in active_codes)
        except grpc.RpcError as e:
            self.log(f"-> [CD2] 查询离线任务失败: {mount_path} - {e.code()} {e.details()}")
            return -1

    # ---------------- 跨云归并 ----------------

    def move_all_children(self, src: str, dst: str, batch_size: int = 10):
        """把 src 下的全部子项跨云移动到 dst（覆盖 + 文件夹递归合并）。返回 (moved_names, failed[(name,msg)])"""
        src = normalize_path(src)
        dst = normalize_path(dst)
        children = self.list_sub(src, force_refresh=True)
        entries = []
        for c in children:
            full = c.fullPathName if (c.fullPathName or "").startswith("/") else f"{src}/{c.name}"
            entries.append((c.name, normalize_path(full)))

        moved, failed = [], []

        def do_move(paths):
            req = pb.MoveFileRequest(
                theFilePaths=paths,
                destPath=dst,
                conflictPolicy=pb.MoveFileRequest.Overwrite,
                moveAcrossClouds=True,
                handleConflictRecursively=True,
            )
            res = self.stub.MoveFile(req, metadata=self.md, timeout=MOVE_TIMEOUT)
            if res.ListFields() and not res.success:
                raise RuntimeError(res.errorMessage or "MoveFile 返回失败")

        for i in range(0, len(entries), batch_size):
            batch = entries[i:i + batch_size]
            try:
                do_move([p for _, p in batch])
                moved.extend(n for n, _ in batch)
            except Exception:
                # 批量失败时逐个重试，隔离问题文件
                for name, path in batch:
                    try:
                        do_move([path])
                        moved.append(name)
                    except grpc.RpcError as e:
                        failed.append((name, f"{e.code()} {e.details()}"))
                    except Exception as e:
                        failed.append((name, str(e)))
        return moved, failed


# ---------------- 归并主流程（monitor 与 cli 共用） ----------------

def run_merge(cd2: CD2Client, targets: list, merge_conf: dict, data_dir: str, logger=print) -> dict:
    """
    将所有非主盘（第 1 个启用目标之外）的保存目录全部内容，跨云移动到主盘保存目录（覆盖），
    然后强制刷新两边保存目录。返回执行摘要。
    """
    enabled = [t for t in targets if t.get("enabled", True)]
    summary = {
        "started_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": "",
        "primary": "",
        "moved": 0,
        "failed": 0,
        "details": [],
        "ok": False,
    }
    if len(enabled) < 2:
        logger("[归并] 启用的 115 目标少于 2 个，无需归并。")
        summary["finished_at"] = summary["started_at"]
        summary["ok"] = True
        _write_merge_status(data_dir, summary)
        return summary

    primary = enabled[0]
    sources = enabled[1:]
    dst = normalize_path(primary["save_folder"])
    summary["primary"] = primary["name"]
    cd2.ensure_folder_chain(dst, primary["mount_path"])

    wait_max = int(merge_conf.get("wait_offline_max_minutes", 120))
    logger(f"[归并] 开始：主盘 [{primary['name']}] {dst} ← {', '.join(s['name'] for s in sources)}")

    for src_t in sources:
        src = normalize_path(src_t["save_folder"])

        # 1. 等待该账号离线任务结束（115 离线文件完成后才会落盘，超时也可安全继续，残留下一轮再搬）
        deadline = time.time() + wait_max * 60
        while True:
            active = cd2.active_offline_count(src_t["mount_path"])
            if active <= 0:
                break
            if time.time() >= deadline:
                logger(f"[归并] [{src_t['name']}] 仍有 {active} 个离线任务未完成，已达等待上限 {wait_max} 分钟，"
                       f"先搬运已完成部分，剩余的下次归并处理。")
                break
            logger(f"[归并] [{src_t['name']}] 还有 {active} 个离线任务进行中，60 秒后再检查...")
            time.sleep(60)

        # 2. 跨云移动全部内容（覆盖）
        try:
            moved, failed = cd2.move_all_children(src, dst)
        except grpc.RpcError as e:
            moved, failed = [], [("<列目录>", f"{e.code()} {e.details()}")]
        summary["moved"] += len(moved)
        summary["failed"] += len(failed)
        summary["details"].append({"source": src_t["name"], "moved": moved, "failed": failed})
        logger(f"[归并] [{src_t['name']}] → [{primary['name']}]：成功 {len(moved)} 项，失败 {len(failed)} 项")
        for name, msg in failed:
            logger(f"    ✗ {name}: {msg}")

        cd2.forget_folders_under(src)

        # 3. 刷新两个账号的保存目录（含主盘中被合并的子目录）
        n_src = cd2.refresh(src)
        n_dst = cd2.refresh(dst)
        for name in moved:
            cd2.refresh(f"{dst}/{name}")
        logger(f"[归并] 已刷新目录：{src}（剩余 {n_src} 项） / {dst}（共 {n_dst} 项）")

    summary["finished_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary["ok"] = summary["failed"] == 0
    _write_merge_status(data_dir, summary)
    logger(f"[归并] 完成：共移动 {summary['moved']} 项，失败 {summary['failed']} 项。")
    return summary


def _write_merge_status(data_dir: str, summary: dict):
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, "merge_status.json")
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
