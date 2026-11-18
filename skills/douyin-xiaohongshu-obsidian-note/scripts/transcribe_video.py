"""Transcribe a local workspace video into timestamped text segments using offline faster-whisper or whisper."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

from common import is_within, local_timestamp, write_json
from run_workspace import validate_workspace


def available_asr_backend() -> str | None:
    if importlib.util.find_spec("faster_whisper") is not None:
        return "faster_whisper"
    if importlib.util.find_spec("whisper") is not None:
        return "openai_whisper"
    return None


def transcribe_with_faster_whisper(
    video_path: Path,
    model_size: str = "small",
    language: str = "zh",
) -> dict[str, Any]:
    from faster_whisper import WhisperModel

    model = None
    chosen_model = model_size
    for candidate in (model_size, "small", "base", "tiny"):
        try:
            model = WhisperModel(candidate, device="cpu", compute_type="int8", local_files_only=True)
            chosen_model = candidate
            break
        except Exception:
            continue
    if model is None:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        chosen_model = model_size

    segments_gen, info = model.transcribe(
        str(video_path),
        language=language,
        vad_filter=True,
        beam_size=5,
    )
    segments: list[dict[str, Any]] = []
    full_lines: list[str] = []
    for idx, seg in enumerate(segments_gen, start=1):
        text = (seg.text or "").strip()
        if not text:
            continue
        segments.append({
            "index": idx,
            "start": round(float(seg.start), 2),
            "end": round(float(seg.end), 2),
            "text": text,
        })
        full_lines.append(text)

    return {
        "backend": f"faster_whisper:{chosen_model}",
        "language": getattr(info, "language", language),
        "duration": round(float(getattr(info, "duration", 0.0) or 0.0), 3),
        "segment_count": len(segments),
        "text": "\n".join(full_lines),
        "segments": segments,
        "transcribed_at": local_timestamp(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True, help="Marked temporary workspace")
    parser.add_argument("--video", type=Path, required=True, help="Video or audio file inside --run-dir")
    parser.add_argument("--output", type=Path, required=True, help="Output transcript JSON path inside --run-dir")
    parser.add_argument("--model", default="small", help="Whisper model size (default: small)")
    parser.add_argument("--language", default="zh", help="Language code (default: zh)")
    args = parser.parse_args()

    run_dir = args.run_dir.expanduser().resolve()
    validate_workspace(run_dir)
    video_path = args.video.expanduser().resolve()
    output_path = args.output.expanduser().resolve()

    if not is_within(video_path, run_dir) or not is_within(output_path, run_dir):
        raise SystemExit("Video input and transcript output must stay inside the marked run workspace")
    if not video_path.is_file():
        raise SystemExit(f"Video file not found: {video_path}")

    backend = available_asr_backend()
    if backend == "faster_whisper":
        payload = transcribe_with_faster_whisper(video_path, model_size=args.model, language=args.language)
    elif backend == "openai_whisper":
        import whisper
        m = whisper.load_model(args.model)
        res = m.transcribe(str(video_path), language=args.language)
        segs = [
            {
                "index": i,
                "start": round(float(s.get("start", 0.0)), 2),
                "end": round(float(s.get("end", 0.0)), 2),
                "text": (s.get("text") or "").strip(),
            }
            for i, s in enumerate(res.get("segments", []), start=1)
            if (s.get("text") or "").strip()
        ]
        payload = {
            "backend": f"openai_whisper:{args.model}",
            "language": args.language,
            "segment_count": len(segs),
            "text": "\n".join(s["text"] for s in segs),
            "segments": segs,
            "transcribed_at": local_timestamp(),
        }
    else:
        raise SystemExit("No local ASR backend (faster_whisper or whisper) found in current Python environment")

    write_json(output_path, payload)
    print(
        json.dumps(
            {
                "transcribed": True,
                "backend": payload["backend"],
                "segment_count": payload["segment_count"],
                "output": str(output_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
