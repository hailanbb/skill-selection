from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from common import (
    FORBIDDEN_HEADINGS,
    is_within,
    load_config,
    local_timestamp,
    sanitize_title,
    split_frontmatter,
    validation_issues,
    yaml_string,
)


PLACEHOLDER = re.compile(r"\{\{image:(\d+)(?:\|([^}]+))?\}\}")


def normalized_image(source: Path, destination_dir: Path, ffmpeg: str | None) -> tuple[Path, bool]:
    if not source.is_file():
        raise FileNotFoundError(f"Image not found: {source}")
    destination_dir.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageOps

        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            if image.width > 640:
                height = max(1, round(image.height * 640 / image.width))
                image = image.resize((640, height), Image.Resampling.LANCZOS)
            with tempfile.TemporaryDirectory(prefix="douyin-note-image-") as temp_dir:
                converted = Path(temp_dir) / "frame.jpg"
                image.save(converted, format="JPEG", quality=92, optimize=True)
                payload = converted.read_bytes()
        digest = hashlib.md5(payload).hexdigest()
        target = destination_dir / f"{digest}_640.jpg"
        created = not target.exists()
        if created:
            target.write_bytes(payload)
        return target, created
    except (ImportError, OSError):
        pass
    if ffmpeg:
        with tempfile.TemporaryDirectory(prefix="douyin-note-image-") as temp_dir:
            converted = Path(temp_dir) / "frame.jpg"
            subprocess.run(
                [
                    ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(source), "-frames:v", "1",
                    "-vf", "scale=640:-2:force_original_aspect_ratio=decrease", "-q:v", "2", "-y", str(converted),
                ],
                check=True,
            )
            payload = converted.read_bytes()
            digest = hashlib.md5(payload).hexdigest()
            target = destination_dir / f"{digest}_640.jpg"
            created = not target.exists()
            if created:
                target.write_bytes(payload)
            return target, created
    payload = source.read_bytes()
    digest = hashlib.md5(payload).hexdigest()
    suffix = source.suffix.lower() if source.suffix else ".bin"
    target = destination_dir / f"{digest}_0{suffix}"
    created = not target.exists()
    if created:
        target.write_bytes(payload)
    return target, created


def choose_note_path(note_dir: Path, slug: str, source_url: str) -> Path:
    preferred = note_dir / f"{slug}.md"
    if not preferred.exists():
        return preferred
    try:
        attributes, _ = split_frontmatter(preferred.read_text(encoding="utf-8"))
        if attributes.get("url") == source_url:
            raise FileExistsError(f"A note for this source already exists: {preferred}")
    except UnicodeDecodeError:
        pass
    digest = hashlib.sha1(source_url.encode("utf-8")).hexdigest()[:8]
    candidate = note_dir / f"{slug}_{digest}.md"
    index = 2
    while candidate.exists():
        try:
            attributes, _ = split_frontmatter(candidate.read_text(encoding="utf-8"))
            if attributes.get("url") == source_url:
                raise FileExistsError(f"A note for this source already exists: {candidate}")
        except UnicodeDecodeError:
            pass
        candidate = note_dir / f"{slug}_{digest}_{index}.md"
        index += 1
    return candidate


def render_body(raw: str, title: str, image_paths: list[str]) -> str:
    _, body = split_frontmatter(raw)
    body = body.strip()
    if FORBIDDEN_HEADINGS.search(body):
        raise ValueError("Draft contains a forbidden transcript/checklist heading")
    if not re.search(r"(?m)^#\s+", body):
        body = f"# {title}\n\n{body}"
    used: set[int] = set()

    def replace(match: re.Match[str]) -> str:
        index = int(match.group(1))
        if index < 1 or index > len(image_paths):
            raise ValueError(f"Image placeholder out of range: {index}")
        used.add(index)
        caption = (match.group(2) or "").strip()
        rendered = f"![[{image_paths[index - 1]}]]"
        if caption:
            rendered += f"\n*{caption}*"
        return rendered

    body = PLACEHOLDER.sub(replace, body)
    unused = [index for index in range(1, len(image_paths) + 1) if index not in used]
    if unused:
        body += "\n\n## 关键画面\n\n" + "\n\n".join(f"![[{image_paths[index - 1]}]]" for index in unused)
    return body.rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish a distilled Douyin note and selected frames into Obsidian")
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--author", default="")
    parser.add_argument("--publish-time", default="")
    parser.add_argument("--category", default="video")
    parser.add_argument("--origin", default="抖音")
    parser.add_argument("--images", nargs="+", type=Path, required=True)
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg"))
    args = parser.parse_args()

    config = load_config(required=True)
    assert config is not None
    note_dir = Path(config["note_dir"]).resolve()
    image_root = Path(config["image_dir"]).resolve()
    vault_root = Path(config["vault_root"]).resolve()
    note_dir.mkdir(parents=True, exist_ok=True)
    image_root.mkdir(parents=True, exist_ok=True)
    if not is_within(note_dir, vault_root) or not is_within(image_root, vault_root):
        raise SystemExit("Configured output paths are outside the Obsidian vault")

    draft = args.draft.expanduser().resolve()
    raw_body = draft.read_text(encoding="utf-8")
    slug = sanitize_title(args.title)
    image_dir = image_root / slug
    note_path = choose_note_path(note_dir, slug, args.source_url)
    render_body(raw_body, args.title, [f"__image_{index}.jpg" for index in range(1, len(args.images) + 1)])
    published_images: list[Path] = []
    newly_created: list[Path] = []
    try:
        for source in args.images:
            published, created = normalized_image(source.expanduser().resolve(), image_dir, args.ffmpeg)
            published_images.append(published)
            if created:
                newly_created.append(published)
        relative_images = [path.relative_to(vault_root).as_posix() for path in published_images]
        body = render_body(raw_body, args.title, relative_images)
        frontmatter_values = [
            ("title", args.title.strip()),
            ("category", args.category.strip()),
            ("url", args.source_url.strip()),
            ("origin", args.origin.strip()),
            ("cover", relative_images[0]),
            ("author", args.author.strip()),
            ("publishTime", args.publish_time.strip()),
            ("createTime", local_timestamp()),
        ]
        frontmatter = "---\n" + "\n".join(f"{key}: {yaml_string(value)}" for key, value in frontmatter_values) + "\n---\n\n"
        content = frontmatter + body
        issues = validation_issues(content, note_path, vault_root)
        if issues:
            raise ValueError("Validation failed before publish: " + "; ".join(issues))

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False, dir=note_dir, prefix=f".{slug}-", suffix=".tmp") as handle:
            handle.write(content)
            temp_path = Path(handle.name)
        try:
            os.replace(temp_path, note_path)
        finally:
            if temp_path.exists():
                temp_path.unlink()
    except Exception:
        if not note_path.exists():
            for path in newly_created:
                path.unlink(missing_ok=True)
            if image_dir.is_dir() and not any(image_dir.iterdir()):
                image_dir.rmdir()
        raise
    print(json.dumps({"note_path": str(note_path), "images": [str(path) for path in published_images]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileExistsError, FileNotFoundError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
