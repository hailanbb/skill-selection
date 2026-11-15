from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

from common import is_within, local_timestamp, write_json
from run_workspace import validate_workspace


def parse_time(value: str) -> float:
    parts = value.split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid timestamp: {value}") from exc
    raise argparse.ArgumentTypeError(f"Invalid timestamp: {value}")


def probe_duration(video: Path, ffprobe: str) -> float:
    completed = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=60,
    )
    payload = json.loads(completed.stdout)
    return float(payload["format"]["duration"])


def detect_scene_changes(video: Path, ffmpeg: str, threshold: float = 0.3) -> list[float]:
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(video),
        "-vf", f"select='gt(scene\\,{threshold:.2f})',showinfo",
        "-f", "null", "-",
    ]
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        matches = re.findall(r"pts_time:(\d+(?:\.\d+)?)", completed.stderr)
        return sorted({round(float(ts), 3) for ts in matches})
    except (subprocess.SubprocessError, OSError):
        return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract review candidates or timestamped keyframes from a local video")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True, help="Marked workspace containing video and output")
    parser.add_argument("--auto-count", type=int, default=16)
    parser.add_argument("--at", action="append", type=parse_time, default=[])
    parser.add_argument("--mode", choices=["auto", "scene", "interval"], default="auto",
                        help="Candidate selection: scene (scene detection), interval (uniform), or auto (hybrid)")
    parser.add_argument("--scene-threshold", type=float, default=0.3,
                        help="Scene change detection sensitivity (0.0 to 1.0, default 0.3)")
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "ffmpeg")
    parser.add_argument("--ffprobe", default=shutil.which("ffprobe") or "ffprobe")
    args = parser.parse_args()

    run_dir = args.run_dir.expanduser().resolve()
    validate_workspace(run_dir)
    video = args.video.expanduser().resolve()
    out_dir = args.out_dir.expanduser().resolve()
    if not is_within(video, run_dir) or not is_within(out_dir, run_dir):
        raise SystemExit("Video and frame output must stay inside the marked run workspace")
    if not video.is_file():
        raise SystemExit(f"Video not found: {video}")
    if args.auto_count < 1 or args.auto_count > 60:
        raise SystemExit("--auto-count must be between 1 and 60")
    duration = probe_duration(video, args.ffprobe)
    if not math.isfinite(duration) or duration <= 0:
        raise SystemExit("Video duration must be positive")

    actual_mode = args.mode
    scene_detected_count = 0
    if args.at:
        times = sorted({round(value, 3) for value in args.at if 0 <= value < duration})
        actual_mode = "manual"
    elif args.mode == "interval":
        count = min(args.auto_count, max(1, int(duration)))
        times = [round((index + 0.5) * duration / count, 3) for index in range(count)]
    else:  # auto or scene
        scenes = [t for t in detect_scene_changes(video, args.ffmpeg, args.scene_threshold) if 0 <= t < duration]
        scene_detected_count = len(scenes)
        if args.mode == "scene":
            if not scenes:
                raise SystemExit("No scene changes detected at the given threshold")
            if len(scenes) > args.auto_count:
                step = (len(scenes) - 1) / (args.auto_count - 1) if args.auto_count > 1 else 1.0
                times = [scenes[round(i * step)] for i in range(args.auto_count)]
            else:
                times = scenes
        else:  # auto mode: hybrid
            min_needed = min(max(3, args.auto_count // 3), args.auto_count)
            if len(scenes) >= min_needed:
                if len(scenes) > args.auto_count:
                    step = (len(scenes) - 1) / (args.auto_count - 1) if args.auto_count > 1 else 1.0
                    times = [scenes[round(i * step)] for i in range(args.auto_count)]
                else:
                    interval_candidates = [round((index + 0.5) * duration / args.auto_count, 3)
                                           for index in range(args.auto_count)]
                    combined = set(scenes)
                    for cand in interval_candidates:
                        if not any(abs(cand - s) < 1.0 for s in scenes):
                            combined.add(cand)
                    times = sorted(combined)[:args.auto_count]
            else:
                count = min(args.auto_count, max(1, int(duration)))
                times = [round((index + 0.5) * duration / count, 3) for index in range(count)]

    if not times:
        raise SystemExit("No valid timestamps to extract")

    out_dir.mkdir(parents=True, exist_ok=True)
    frames: list[dict[str, object]] = []
    for index, timestamp in enumerate(times, start=1):
        millis = int(round(timestamp * 1000))
        output = out_dir / f"candidate_{index:03d}_{millis:09d}ms.jpg"
        subprocess.run(
            [
                args.ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{timestamp:.3f}",
                "-i", str(video), "-frames:v", "1", "-vf", "scale='min(1920,iw)':-2",
                "-q:v", "2", "-y", str(output),
            ],
            check=True,
            timeout=120,
        )
        frames.append({"index": index, "timestamp_seconds": timestamp, "path": str(output)})
    manifest = {
        "video": str(video), "duration_seconds": round(duration, 3),
        "mode": actual_mode, "scene_detected_count": scene_detected_count,
        "created_at": local_timestamp(), "frames": frames
    }
    manifest_path = out_dir / "candidates.json"
    write_json(manifest_path, manifest)
    print(json.dumps({"count": len(frames), "manifest": str(manifest_path), "mode": actual_mode}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
