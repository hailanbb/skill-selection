#!/usr/bin/env python3
"""Read-only structural/content gates; not a semantic or external fact checker."""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

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
        expected = {"sources": "source", "concepts": "concept", "entities": "entity", "insights": "insight"}.get(page.parent.name)
        if page.name == "index.md" and re.search(r"原始资料未提供(?:摘要|结构化要点)", body):
            issue(page, "index_placeholder")
        if not data.get("type") or (expected and data["type"] != expected):
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
        for block in re.findall(r"(?m)^>\s*\[!WARNING\].*观点分歧.*(?:\n>.*)*", body):
            if "用户已裁定" not in block:
                warnings.append({"path": page.relative_to(vault).as_posix(), "code": "unresolved_conflict"})
                if "待用户裁定" not in block:
                    issue(page, "conflict_status_missing")
        if page.parent != w / "sources":
            continue
        source_total += 1
        op = data.get("original_path")
        if not isinstance(op, str) or "\\" in op or Path(op).is_absolute():
            issue(page, "invalid_original_path"); continue
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
