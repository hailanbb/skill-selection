#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TG -> 115 频道真实消息结构探测与解析诊断工具
用于在接入新 Telegram 频道前，先抽样拉取真实消息，深入检测其发帖形态、
种子/磁链提供方式、女优名称位置与格式兼容性。
"""

import os
import sys
import json
import re
import asyncio
import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from telethon import TelegramClient

SESSION_PATH = os.path.join(BASE_DIR, "user_session")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
ACTORS_FILE = os.path.join(BASE_DIR, "actors.json")
ACTORS_TXT_FILE = os.path.join(BASE_DIR, "actors.txt")


def load_actors() -> dict:
    if os.path.exists(ACTORS_TXT_FILE):
        actors = {}
        try:
            with open(ACTORS_TXT_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if ":" in line or "：" in line:
                        delim = ":" if ":" in line else "："
                        main, rest = line.split(delim, 1)
                        aliases = [a.strip() for a in rest.split(",") if a.strip()]
                        main = main.strip()
                        if main not in aliases:
                            aliases.insert(0, main)
                        actors[main] = aliases
            if actors:
                return actors
        except Exception:
            pass

    if os.path.exists(ACTORS_FILE):
        try:
            with open(ACTORS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


def match_actors_in_text(text: str, target_actors: dict) -> list:
    if not text or not target_actors:
        return []
    text_lower = text.lower()
    matched = []
    for main_name, aliases in target_actors.items():
        for alias in aliases:
            if alias and alias.lower() in text_lower:
                matched.append(main_name)
                break
    return matched


def format_msg_date(dt) -> str:
    if not dt:
        return ""
    try:
        local_dt = dt.astimezone()
        return local_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return dt.strftime("%Y-%m-%d %H:%M:%S")


def load_tg_conf() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            return cfg.get("telegram", {})
    except Exception:
        return {}


async def probe_channel_async(channel_name: str, limit: int = 8):
    tg_conf = load_tg_conf()
    api_id = tg_conf.get("api_id")
    api_hash = tg_conf.get("api_hash")

    if not api_id or not api_hash:
        print("[错误] 未在 config.json 中找到有效 telegram.api_id 与 api_hash，请先完成基础配置！")
        return False

    channel_clean = channel_name.strip().lstrip("@")
    if not channel_clean:
        print("[错误] 请提供有效的频道用户名或链接！")
        return False

    client = TelegramClient(SESSION_PATH, api_id, api_hash)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            print("[错误] 尚未完成 Telegram 登录认证，请先通过 ./tg115.sh 菜单 1 进行首次手机验证码登录！")
            return False

        print(f"\n[*] 正在连接 Telegram 服务器并解析频道: @{channel_clean} ...")
        try:
            entity = await client.get_entity(channel_clean)
        except Exception as e:
            print(f"[错误] 无法获取频道 @{channel_clean}: {e}")
            print("      请检查频道名称是否拼写正确，或当前账号是否有权访问该公开/私有频道。")
            return False

        title = getattr(entity, "title", channel_clean)
        chat_id = getattr(entity, "id", "-")
        username = getattr(entity, "username", channel_clean) or channel_clean

        actors_dict = load_actors()
        print("\n" + "=" * 72)
        print(f"        Telegram 频道真实消息结构探测报告: @{username}")
        print("=" * 72)
        print(f"  频道名称 : {title}")
        print(f"  频道 ID   : {chat_id}")
        print(f"  白名单库 : 已载入 {len(actors_dict)} 位出演者（用于实地匹配测试）")
        print(f"  抽样数量 : 最新 {limit} 条真实消息")
        print("-" * 72)

        messages = []
        async for m in client.iter_messages(entity, limit=limit):
            messages.append(m)

        if not messages:
            print("[提示] 该频道当前为空或未获取到任何历史消息。")
            return False

        # 从旧到新排序分析更符合发帖脉络
        messages.reverse()

        torrent_count = 0
        magnet_count = 0
        photo_count = 0
        doc_count = 0
        actor_hit_count = 0
        external_link_count = 0
        samples_info = []

        for idx, msg in enumerate(messages, 1):
            text = (msg.text or msg.message or "").strip()
            date_str = format_msg_date(msg.date)
            media_kind = "纯文本"
            doc_filename = ""
            doc_mime = ""
            doc_size_kb = 0
            is_torrent = False

            if msg.media:
                media_cls = msg.media.__class__.__name__
                if "Photo" in media_cls:
                    media_kind = "图片 (Photo)"
                    photo_count += 1
                elif "Document" in media_cls:
                    doc_count += 1
                    if msg.file:
                        doc_filename = getattr(msg.file, "name", "") or ""
                        doc_mime = getattr(msg.file, "mime_type", "") or ""
                        doc_size_kb = round((getattr(msg.file, "size", 0) or 0) / 1024, 1)
                        if doc_filename.lower().endswith(".torrent") or doc_mime == "application/x-bittorrent":
                            media_kind = f"种子文件 (.torrent, {doc_size_kb}KB)"
                            is_torrent = True
                            torrent_count += 1
                        else:
                            media_kind = f"文档附件 ({doc_filename or '未命名'}, {doc_size_kb}KB)"
                    else:
                        media_kind = "文档附件 (Document)"
                elif "WebPage" in media_cls:
                    media_kind = "网页预览卡片 (WebPage)"
                else:
                    media_kind = f"媒体 ({media_cls})"

            magnets = re.findall(r"magnet:\?xt=urn:btih:[a-zA-Z0-9]+", text, re.IGNORECASE)
            if magnets:
                magnet_count += len(magnets)

            ext_links = re.findall(r"https?://[^\s]+", text)
            if ext_links:
                external_link_count += len(ext_links)

            matched = match_actors_in_text(text, actors_dict)
            if matched:
                actor_hit_count += 1

            samples_info.append({
                "id": msg.id,
                "date": date_str,
                "kind": media_kind,
                "doc_name": doc_filename,
                "is_torrent": is_torrent,
                "magnets": magnets,
                "matched": matched,
                "text_snippet": text.replace("\n", " ")[:90] if text else "(无文字正文)",
            })

        for s in samples_info:
            print(f"[消息 ID: {s['id']}] 时间: {s['date']}")
            print(f"  类型: {s['kind']}")
            if s["is_torrent"]:
                print(f"  附件: [√ 检测到种子文件] {s['doc_name']}")
            if s["magnets"]:
                print(f"  磁链: [√ 正文含有磁力链接] {s['magnets'][0]}")
            if s["matched"]:
                print(f"  出演者: [★ 命中白名单] {', '.join(s['matched'])}")
            print(f"  正文: {s['text_snippet']}")
            print("")

        print("-" * 72)
        print("【真实消息结构与兼容性诊断结论】")
        print(f"  1. 种子/磁链提供方式 : ", end="")
        if torrent_count > 0 and magnet_count > 0:
            print(f"同时包含 .torrent 附件 ({torrent_count}个) 与 正文磁链 ({magnet_count}条) [极佳]")
        elif torrent_count > 0:
            print(f"以 .torrent 种子文件附件为主 ({torrent_count}个) [标准规范]")
        elif magnet_count > 0:
            print(f"直接在正文中提供 magnet 磁力链接 ({magnet_count}条) [直接可用]")
        elif external_link_count > 0:
            print(f"未检测到直接种子/磁力，检测到 {external_link_count} 条外部跳转网页链接 [需注意：非直接磁链]")
        else:
            print("在当前抽样的最新消息中暂未检测到 .torrent 附件或直接磁力链接")

        print(f"  2. 发帖组织模式      : ", end="")
        if photo_count > 0 and torrent_count > 0:
            print("典型【图文封面 + 独立种子附件】多条关联发布模式（完全契合当前跨条关联引擎）")
        elif torrent_count > 0 or magnet_count > 0:
            print("单条消息自闭环发布模式")
        else:
            print("纯资讯或图文展示模式")

        print(f"  3. 出演者匹配表现    : 抽样中有 {actor_hit_count} 条命中当前 100+ 热门女优库")

        print(f"  4. 引擎综合兼容评分  : ", end="")
        if torrent_count > 0 or magnet_count > 0:
            print("【100% 完美兼容！可直接加入监听下载，无需任何代码修改】")
            compatible = True
        elif external_link_count > 0:
            print("【需注意：该频道采用网盘/第三方外链跳转，115 无法直接离线下载此类非种子链接】")
            compatible = False
        else:
            print("【待确认：建议抽样更大范围（如 20 条）或观察最新发帖是否包含种子文件】")
            compatible = False

        print("=" * 72)
        return compatible

    finally:
        if client.is_connected():
            await client.disconnect()


def main():
    if len(sys.argv) > 1:
        channel_name = sys.argv[1].strip()
    else:
        channel_name = input("请输入要探测的 Telegram 频道用户名 (如 jp_ziyuan 或 @jp_ziyuan): ").strip()

    if not channel_name:
        print("[错误] 未指定频道名称。")
        sys.exit(1)

    limit = 8
    if len(sys.argv) > 2:
        try:
            limit = int(sys.argv[2])
        except ValueError:
            pass

    asyncio.run(probe_channel_async(channel_name, limit=limit))


if __name__ == "__main__":
    main()
