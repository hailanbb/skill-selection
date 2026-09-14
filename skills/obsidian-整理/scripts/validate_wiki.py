#!/usr/bin/env python3
"""Read-only structural/content gates; not a semantic or external fact checker."""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import re
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

try:
    import yaml
    if not callable(getattr(yaml, "safe_load", None)):
        raise ImportError("incomplete yaml module")
except ImportError as exc:
    raise SystemExit("PyYAML is required; validation did not run.") from exc


class UniqueLoader(yaml.SafeLoader):
    """Reject duplicate keys instead of silently overwriting metadata."""


def mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)


def read_note(path):
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError("Missing frontmatter")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise ValueError("Unclosed frontmatter")
    data = yaml.load("".join(lines[1:end]), Loader=UniqueLoader)
    if not isinstance(data, dict):
        raise ValueError("Frontmatter must be a mapping")
    return data, "".join(lines[end + 1:])


def section(body, heading):
    match = re.search(r"^##\s+" + re.escape(heading) + r"\s*\n(.*?)(?=^##\s|\Z)", body, re.M | re.S)
    return match.group(1).strip() if match else ""


def links(text):
    # Code examples are not navigable links.
    text = re.sub(r"(?ms)^\s*(`{3,}|~{3,}).*?^\s*\1\s*$", "", text)
    text = re.sub(r"`+[^`\n]*`+", "", text)
    return [s.split("|", 1)[0].split("#", 1)[0].strip()
            for s in re.findall(r"\[\[([^\]\n]+)\]\]", text)]


def valid_rel_path(value):
    """Return a canonical vault-relative POSIX path, or None."""
    if (not isinstance(value, str) or not value or any(ch in value for ch in '\\#|:*?"<>')
            or any(ord(ch) < 32 for ch in value)):
        return None
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        return None
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return None
    path = PurePosixPath(value)
    if path.as_posix() != value:
        return None
    return value


def nonempty_string_list(value):
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) and item.strip() for item in value)


def aliases_list(value):
    return (isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)
            and len(set(value)) == len(value))


def audit(vault, wiki="04 wiki", archive="06 已归档", today=None):
    vault = Path(vault).resolve()
    w, a = vault / wiki, vault / archive
    if not w.is_dir() or not a.is_dir():
        raise ValueError("Wiki and archive directories must exist")
    today = today or dt.date.today()
    month = today.year * 12 + today.month - 1 - 6
    year, mon = divmod(month, 12)
    cutoff = dt.date(year, mon + 1, min(today.day, calendar.monthrange(year, mon + 1)[1]))
    pages = sorted(w.rglob("*.md")); originals = set(a.rglob("*.md"))
    candidates = pages + sorted(originals)
    issues = []; warnings = []; inbound = Counter(); mapped = defaultdict(list)
    valid_sources = set(); source_total = 0
    parsed = {}
    object_ids = defaultdict(list)

    def issue(path, code, detail=""):
        issues.append({"path": path.relative_to(vault).as_posix(), "code": code, "detail": detail})

    def resolve(target, page):
        if not target:
            return []
        name = target if target.endswith(".md") else target + ".md"
        # Prefer document-relative, vault-relative, then wiki-relative paths.
        for candidate in (page.parent / name, vault / name, w / name):
            resolved = candidate.resolve()
            if resolved.is_relative_to(vault) and resolved.is_file():
                return [resolved]
        return [p for p in candidates if p.relative_to(vault).as_posix().casefold().endswith("/" + name.casefold())]

    for page in pages:
        start = len(issues)
        try:
            data, body = read_note(page)
        except (ValueError, OSError, UnicodeError, yaml.YAMLError) as exc:
            issue(page, "parse_error", str(exc)); continue
        parsed[page] = (data, body)
        expected = {"sources": "source", "concepts": "concept", "entities": "entity", "insights": "insight"}.get(page.parent.name)
        if page.name == "index.md" and re.search(r"原始资料未提供(?:摘要|结构化要点)", body):
            issue(page, "index_placeholder")
        page_type = data.get("type")
        redirect_allowed = page.parent.name in ("entities", "concepts") and page_type == "redirect"
        if not isinstance(page_type, str) or not page_type or (expected and page_type != expected and not redirect_allowed):
            issue(page, "invalid_type")
        try:
            date = dt.date.fromisoformat(str(data["last_updated"]))
            if date < cutoff:
                warnings.append({"path": str(page.relative_to(vault)), "code": "stale"})
        except (KeyError, ValueError):
            issue(page, "invalid_last_updated")
        targets = links(body)
        source_refs = set()
        for target in targets:
            if not target:
                continue
            matches = resolve(target, page)
            if len(matches) != 1:
                issue(page, "broken_link" if not matches else "ambiguous_link", target)
            elif matches[0] != page:
                inbound[matches[0]] += 1
                if matches[0].parent == w / "sources":
                    source_refs.add(matches[0])
        if "source_count" in data and data["source_count"] != len(source_refs):
            issue(page, "source_count_mismatch", f"declared={data['source_count']}, actual={len(source_refs)}")
        if page_type in ("entity", "concept"):
            new_fields = {"knowledge_schema", "object_id", "identity_evidence", "source_refs"}
            if any(field in data for field in new_fields):
                if data.get("knowledge_schema") != 1 or not isinstance(data.get("knowledge_schema"), int) or isinstance(data.get("knowledge_schema"), bool):
                    issue(page, "invalid_knowledge_schema")
                if not isinstance(data.get("object_id"), str) or not data["object_id"].strip():
                    issue(page, "invalid_object_id")
                elif data["object_id"]:
                    object_ids[data["object_id"]].append(page)
                if not nonempty_string_list(data.get("identity_evidence")):
                    issue(page, "invalid_identity_evidence")
                if not aliases_list(data.get("aliases")):
                    issue(page, "invalid_aliases")
                body_source_refs = set(source_refs)
                refs = data.get("source_refs")
                if (not isinstance(refs, list) or not refs or not all(isinstance(ref, str) for ref in refs)
                        or len(set(refs)) != len(refs)
                        or not all(valid_rel_path(ref) and ref.endswith(".md") for ref in refs)):
                    issue(page, "invalid_source_refs")
                    refs = []
                metadata_sources = set()
                for ref in refs:
                    target = vault / ref
                    resolved_target = target.resolve()
                    target_data = None
                    in_sources = (target.parent == w / "sources"
                                  and resolved_target.parent == (w / "sources").resolve()
                                  and resolved_target.is_relative_to(vault))
                    if in_sources and resolved_target.is_file():
                        try:
                            target_data, _ = read_note(resolved_target)
                        except (ValueError, OSError, UnicodeError, yaml.YAMLError):
                            pass
                    if (not in_sources or not resolved_target.is_file()
                            or not isinstance(target_data, dict) or target_data.get("type") != "source"):
                        issue(page, "invalid_source_ref", ref)
                    else:
                        metadata_sources.add(target)
                if not isinstance(data.get("source_count"), int) or isinstance(data.get("source_count"), bool) or data["source_count"] < 0:
                    issue(page, "invalid_source_count")
                elif data["source_count"] != len(metadata_sources) or metadata_sources != body_source_refs:
                    issue(page, "source_count_mismatch", f"declared={data['source_count']}, metadata={len(metadata_sources)}, body={len(body_source_refs)}")
        elif page_type == "redirect":
            if page.parent not in (w / "entities", w / "concepts"):
                issue(page, "invalid_redirect_location")
            if data.get("knowledge_schema") != 1 or not isinstance(data.get("knowledge_schema"), int) or isinstance(data.get("knowledge_schema"), bool):
                issue(page, "invalid_knowledge_schema")
            if "canonical_path" not in data or not valid_rel_path(data.get("canonical_path")) or not data.get("canonical_path", "").endswith(".md"):
                issue(page, "invalid_canonical_path")
            forbidden = {"object_id", "source_count", "source_refs", "identity_evidence"}
            for field in sorted(forbidden):
                if field in data:
                    issue(page, "redirect_forbidden_field", field)
            if "aliases" in data and not aliases_list(data["aliases"]):
                issue(page, "invalid_aliases")
        for block in re.findall(r"(?m)^>\s*\[!WARNING\].*观点分歧.*(?:\n>.*)*", body):
            if "用户已裁定" not in block:
                warnings.append({"path": page.relative_to(vault).as_posix(), "code": "unresolved_conflict"})
                if "待用户裁定" not in block:
                    issue(page, "conflict_status_missing")
        if page.parent != w / "sources":
            continue
        source_total += 1
        op = data.get("original_path")
        if valid_rel_path(op) is None:
            issue(page, "invalid_original_path")
            issue(page, "missing_original", str(op)); continue
        source = (vault / op).resolve()
        if not source.is_relative_to(a.resolve()) or source not in originals:
            issue(page, "missing_original", op); continue
        mapped[source].append(page)
        try:
            original, _ = read_note(source)
        except (ValueError, OSError, UnicodeError, yaml.YAMLError) as exc:
            issue(page, "original_parse_error", str(exc)); continue
        summary, points = section(body, "核心摘要"), section(body, "关键要点")
        if not summary or not re.search(r"(?m)^[-*]\s+\S", points):
            issue(page, "missing_content")
        if re.search(r"原始资料未提供(?:摘要|结构化要点)|待补充|TODO|TBD", summary + points, re.I):
            issue(page, "placeholder_content")
        provenance = section(body, "来源")
        for key, label in (("author", "作者"), ("published", "发布日期"), ("source", "原始链接")):
            if original.get(key) and re.search(r"(?m)^- " + label + r"[：:]\s*(?:—|未提供)?\s*$", provenance):
                issue(page, "metadata_dropped", key)
            elif original.get(key) and not re.search(r"(?m)^- " + label + r"[：:]", provenance):
                issue(page, "metadata_dropped", key)
        original_links = resolve(str(data.get("original", "")).removeprefix("[[").removesuffix("]]").split("|", 1)[0], page)
        if data.get("original") and original_links != [source]:
            issue(page, "original_link_mismatch")
        if len(issues) == start:
            valid_sources.add(source)
    for source, summaries in mapped.items():
        if len(summaries) > 1:
            valid_sources.discard(source)
            for page in summaries:
                issue(page, "duplicate_original", source.relative_to(vault).as_posix())
    for object_id, owners in object_ids.items():
        if len(owners) > 1:
            for page in owners:
                issue(page, "duplicate_object_id", object_id)
    for page, (data, body) in parsed.items():
        if data.get("type") != "redirect":
            continue
        canonical = data.get("canonical_path")
        target = (vault / canonical).resolve() if valid_rel_path(canonical) else None
        target_data = parsed.get(target, (None, ""))[0] if target else None
        target_in_area = (target is not None and target.is_relative_to(vault) and target.is_file() and target.parent in ((w / "entities").resolve(), (w / "concepts").resolve())
                          and isinstance(target_data, dict))
        if target == page:
            issue(page, "redirect_self")
        elif target_in_area and target_data.get("type") == "redirect":
            issue(page, "redirect_chain", canonical)
        valid_target = target_in_area and target_data.get("type") in ("entity", "concept")
        if not valid_target:
            issue(page, "invalid_canonical_target", str(canonical))
        elif target != page:
            target_links = [p for t in links(body) for p in resolve(t, page)]
            if target not in target_links:
                issue(page, "redirect_body_link_missing", canonical)
    for page in pages:
        if page.parent != w and inbound[page] == 0:
            issue(page, "orphan")
    home = w / "_home.md"
    if home.is_file():
        home_text = home.read_text(encoding="utf-8-sig")
        table = re.search(r"\| 原始资料 \| 内容门禁通过 \| 待处理 \|\s*\n[^\n]+\n\|\s*\*\*(\d+)\*\*\s*\|\s*\*\*(\d+)\*\*\s*\|\s*\*\*(\d+)\*\*", home_text)
        if table and tuple(map(int, table.groups())) != (len(originals), len(valid_sources), len(originals) - len(valid_sources)):
            issue(home, "home_counts_mismatch")
    return {"archive_count": len(originals), "wiki_count": len(pages),
            "canonical_page_count": sum(1 for data, _ in parsed.values() if data.get("type") in ("entity", "concept")),
            "redirect_page_count": sum(1 for data, _ in parsed.values() if data.get("type") == "redirect"),
            "source_page_count": source_total, "mapped_original_count": len(mapped),
            "content_gate_passed": len(valid_sources),
            "unmapped_originals": sorted(p.relative_to(vault).as_posix() for p in originals - mapped.keys()),
            "issues": issues, "warnings": warnings,
            "limitation": "Content gates do not prove semantic fidelity or external factual accuracy."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vault", type=Path)
    parser.add_argument("--wiki", default="04 wiki")
    parser.add_argument("--archive", default="06 已归档")
    parser.add_argument("--today", type=dt.date.fromisoformat)
    args = parser.parse_args()
    try:
        result = audit(args.vault, args.wiki, args.archive, args.today)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Validation unavailable: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(bool(result["issues"] or result["unmapped_originals"]))


if __name__ == "__main__":
    raise SystemExit(main())
