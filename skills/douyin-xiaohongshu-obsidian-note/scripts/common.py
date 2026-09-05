from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any


CONFIG_ENV = "DOUYIN_XIAOHONGSHU_OBSIDIAN_NOTE_CONFIG"
CONFIG_VERSION = 1
FORBIDDEN_HEADINGS = re.compile(
    r"^#{1,6}\s*[^\n]*(?:逐字稿|全文转录|完整转录|字幕全文|全文字幕|可迁移.*自检清单|实践清单|自测题|自检清单)[^\n]*$",
    re.MULTILINE | re.IGNORECASE,
)


def config_path() -> Path:
    override = os.environ.get(CONFIG_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".config" / "douyin-xiaohongshu-obsidian-note" / "config.json").resolve()


def read_json(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(payload, encoding="utf-8", newline="\n")
    os.replace(temp_path, path)


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def discover_vault_root(path: Path) -> Path | None:
    current = path.resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".obsidian").is_dir():
            return candidate
    return None


def load_config(required: bool = True) -> dict[str, Any] | None:
    path = config_path()
    if not path.is_file():
        if required:
            raise FileNotFoundError(f"Configuration not found: {path}")
        return None
    config = read_json(path)
    for key in ("note_dir", "image_dir", "vault_root"):
        if not isinstance(config.get(key), str) or not config[key]:
            raise ValueError(f"Invalid configuration key: {key}")
    note_dir = Path(config["note_dir"]).resolve()
    image_dir = Path(config["image_dir"]).resolve()
    vault_root = Path(config["vault_root"]).resolve()
    if not (vault_root / ".obsidian").is_dir():
        raise ValueError(f"Configured vault no longer contains .obsidian: {vault_root}")
    if not is_within(note_dir, vault_root) or not is_within(image_dir, vault_root):
        raise ValueError("Configured note and image directories must be inside the same vault")
    return config


def sanitize_title(value: str, max_length: int = 56) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    kept: list[str] = []
    for char in normalized:
        if char.isalnum() or char in "_-":
            kept.append(char)
    result = "".join(kept).strip("._-")
    if not result:
        result = "短内容图文笔记"
    result = result[:max_length].rstrip("._-")
    reserved = {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if result.upper() in reserved:
        result = f"笔记_{result}"
    return result


def yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def local_timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return {}, normalized
    end = normalized.find("\n---\n", 4)
    if end < 0:
        raise ValueError("Unterminated YAML frontmatter")
    attributes: dict[str, str] = {}
    for line in normalized[4:end].splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        value = raw_value.strip()
        if value.startswith('"') and value.endswith('"'):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
        attributes[key.strip()] = value
    return attributes, normalized[end + 5 :]


def validation_issues(text: str, note_path: Path, vault_root: Path) -> list[str]:
    issues: list[str] = []
    attributes, body = split_frontmatter(text)
    required = ["title", "category", "url", "origin", "cover", "author", "publishTime", "createTime"]
    missing = [key for key in required if key not in attributes]
    if missing:
        issues.append("missing frontmatter keys: " + ", ".join(missing))
    if FORBIDDEN_HEADINGS.search(body):
        issues.append("contains a forbidden transcript/checklist heading")
    if "{{image:" in body:
        issues.append("contains unresolved image placeholders")
    if "file:///" in body.lower():
        issues.append("contains file:/// links")
    if re.search(r"!\[[^\]]*\]\([^)]*\)", body):
        issues.append("contains Markdown image syntax; use local Obsidian wiki embeds")
    timestamp_lines = re.findall(r"(?m)^\s*(?:\[)?\d{1,2}:\d{2}(?::\d{2})?(?:\])?\s+", body)
    if len(timestamp_lines) > 30:
        issues.append("looks like a timestamp-heavy transcript dump")
    embeds = re.findall(r"!\[\[([^\]|#]+)", body)
    if not embeds:
        issues.append("contains no local Obsidian image embeds")
    for embed in embeds:
        relative = Path(embed.replace("/", os.sep))
        if relative.is_absolute():
            issues.append(f"image embed must be vault-relative: {embed}")
            continue
        target = (vault_root / relative).resolve()
        if not is_within(target, vault_root):
            issues.append(f"image embed escapes the vault: {embed}")
        elif not target.is_file():
            issues.append(f"image embed target does not exist: {embed}")
    cover = attributes.get("cover", "")
    if cover:
        cover_path = (vault_root / Path(cover.replace("/", os.sep))).resolve()
        if not is_within(cover_path, vault_root) or not cover_path.is_file():
            issues.append("frontmatter cover does not resolve to a local vault image")
    if re.search(r"(?i)\.(?:mp4|mov|mkv|webm|wav|mp3)(?:\)|\]|\s|$)", body):
        issues.append("contains a video or audio file link")
    if note_path.suffix.lower() != ".md":
        issues.append("note must use the .md extension")
    return issues
