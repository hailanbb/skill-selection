"""Inspect the selected Python runtime; never install dependencies or assume browser access."""
from __future__ import annotations
import importlib.util
import json
import shutil
import sys


def main() -> int:
    supported = sys.version_info >= (3, 10)
    pillow = importlib.util.find_spec("PIL") is not None
    print(json.dumps({
        "python": sys.executable, "version": sys.version.split()[0],
        "python_supported": supported, "pillow": pillow,
        "image_publish_ready": supported and pillow,
        "ffmpeg": shutil.which("ffmpeg"), "ffprobe": shutil.which("ffprobe"),
        "browser_session": "must_be_verified_by_agent",
        "vision": "must_be_verified_by_agent", "asr": "optional_external_capability",
    }, ensure_ascii=False, indent=2))
    return 0 if supported and pillow else 2


if __name__ == "__main__":
    raise SystemExit(main())
