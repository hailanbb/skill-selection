#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VideoCaptioner 样式预设快速初始化脚本
用于在全新环境中预先注入符合工业级标准的 ASS 默认字幕样式（支持 720p 与 1080p）。
"""

import sys
import json
from pathlib import Path

def init_styles():
    try:
        from videocaptioner.config import SUBTITLE_STYLE_PATH
        from videocaptioner.core.subtitle.style_manager import SubtitleStyle, StyleMode
    except ImportError:
        print("[!] 未检测到 videocaptioner 库，请先执行: pip install videocaptioner", file=sys.stderr)
        return False

    SUBTITLE_STYLE_PATH.mkdir(parents=True, exist_ok=True)

    # 1. 720p 标准高清样式预设 (字号 42px)
    style_720p = SubtitleStyle(
        name="default",
        description="标准 720p 高清视频字幕 (42px, 纯黑高对比度描边, 微软雅黑加粗)",
        mode=StyleMode.ASS,
        font_name="Microsoft YaHei",
        font_size=42,
        primary_color="#ffffff",
        outline_color="#000000",
        outline_width=2.2,
        bold=True,
        spacing=1.2,
        margin_bottom=35
    )

    # 2. 1080p 全高清样式预设 (字号 60px)
    style_1080p = SubtitleStyle(
        name="1080p",
        description="标准 1080p 全高清视频字幕 (60px, 纯黑高对比度描边, 微软雅黑加粗)",
        mode=StyleMode.ASS,
        font_name="Microsoft YaHei",
        font_size=60,
        primary_color="#ffffff",
        outline_color="#000000",
        outline_width=3.2,
        bold=True,
        spacing=1.5,
        margin_bottom=45
    )

    # 写入文件
    files_to_write = {
        "default.json": style_720p,
        "ass-default.json": style_720p,
        "1080p.json": style_1080p,
        "ass-1080p.json": style_1080p
    }

    for filename, style_obj in files_to_write.items():
        dest = SUBTITLE_STYLE_PATH / filename
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(style_obj.to_json_dict(), f, indent=2, ensure_ascii=False)
        print(f"[✓] 成功写入预设: {dest.name}")

    print(f"\n[✓] 所有字幕预设已成功部署至: {SUBTITLE_STYLE_PATH}")
    return True

if __name__ == "__main__":
    success = init_styles()
    sys.exit(0 if success else 1)
