"""Publish inspected local evidence as an Obsidian note; no network or model dependency."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
import sys
import tempfile
import warnings
from pathlib import Path
from typing import Any

from common import (FORBIDDEN_HEADINGS, is_within, load_config, local_timestamp,
                    read_json, sanitize_title, split_frontmatter, validation_issues, yaml_string)
from run_workspace import validate_workspace
from sources import canonical_source, classify

PLACEHOLDER = re.compile(r"\{\{image:([1-9][0-9]*)\}\}")
PRIVATE_LINK = re.compile(r"(?i)xsec_token|xsec_source|[?&](?:auth_token|access_token|signature)=")


def existing_notes(note_dir: Path) -> dict[tuple[str, str], Path]:
    note_dir = note_dir.resolve()
    result: dict[tuple[str, str], Path] = {}
    for path in sorted(note_dir.rglob("*.md")):
        if not is_within(path, note_dir):
            continue
        try:
            attributes, _ = split_frontmatter(path.read_text(encoding="utf-8-sig"))
        except (UnicodeError, ValueError):
            continue
        source = classify(attributes.get("url", ""))
        if source["kind"] == "note":
            result.setdefault((source["platform"], source["note_id"]), path)
    return result


def safe_run_file(value: str, run_dir: Path) -> Path:
    path = Path(value)
    path = (path if path.is_absolute() else run_dir / path).resolve()
    if not is_within(path, run_dir) or not path.is_file():
        raise ValueError("Evidence and draft files must exist inside the marked run workspace")
    return path


def validate_evidence(meta: dict[str, Any], allow_partial: bool) -> tuple[dict[str, str], list[str]]:
    source = canonical_source(meta.get("source_url", ""))
    for key in ("title", "author", "publish_time", "content_basis"):
        if not isinstance(meta.get(key), str):
            raise ValueError(f"Metadata requires a string: {key}")
    if not meta["title"].strip():
        raise ValueError("An evidence-based title is required")
    date = meta["publish_time"]
    if date:
        from datetime import date as calendar_date
        calendar_date.fromisoformat(date)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            raise ValueError("publish_time must be a verified YYYY-MM-DD date or empty")
    kind = meta.get("media_type")
    if kind not in {"gallery", "video", "mixed"}:
        raise ValueError("media_type must be gallery, video, or mixed, verified in the note container")
    if source["platform"] == "douyin" and kind != "video":
        raise ValueError("This combined skill currently supports Douyin video links; use video media_type")
    if meta["content_basis"] not in {"text_and_images", "subtitles_and_frames", "asr_and_frames", "visual_only"}:
        raise ValueError("Unknown content_basis")
    limitations = meta.get("limitations", [])
    if not isinstance(limitations, list) or any(not isinstance(x, str) or not x.strip() for x in limitations):
        raise ValueError("limitations must be an array of nonempty strings")
    limitations = list(limitations)
    partial = False
    if kind in {"gallery", "mixed"}:
        coverage = meta.get("gallery_coverage", {})
        count = coverage.get("expected_count")
        positions = coverage.get("reviewed_positions", [])
        if type(count) is not int or not 1 <= count <= 1000:
            raise ValueError("gallery_coverage.expected_count must be the observed image count")
        if not isinstance(positions, list) or any(type(p) is not int or not 1 <= p <= count for p in positions):
            raise ValueError("Invalid reviewed gallery positions")
        partial = set(positions) != set(range(1, count + 1))
        if partial:
            limitations.append(f"原帖共 {count} 张图片，本次仅核实 {len(set(positions))} 张；不代表完整原帖。")
    if kind in {"video", "mixed"}:
        duration = meta.get("video_duration_seconds")
        if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
            raise ValueError("Video requires the verified positive video_duration_seconds")
        partial = partial or meta.get("video_reviewed_to_end") is not True
        if meta.get("video_reviewed_to_end") is not True:
            limitations.append("未核实完整视频，以下内容仅限已查看的片段。")
        if meta["content_basis"] == "text_and_images":
            raise ValueError("Video requires subtitles/ASR and frames, or explicitly visual_only")
        if meta["content_basis"] == "visual_only":
            limitations.append("仅依据可见画面与原帖正文整理，未核实口播；不代表完整视频内容。")
    if partial and not allow_partial:
        raise ValueError("Incomplete evidence: finish reviewing or obtain consent for --allow-partial")
    if partial and not meta.get("limitations"):
        raise ValueError("Partial publication requires a concrete reason in limitations")
    assets = meta.get("assets")
    if not isinstance(assets, list) or not assets or len(assets) > 100:
        raise ValueError("Supply 1 to 100 selected, inspected image assets")
    for item in assets:
        if not isinstance(item, dict) or item.get("inspected") is not True:
            raise ValueError("Every selected asset must actually be visually inspected by the agent")
        if not isinstance(item.get("path"), str) or item.get("role") not in {"image", "frame"}:
            raise ValueError("Asset requires path and role (image/frame)")
        if not isinstance(item.get("caption"), str) or not item["caption"].strip():
            raise ValueError("Asset requires an evidence-based caption")
        if item["role"] == "image":
            if kind == "video" or type(item.get("position")) is not int or item.get("position") not in meta.get("gallery_coverage", {}).get("reviewed_positions", []):
                raise ValueError("Gallery image position must have been reviewed")
        else:
            seconds = item.get("timestamp_seconds")
            if kind == "gallery" or type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
                raise ValueError("Video frame needs a finite nonnegative timestamp_seconds")
            if seconds >= meta["video_duration_seconds"]:
                raise ValueError("Selected frame timestamp must be inside the actual video duration")
    if kind == "mixed" and {item["role"] for item in assets} != {"image", "frame"}:
        raise ValueError("Mixed-media notes require selected evidence from both images and video frames")
    return source, limitations


def image_payload(path: Path, role: str, frame_width: int) -> tuple[str, bytes]:
    from PIL import Image, ImageOps
    if path.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("Selected image exceeds 50 MiB; select a safe static image")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as probe:
            if probe.format not in {"JPEG", "PNG", "WEBP"} or getattr(probe, "n_frames", 1) != 1:
                raise ValueError("Only verified static JPEG/PNG/WebP images are supported; extract a still first")
            probe.verify()
        with Image.open(path) as original:
            max_width = frame_width if role == "frame" else 0
            oriented = ImageOps.exif_transpose(original)
            has_alpha = "A" in oriented.getbands() or "transparency" in oriented.info
            frame = oriented.convert("RGBA" if has_alpha and not max_width else "RGB")
            if max_width and frame.width > max_width:
                frame = frame.resize((max_width, max(1, round(frame.height * max_width / frame.width))), Image.Resampling.LANCZOS)
            # PNG retains fine text; JPEG is used for resized video frames.
            # Re-encoding strips EXIF/GPS and comments, while _0 preserves pixel dimensions.
            extension = "jpg" if max_width else "png"
            buffer = io.BytesIO()
            frame.info.clear()
            frame.save(buffer, format="JPEG" if max_width else "PNG", **({"quality": 95} if max_width else {}))
    payload = buffer.getvalue()
    digest = hashlib.md5(payload, usedforsecurity=False).hexdigest()
    return f"{digest}_{max_width}.{extension}", payload


def publish(manifest: Path, draft: Path, run_dir: Path, *, allow_partial: bool = False,
            frame_width: int = 0) -> dict[str, Any]:
    validate_workspace(run_dir)
    run_dir = run_dir.resolve()
    manifest = safe_run_file(str(manifest.resolve()), run_dir)
    draft = safe_run_file(str(draft.resolve()), run_dir)
    meta = read_json(manifest)
    source, limitations = validate_evidence(meta, allow_partial)
    config = load_config()
    vault = Path(config["vault_root"]).resolve()
    note_dir, image_dir = Path(config["note_dir"]).resolve(), Path(config["image_dir"]).resolve()
    if is_within(vault, run_dir) or is_within(run_dir, vault):
        raise ValueError("Temporary workspace and permanent vault must be separate")
    for output in (note_dir, image_dir):
        if not output.is_dir():
            raise ValueError("Configured output directory is missing; reconfigure first")
        if any(char in output.relative_to(vault).as_posix() for char in "[]|#\n\r"):
            raise ValueError("Output path contains unsupported Obsidian embed delimiters")
    if frame_width not in {0, 640, 1280, 1920}:
        raise ValueError("frame_width must be 0, 640, 1280, or 1920")
    body = draft.read_text(encoding="utf-8-sig").strip()
    if not body or body.startswith("---") or FORBIDDEN_HEADINGS.search(body):
        raise ValueError("Draft must be a substantive body without frontmatter or transcript/checklist headings")
    if re.search(r"(?m)^\s*[-*+]\s+\[[ xX]\]", body):
        raise ValueError("Do not add self-test/task checklists to the note")
    if "![[" in body or re.search(r"!\[[^\]]*\]\(", body):
        raise ValueError("Use {{image:N}} placeholders, not existing or remote image embeds")
    if PRIVATE_LINK.search(body + json.dumps(meta.get("limitations", []), ensure_ascii=False)):
        raise ValueError("Remove signed/private access parameters from the final note")
    indices = [int(match.group(1)) for match in PLACEHOLDER.finditer(body)]
    if set(indices) != set(range(1, len(meta["assets"]) + 1)):
        raise ValueError("Every selected asset must be embedded, and every placeholder must resolve")
    assets = [(item, *image_payload(safe_run_file(item["path"], run_dir), item["role"], frame_width))
              for item in meta["assets"]]
    created_images: list[Path] = []
    temp_note: Path | None = None
    committed = False
    # A vault-level exclusive lock protects shared content-addressed images as well as notes.
    lock_path = vault / ".douyin-xiaohongshu-obsidian-note.publish.lock"
    with lock_path.open("x", encoding="utf-8", newline="\n") as lock:
        lock.write(json.dumps({"pid": os.getpid(), "created_at": local_timestamp()}))
    try:
        existing = existing_notes(note_dir).get((source["platform"], source["note_id"]))
        if existing:
            return {"status": "skipped_existing", "note": str(existing), "note_id": source["note_id"]}
        title = sanitize_title(meta["title"])
        note_path = note_dir / f"{title}.md"
        if note_path.exists():
            note_path = note_dir / f"{title}_{source['note_id']}.md"
        if note_path.exists():
            raise FileExistsError("Target filename already exists; no overwrite is permitted")
        relative_images: list[str] = []
        for item, name, payload in assets:
            target = image_dir / name
            if target.is_symlink() or not is_within(target, image_dir):
                raise ValueError("Image target cannot be a symlink or escape the image directory")
            if target.exists():
                if target.read_bytes() != payload:
                    raise ValueError("Image hash collision or corrupted existing image; refusing overwrite")
            else:
                with target.open("xb") as image_file:
                    created_images.append(target)
                    image_file.write(payload)
            relative_images.append(target.relative_to(vault).as_posix())

        def embed(match: re.Match[str]) -> str:
            index = int(match.group(1)) - 1
            caption = " ".join(meta["assets"][index]["caption"].splitlines())
            return f"![[{relative_images[index]}]]\n\n> {caption}"

        body = PLACEHOLDER.sub(embed, body)
        if limitations:
            body += "\n\n## 材料边界\n\n" + "\n".join(f"- {line}" for line in limitations)
        origin = "抖音" if source["platform"] == "douyin" else "小红书"
        source_label = "抖音原视频" if source["platform"] == "douyin" else "小红书原笔记"
        category = ("抖音视频笔记" if source["platform"] == "douyin" else
                    "小红书图文笔记" if meta["media_type"] == "gallery" else
                    "小红书视频笔记" if meta["media_type"] == "video" else "小红书混合笔记")
        body += f"\n\n## 来源\n\n[{source_label}]({source['canonical_url']})\n"
        attrs = {"title": meta["title"].strip(), "category": category,
                 "url": source["canonical_url"], "origin": origin, "cover": relative_images[0],
                 "author": meta["author"], "publishTime": meta["publish_time"], "createTime": local_timestamp()}
        result_text = "---\n" + "\n".join(f"{key}: {yaml_string(value)}" for key, value in attrs.items()) + "\n---\n\n" + body
        if PRIVATE_LINK.search(result_text):
            raise ValueError("Final note contains a signed/private access parameter")
        issues = validation_issues(result_text, note_path, vault)
        if issues:
            raise ValueError("; ".join(issues))
        fd, temp_name = tempfile.mkstemp(prefix=".social-note-publish-", suffix=".tmp", dir=note_dir)
        temp_note = Path(temp_name)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            output.write(result_text)
            output.flush()
            os.fsync(output.fileno())
        if temp_note.read_text(encoding="utf-8") != result_text:
            raise ValueError("UTF-8 read-back mismatch")
        # Hard-link creation is atomic and refuses an existing destination, unlike replace().
        # Unsupported/network filesystems fail safely; do not silently fall back to overwrite.
        os.link(temp_note, note_path)
        committed = True
        return {"status": "published", "note": str(note_path), "note_id": source["note_id"],
                "images": relative_images, "limitations": limitations}
    finally:
        try:
            if temp_note is not None:
                temp_note.unlink(missing_ok=True)
            if not committed:
                for image_path in created_images:
                    image_path.unlink(missing_ok=True)
        finally:
            lock_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--frame-width", type=int, choices=[0, 640, 1280, 1920], default=0)
    args = parser.parse_args()
    result = publish(args.manifest, args.draft, args.run_dir,
                     allow_partial=args.allow_partial, frame_width=args.frame_width)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        print(f"Publication stopped: {exc}", file=sys.stderr)
        raise SystemExit(2)
