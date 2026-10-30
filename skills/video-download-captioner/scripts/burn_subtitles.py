#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能视频字幕烧录工具 (基于行业标准比例自动适配字号)
用法:
    python burn_subtitles.py <video_path> <srt_path> [--mode hard|soft] [--output output.mp4]
"""

import sys
import os
import json
import subprocess
import argparse
from pathlib import Path

def get_video_dimensions(video_path: str):
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json", video_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        stream = data["streams"][0]
        return int(stream["width"]), int(stream["height"])
    except Exception as e:
        print(f"[!] 无法获取视频分辨率，采用默认 720p: {e}", file=sys.stderr)
        return 1280, 720

def calculate_subtitle_style(height: int):
    """
    根据画面高度计算工业级字幕比例 (字高约 5.5% ~ 6.0%)
    """
    font_size = max(28, int(height * 0.058))
    outline_width = round(font_size * 0.055, 1)
    margin_bottom = int(height * 0.048)

    return {
        "font_name": "Microsoft YaHei",
        "font_size": font_size,
        "primary_color": "#ffffff",
        "outline_color": "#000000",
        "outline_width": outline_width,
        "bold": True,
        "spacing": 1.2,
        "margin_bottom": margin_bottom
    }

def main():
    parser = argparse.ArgumentParser(description="根据分辨率自适应烧录标准中文字幕")
    parser.add_argument("video", help="输入视频路径")
    parser.add_argument("subtitle", help="输入 SRT/ASS 字幕路径")
    parser.add_argument("--mode", choices=["hard", "soft"], default="hard", help="字幕嵌入模式 (默认 hard 硬字幕)")
    parser.add_argument("--quality", choices=["ultra", "high", "medium"], default="high", help="压制画质")
    parser.add_argument("-o", "--output", help="输出视频路径")

    args = parser.parse_args()

    video_path = Path(args.video).resolve()
    sub_path = Path(args.subtitle).resolve()

    if not video_path.exists():
        print(f"[!] 视频文件不存在: {video_path}", file=sys.stderr)
        sys.exit(1)
    if not sub_path.exists():
        print(f"[!] 字幕文件不存在: {sub_path}", file=sys.stderr)
        sys.exit(1)

    output_path = args.output
    if not output_path:
        suffix = "_sub.mp4" if args.mode == "hard" else "_soft.mp4"
        output_path = video_path.with_name(f"{video_path.stem}{suffix}")

    width, height = get_video_dimensions(str(video_path))
    style = calculate_subtitle_style(height)

    print(f"[*] 视频分辨率: {width}x{height}")
    print(f"[*] 自适应标准字号: {style['font_size']}px (占画面高度 ~5.8%), 描边: {style['outline_width']}px, 底边距: {style['margin_bottom']}px")

    cmd = [
        "videocaptioner", "synthesize",
        str(video_path),
        "-s", str(sub_path),
        "--subtitle-mode", args.mode,
        "--quality", args.quality,
        "--style-override", json.dumps(style, ensure_ascii=False),
        "-o", str(output_path),
        "-v"
    ]

    print(f"[*] 执行压制命令: {' '.join(cmd)}")
    ret = subprocess.run(cmd)
    if ret.returncode == 0:
        print(f"\n[✓] 字幕压制完成 -> {output_path}")
    else:
        print(f"\n[!] 压制失败，退出码: {ret.returncode}", file=sys.stderr)
        sys.exit(ret.returncode)

if __name__ == "__main__":
    main()
