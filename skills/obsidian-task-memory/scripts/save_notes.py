"""Preview and create immutable Markdown notes. No network or transcript access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

import yaml


class Invalid(ValueError):
    pass


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise Invalid("YAML keys must be unique strings")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def relative(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise Invalid("Use a nonempty relative path with forward slashes")
    parts = value.split("/")
    for part in parts:
        if (part in ("", ".", "..") or part.startswith(".") or
                part.endswith((" ", ".")) or
                re.search(r'[<>:"|?*\x00-\x1f\x7f]', part) or
                re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", part.split(".")[0], re.I)):
            raise Invalid(f"Unsafe path component: {part!r}")
    return Path(*parts)


def reject_links(path):
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise Invalid(f"Symbolic links/reparse points are unsupported: {item}")


def contained(root, path):
    reject_links(path)
    if not path.resolve().is_relative_to(root.resolve()):
        raise Invalid(f"Path escapes permitted root: {path}")


def prose_only(body):
    lines, fence = [], None
    for line in body.splitlines():
        match = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
                fence = None
        elif match:
            fence = match[1]
        else:
            lines.append(re.sub(r"`+[^`]*`+", "", line))
    if fence:
        raise Invalid("Unclosed code fence")
    return "\n".join(lines)


def parse_note(content):
    if not isinstance(content, str) or not content.startswith("---\n") or "\x00" in content:
        raise Invalid("Note must be UTF-8 text with LF YAML frontmatter")
    parts = content.split("\n---\n", 1)
    if len(parts) != 2:
        raise Invalid("Missing frontmatter end")
    metadata = yaml.load(parts[0][4:], Loader=UniqueLoader)
    if not isinstance(metadata, dict):
        raise Invalid("Frontmatter must be a mapping")
    for key in ("id", "task_id", "type", "created", "status", "summary", "source_scope"):
        if not isinstance(metadata.get(key), str) or not metadata[key].strip():
            raise Invalid(f"Missing/non-string metadata: {key}")
    from datetime import datetime
    try:
        timestamp = datetime.fromisoformat(metadata["created"])
        if timestamp.tzinfo is None:
            raise ValueError()
    except ValueError:
        raise Invalid("created must be ISO 8601 with timezone") from None
    if metadata["type"] not in ("session", "decision", "prompt", "code", "lesson"):
        raise Invalid("Invalid note type")
    statuses = ("active", "paused", "blocked", "completed", "cancelled") if metadata["type"] == "session" else ("draft", "observed", "verified", "deprecated")
    if metadata["status"] not in statuses:
        raise Invalid("Invalid status for note type")
    if not isinstance(metadata.get("tags"), list) or not all(isinstance(x, str) and x.strip() for x in metadata["tags"]):
        raise Invalid("tags must be a string list")
    if not parts[1].strip():
        raise Invalid("Empty note body")
    return metadata, prose_only(parts[1])


def plan(manifest):
    if not isinstance(manifest, dict) or set(manifest) != {"vault_root", "archive_root", "notes"}:
        raise Invalid("Manifest requires only vault_root, archive_root, notes")
    vault = Path(manifest["vault_root"])
    if not vault.is_absolute() or not vault.is_dir():
        raise Invalid("vault_root must be an existing absolute directory")
    reject_links(vault)
    vault = vault.resolve()
    archive = vault / relative(manifest["archive_root"])
    contained(vault, archive)
    notes = manifest["notes"]
    if not isinstance(notes, list) or not notes:
        raise Invalid("notes must be a nonempty list")
    prepared, names, ids = [], set(), set()
    for note in notes:
        if not isinstance(note, dict) or set(note) != {"path", "content"}:
            raise Invalid("Each note requires only path and content")
        rel = relative(note["path"])
        if rel.suffix != ".md":
            raise Invalid("Only .md notes are supported")
        target = archive / rel
        contained(archive, target)
        key = str(target).casefold()
        if key in names:
            raise Invalid("Duplicate/case-colliding destination")
        names.add(key)
        metadata, prose = parse_note(note["content"])
        if metadata["id"] in ids:
            raise Invalid("Duplicate note id in manifest")
        ids.add(metadata["id"])
        data = note["content"].encode("utf-8", errors="strict")
        if target.exists() and (not target.is_file() or target.read_bytes() != data):
            raise Invalid(f"Existing content conflict; preserved: {target}")
        prepared.append({"target": target, "data": data, "metadata": metadata, "prose": prose})
    planned = {x["target"] for x in prepared}
    for item in prepared:
        targets = []
        for link in re.findall(r"\[\[([^\]\n]+)\]\]", item["prose"]):
            target = link.split("|", 1)[0]
            if "#" in target:
                raise Invalid("Heading/block wikilinks need separate verification; use file links")
            targets.append(target if target.endswith(".md") else target + ".md")
        for prop in ("previous", "supersedes"):
            if prop in item["metadata"]:
                targets.append(item["metadata"][prop])
        for target in targets:
            resolved = vault / relative(target)
            contained(vault, resolved)
            if resolved == item["target"]:
                raise Invalid("Self-referential history/link")
            if resolved not in planned and not resolved.is_file():
                raise Invalid(f"Missing linked note: {resolved}")
    digest = hashlib.sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return digest, archive, prepared


def run(manifest, apply=False, expected=None):
    digest, archive, prepared = plan(manifest)
    result = {"digest": digest, "mode": "apply" if apply else "preview", "created": [], "unchanged": [], "planned": [str(x["target"]) for x in prepared]}
    if not apply:
        return result
    if expected != digest:
        raise Invalid("Manifest digest changed or missing; preview again")
    try:
        for item in prepared:
            target, data = item["target"], item["data"]
            contained(archive, target)
            if target.exists():
                if target.read_bytes() != data:
                    raise Invalid(f"Concurrent content change; preserved: {target}")
                result["unchanged"].append(str(target))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            contained(archive, target)
            fd, tempname = tempfile.mkstemp(prefix=".task-memory-", dir=target.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                contained(archive, target)
                try:
                    os.link(tempname, target)
                    result["created"].append(str(target))
                except FileExistsError:
                    reject_links(target)
                    if target.read_bytes() != data:
                        raise Invalid(f"Concurrent content conflict; preserved: {target}") from None
                    result["unchanged"].append(str(target))
                if target.read_bytes() != data:
                    raise Invalid(f"Readback mismatch: {target}")
            finally:
                Path(tempname).unlink(missing_ok=True)
        # Recheck links and bytes once all pages have been submitted.
        plan(manifest)
        result["verified"] = True
    except (OSError, ValueError, yaml.YAMLError) as error:
        result["error"] = str(error)
        result["verified"] = False
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expect")
    args = parser.parse_args()
    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        result = run(manifest, args.apply, args.expect)
    except (OSError, ValueError, TypeError, yaml.YAMLError) as error:
        result = {"error": str(error), "verified": False}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if "error" in result else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
