#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Skill Selection Repository & Runtime Version Manager.

Provides bidirectional synchronization, testing, status inspection,
and Windows junction linking between local Antigravity runtime (~/.gemini/config/skills)
and the version-controlled Git repository (hailanbb/skill-selection).
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent
SKILLS_DIR = REPO_ROOT / "skills"
DEFAULT_RUNTIME_DIR = Path.home() / ".gemini" / "config" / "skills"

EXCLUDE_PATTERNS = {
    "cookies",
    ".cookies",
    "__pycache__",
    ".pytest_cache",
    ".git",
    "*.pyc",
    "*.pyo",
    "*.tmp",
    "*.part",
    "*.log",
    ".DS_Store",
    "Thumbs.db",
}

PRIVATE_FILES = {
    "config.json",
    "douyin.txt",
    "xiaohongshu.txt",
}


def is_excluded(rel_path: Path) -> bool:
    for part in rel_path.parts:
        if part in EXCLUDE_PATTERNS or part.startswith(".pytest_cache"):
            return True
        if part.endswith(".pyc") or part.endswith(".tmp") or part.endswith(".part"):
            return True
    return False


def is_junction(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        # On Windows, a junction's resolved path differs from its physical parent path,
        # or resolves directly to the target.
        resolved = path.resolve()
        return resolved != path.absolute()
    except Exception:
        return False


def get_git_status() -> dict[str, Any]:
    info: dict[str, Any] = {"clean": True, "branch": "unknown", "ahead": 0, "behind": 0, "untracked": []}
    try:
        branch_res = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "branch", "--show-current"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        info["branch"] = branch_res.stdout.strip()

        status_res = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "-s"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        status_lines = [l.strip() for l in status_res.stdout.splitlines() if l.strip()]
        info["clean"] = len(status_lines) == 0
        info["status_lines"] = status_lines

        # Check tracking
        tracking_res = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-list", "--left-right", "--count", "@{upstream}...HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if tracking_res.returncode == 0:
            parts = tracking_res.stdout.strip().split()
            if len(parts) == 2:
                info["behind"] = int(parts[0])
                info["ahead"] = int(parts[1])
    except Exception as exc:
        info["error"] = str(exc)
    return info


def compare_skill_dirs(repo_skill: Path, runtime_skill: Path) -> dict[str, list[str]]:
    diff: dict[str, list[str]] = {
        "modified_in_runtime": [],
        "only_in_runtime": [],
        "only_in_repo": [],
    }
    if not runtime_skill.is_dir() or not repo_skill.is_dir():
        return diff

    # Check files in runtime
    for r_file in runtime_skill.rglob("*"):
        rel = r_file.relative_to(runtime_skill)
        if is_excluded(rel) or rel.name in PRIVATE_FILES:
            continue
        repo_file = repo_skill / rel
        if r_file.is_file():
            if not repo_file.is_file():
                diff["only_in_runtime"].append(str(rel))
            else:
                r_bytes = r_file.read_bytes().replace(b"\r\n", b"\n")
                repo_bytes = repo_file.read_bytes().replace(b"\r\n", b"\n")
                if r_bytes != repo_bytes:
                    diff["modified_in_runtime"].append(str(rel))

    # Check files in repo
    for repo_file in repo_skill.rglob("*"):
        rel = repo_file.relative_to(repo_skill)
        if is_excluded(rel) or rel.name in PRIVATE_FILES:
            continue
        r_file = runtime_skill / rel
        if repo_file.is_file() and not r_file.is_file():
            diff["only_in_repo"].append(str(rel))

    return diff


def cmd_status(args: argparse.Namespace) -> int:
    runtime_dir = Path(args.runtime_dir).expanduser().resolve()
    print("=" * 60)
    print("  Skill Selection - 版本状态巡检")
    print("=" * 60)

    # 1. Git 仓库状态
    git_info = get_git_status()
    print(f"\n[Git 仓库] {REPO_ROOT}")
    print(f"  当前分支: {git_info.get('branch', 'unknown')}")
    if git_info.get("behind", 0) > 0:
        print(f"  ⚠️  落后远程 origin: {git_info['behind']} 个 commit (建议运行 git pull)")
    if git_info.get("ahead", 0) > 0:
        print(f"  🚀 超前远程 origin: {git_info['ahead']} 个 commit (可运行 python manage.py push)")
    if git_info.get("clean"):
        print("  工作区状态: 干净 (无未提交更改)")
    else:
        print("  工作区状态: 存在未提交更改:")
        for line in git_info.get("status_lines", []):
            print(f"    {line}")

    # 2. 本地历史冗余仓库巡检
    candidates = [
        Path(r"E:\GoogleAI\ls\skill-selection"),
        Path(r"E:\GoogleAI\workbak\skill-selection"),
    ]
    stale_found = [c for c in candidates if c.is_dir() and c.resolve() != REPO_ROOT]
    if stale_found:
        print("\n[本地冗余副本检测]")
        for c in stale_found:
            print(f"  ⚠️  检测到历史克隆副本: {c} (建议清理归档，避免在此目录误操作)")

    # 3. 与 Antigravity 运行时一致性对比
    print(f"\n[运行时对账] Antigravity 运行目录: {runtime_dir}")
    if not runtime_dir.is_dir():
        print(f"  运行时目录不存在: {runtime_dir}")
        return 0

    repo_skills = sorted([p for p in SKILLS_DIR.iterdir() if p.is_dir()])
    for skill in repo_skills:
        skill_name = skill.name
        rt_skill = runtime_dir / skill_name
        if not rt_skill.exists():
            print(f"  ⚪ {skill_name:<34} [仅在 Repo，未安装至运行时]")
            continue

        if is_junction(rt_skill):
            target = rt_skill.resolve()
            if target == skill.resolve():
                print(f"  🔗 {skill_name:<34} [已软链 (Junction 实时同步)]")
            else:
                print(f"  ⚠️  {skill_name:<34} [软链目标异常: {target}]")
            continue

        diff = compare_skill_dirs(skill, rt_skill)
        has_diff = any(len(v) > 0 for v in diff.values())
        if not has_diff:
            print(f"  🟢 {skill_name:<34} [完全一致 (文件副本同步)]")
        else:
            mod_cnt = len(diff["modified_in_runtime"])
            only_rt = len(diff["only_in_runtime"])
            only_rp = len(diff["only_in_repo"])
            details = []
            if mod_cnt:
                details.append(f"{mod_cnt} 个文件在运行时被修改")
            if only_rt:
                details.append(f"{only_rt} 个新文件仅在运行时")
            if only_rp:
                details.append(f"{only_rp} 个文件仅在 Repo")
            print(f"  🟡 {skill_name:<34} [差异待同步: {', '.join(details)}]")

    return 0


def run_tests_for_skill(skill_dir: Path) -> bool:
    tests_dir = skill_dir / "tests"
    test_files = list(skill_dir.glob("test*.py")) + (list(tests_dir.glob("test*.py")) if tests_dir.is_dir() else [])
    if not test_files:
        print(f"  [跳过测试] {skill_dir.name} 无测试套件")
        return True
    target = tests_dir if tests_dir.is_dir() else skill_dir
    print(f"  [正在测试] {skill_dir.name} ...")
    cmd = [sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", str(target), "-v"]
    completed = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8")
    if completed.returncode == 0:
        print(f"  [测试通过] {skill_dir.name}")
        return True
    print(f"  ❌ [测试失败] {skill_dir.name}:\n{completed.stderr}")
    return False


def cmd_test(args: argparse.Namespace) -> int:
    target_skill = args.skill
    all_passed = True
    if target_skill:
        skill_dir = SKILLS_DIR / target_skill
        if not skill_dir.is_dir():
            print(f"错误: 技能不存在: {target_skill}", file=sys.stderr)
            return 2
        all_passed = run_tests_for_skill(skill_dir)
    else:
        print("运行全库技能测试套件...")
        for skill_dir in sorted(SKILLS_DIR.iterdir()):
            if skill_dir.is_dir():
                passed = run_tests_for_skill(skill_dir)
                if not passed:
                    all_passed = False
    return 0 if all_passed else 1


def sync_directory(src: Path, dst: Path, preserve_private: bool = True) -> int:
    dst.mkdir(parents=True, exist_ok=True)
    count = 0
    for src_file in src.rglob("*"):
        rel = src_file.relative_to(src)
        if is_excluded(rel):
            continue
        if preserve_private and rel.name in PRIVATE_FILES and (dst / rel).exists():
            continue
        dst_target = dst / rel
        if src_file.is_dir():
            dst_target.mkdir(parents=True, exist_ok=True)
        elif src_file.is_file():
            dst_target.parent.mkdir(parents=True, exist_ok=True)
            if not dst_target.exists() or dst_target.read_bytes() != src_file.read_bytes():
                shutil.copy2(src_file, dst_target)
                count += 1
    return count


def cmd_sync_to_repo(args: argparse.Namespace) -> int:
    runtime_dir = Path(args.runtime_dir).expanduser().resolve()
    skill_name = args.skill
    skills_to_sync = [skill_name] if skill_name else [s.name for s in SKILLS_DIR.iterdir() if s.is_dir()]

    for name in skills_to_sync:
        rt_skill = runtime_dir / name
        repo_skill = SKILLS_DIR / name
        if not rt_skill.is_dir():
            if skill_name:
                print(f"错误: 运行时目录中不存在技能: {name}", file=sys.stderr)
                return 2
            continue
        if is_junction(rt_skill):
            print(f"[已跳过] {name} 当前为 Junction 实时链接状态，无需复制同步。")
            continue

        print(f"正在同步: {name} (运行时 -> Repo)...")
        updated = sync_directory(rt_skill, repo_skill, preserve_private=False)
        print(f"  已更新 {updated} 个文件到 Repo。正在执行回归测试...")
        if not run_tests_for_skill(repo_skill):
            print(f"  ⚠️  同步后单元测试失败，请检查修改！", file=sys.stderr)
            return 1
    print("✅ 同步到 Repo 完成。")
    return 0


def cmd_sync_to_runtime(args: argparse.Namespace) -> int:
    runtime_dir = Path(args.runtime_dir).expanduser().resolve()
    skill_name = args.skill
    skills_to_sync = [skill_name] if skill_name else [s.name for s in SKILLS_DIR.iterdir() if s.is_dir()]

    for name in skills_to_sync:
        repo_skill = SKILLS_DIR / name
        rt_skill = runtime_dir / name
        if not repo_skill.is_dir():
            if skill_name:
                print(f"错误: 技能不存在于 Repo: {name}", file=sys.stderr)
                return 2
            continue
        if is_junction(rt_skill):
            print(f"[已跳过] {name} 当前为 Junction 实时链接状态，无需复制同步。")
            continue

        print(f"正在部署: {name} (Repo -> 运行时)...")
        updated = sync_directory(repo_skill, rt_skill, preserve_private=True)
        print(f"  已更新 {updated} 个文件到运行时。")
    print("✅ 部署到运行时完成。")
    return 0


def cmd_link(args: argparse.Namespace) -> int:
    print(
        "⚠️  [重要提示] Antigravity 底层的 Go 语言服务器 (os.ReadDir) 在 Windows 下会跳过带有 ReparsePoint 属性的 Junction 软链目录，\n"
        "   导致软链后的技能从可用技能列表中隐身！\n"
        "   因此已禁用 Junction 软链模式，自动为您切换为实体目录双向同步 (sync-to-runtime)。"
    )
    return cmd_sync_to_runtime(args)


def cmd_unlink(args: argparse.Namespace) -> int:
    if os.name != "nt":
        print("错误: unlink 命令仅支持 Windows 系统。", file=sys.stderr)
        return 2
    skill_name = args.skill
    runtime_dir = Path(args.runtime_dir).expanduser().resolve()
    rt_skill = runtime_dir / skill_name
    repo_skill = (SKILLS_DIR / skill_name).resolve()

    if not is_junction(rt_skill):
        print(f"{skill_name} 不是 Junction 链接，无需解除。")
        return 0

    # Windows 删除 junction
    subprocess.run(["cmd", "/c", "rmdir", str(rt_skill)], check=True)
    print(f"已移除 Junction: {rt_skill}")
    print(f"正在恢复独立文件目录...")
    sync_directory(repo_skill, rt_skill, preserve_private=False)
    print(f"✅ 已解除软链并恢复为独立副本。")
    return 0


def cmd_push(args: argparse.Namespace) -> int:
    message = args.message
    if not message:
        print("错误: 请提供提交信息，例如: python manage.py push \"feat: 更新说明\"", file=sys.stderr)
        return 2

    print("第 1 步: 运行全库单元测试套件预检...")
    test_ret = cmd_test(argparse.Namespace(skill=None))
    if test_ret != 0:
        print("❌ 单元测试存在失败用例，已自动终止提交！请修复后再推送。", file=sys.stderr)
        return 1

    print("\n第 2 步: 暂存改动并提交...")
    subprocess.run(["git", "-C", str(REPO_ROOT), "add", "."], check=True)
    commit_res = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "commit", "-m", message],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if commit_res.returncode != 0 and "nothing to commit" in commit_res.stdout:
        print("  工作区干净，无新改动需要提交。")
    else:
        print(f"  {commit_res.stdout.strip()}")

    print("\n第 3 步: 推送至 GitHub (origin master)...")
    push_res = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "push", "origin", "master"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if push_res.returncode == 0:
        print("🚀 推送成功！已同步至 GitHub: https://github.com/hailanbb/skill-selection")
        return 0
    else:
        print(f"❌ 推送失败:\n{push_res.stderr}", file=sys.stderr)
        return 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--runtime-dir",
        default=str(DEFAULT_RUNTIME_DIR),
        help=f"Antigravity skills runtime directory (default: {DEFAULT_RUNTIME_DIR})",
    )

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # status
    p_status = subparsers.add_parser("status", help="巡检 Git 状态、冗余副本及与 Antigravity 运行环境的一致性")
    p_status.set_defaults(func=cmd_status)

    # test
    p_test = subparsers.add_parser("test", help="运行技能单元测试")
    p_test.add_argument("skill", nargs="?", help="指定技能名称 (缺省则测试全库)")
    p_test.set_defaults(func=cmd_test)

    # sync-to-repo
    p_s2r = subparsers.add_parser("sync-to-repo", help="从 Antigravity 运行目录同步到 Git 仓库并执行测试")
    p_s2r.add_argument("skill", nargs="?", help="指定技能名称 (缺省则同步全部)")
    p_s2r.set_defaults(func=cmd_sync_to_repo)

    # sync-to-runtime
    p_s2m = subparsers.add_parser("sync-to-runtime", help="从 Git 仓库发布部署到 Antigravity 运行目录")
    p_s2m.add_argument("skill", nargs="?", help="指定技能名称 (缺省则部署全部)")
    p_s2m.set_defaults(func=cmd_sync_to_runtime)

    # link
    p_link = subparsers.add_parser("link", help="使用 Windows Junction 建立实时映射软链 (推荐，零版本漂移)")
    p_link.add_argument("skill", help="指定要链接的技能名称 (例如: douyin-xiaohongshu-obsidian-note)")
    p_link.set_defaults(func=cmd_link)

    # unlink
    p_unlink = subparsers.add_parser("unlink", help="解除 Junction 软链并恢复为独立目录")
    p_unlink.add_argument("skill", help="指定要解除链接的技能名称")
    p_unlink.set_defaults(func=cmd_unlink)

    # push
    p_push = subparsers.add_parser("push", help="测试预检 -> Git 提交 -> 推送 GitHub 一体化闭环")
    p_push.add_argument("message", help="Git 提交日志信息")
    p_push.set_defaults(func=cmd_push)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已取消操作。")
        raise SystemExit(130)
