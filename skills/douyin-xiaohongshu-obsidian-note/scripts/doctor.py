"""Inspect the selected Python runtime and headless CLI readiness without using a browser."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import shutil
import sys


def main() -> int:
    supported = sys.version_info >= (3, 10)
    pillow = importlib.util.find_spec("PIL") is not None
    faster_whisper = importlib.util.find_spec("faster_whisper") is not None
    openai_whisper = importlib.util.find_spec("whisper") is not None
    cookie_dir = Path(__file__).resolve().parents[1] / "cookies"
    douyin_cookie = (cookie_dir / "douyin.txt").is_file() and (cookie_dir / "douyin.txt").stat().st_size > 0
    xhs_cookie = (cookie_dir / "xiaohongshu.txt").is_file() and (cookie_dir / "xiaohongshu.txt").stat().st_size > 0
    print(json.dumps({
        "python": sys.executable, "version": sys.version.split()[0],
        "python_supported": supported, "pillow": pillow,
        "image_publish_ready": supported and pillow,
        "ffmpeg": shutil.which("ffmpeg"), "ffprobe": shutil.which("ffprobe"),
        "yt_dlp": shutil.which("yt-dlp"),
        "execution_mode": "headless_cli_only",
        "local_cookies": {"douyin": douyin_cookie, "xiaohongshu": xhs_cookie},
        "local_asr": "faster_whisper" if faster_whisper else ("openai_whisper" if openai_whisper else None),
        "vision": "must_be_verified_by_agent", "asr": "ready_via_transcribe_video_py" if (faster_whisper or openai_whisper) else "optional_external_capability",
    }, ensure_ascii=False, indent=2))
    return 0 if supported and pillow else 2


if __name__ == "__main__":
    raise SystemExit(main())
