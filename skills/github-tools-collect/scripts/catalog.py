"""Generate the catalog and validate local collection invariants (Python 3.10+)."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import os
from urllib.parse import urlparse
from datetime import datetime

START, END = '<!-- catalog:start -->', '<!-- catalog:end -->'


def canonical(url):
    value = url.strip()
    if value.startswith('git@github.com:'):
        value = 'https://github.com/' + value[len('git@github.com:'):]
    p = urlparse(value)
    if p.scheme not in ('https', 'http') or p.hostname != 'github.com' or p.username or p.password or p.port:
        raise ValueError('Expected a GitHub repository URL')
    parts = p.path.strip('/').split('/')
    if len(parts) != 2 or p.query or p.fragment:
        raise ValueError('Registry keys must identify a repository, not a branch or file')
    owner, repo = parts
    repo = re.sub(r'\.git$', '', repo, flags=re.I)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', owner) or not re.fullmatch(r'[A-Za-z0-9_.-]+', repo):
        raise ValueError('Invalid owner/repository')
    if owner in ('.', '..') or repo in ('.', '..'):
        raise ValueError('Invalid owner/repository')
    return f'https://github.com/{owner}/{repo}'.lower()


def cell(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Catalog values must be non-empty strings')
    return value.replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def validate(root):
    registry = read_json(root / 'imported_sources.json')
    if registry.get('schema_version') != 1 or not isinstance(registry.get('imported_urls'), dict):
        raise ValueError('Unsupported registry schema')
    rows, seen, slugs = [], set(), set()
    for url, item in registry['imported_urls'].items():
        identity = canonical(url)
        if identity in seen:
            raise ValueError(f'Duplicate source: {identity}')
        seen.add(identity)
        if url != identity:
            raise ValueError(f'Use canonical registry key: {identity}')
        slug = item['tool_name']
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug) or slug in slugs:
            raise ValueError(f'Invalid or duplicate directory: {slug}')
        slugs.add(slug)
        folder = root / 'tools' / slug
        for name in ('README.md', 'UPSTREAM.md'):
            if not (folder / name).is_file():
                raise ValueError(f'Missing {slug}/{name}')
        for key in ('ref', 'license', 'verification'):
            cell(item[key])
        for key in ('imported_at', 'checked_at', 'updated_at'):
            if key in item:
                if datetime.fromisoformat(item[key]).tzinfo is None:
                    raise ValueError(f'{slug}: {key} needs timezone')
            elif key != 'updated_at':
                raise ValueError(f'{slug}: missing {key}')
        if not isinstance(item['platforms'], list) or not item['platforms']:
            raise ValueError('platforms must be a non-empty list')
        for platform in item['platforms']:
            cell(platform)
        if item['mode'] not in ('snapshot', 'guide-only'):
            raise ValueError(f'Unknown mode: {slug}')
        if not re.fullmatch(r'[0-9a-f]{40}', item['commit']):
            raise ValueError(f'Invalid commit: {slug}')
        if item['mode'] == 'snapshot':
            source = folder / 'source'
            manifest = read_json(folder / 'snapshot-manifest.json')
            if not isinstance(manifest, dict) or not manifest:
                raise ValueError(f'Empty snapshot: {slug}')
            actual = {}
            for path in source.rglob('*'):
                relative = path.relative_to(source).as_posix()
                spec = manifest.get(relative)
                if isinstance(spec, dict) and spec.get('type') == 'symlink':
                    target = os.readlink(path) if path.is_symlink() else path.read_text(encoding='utf-8')
                    resolved = (path.parent / target).resolve()
                    if not resolved.is_relative_to(source.resolve()) or not resolved.exists():
                        raise ValueError(f'Unsafe or missing link target: {relative}')
                    actual[relative] = {'type': 'symlink', 'target': target, 'sha256': hashlib.sha256(target.encode('utf-8')).hexdigest()}
                    continue
                if path.is_symlink():
                    raise ValueError(f'Symlink needs explicit handling: {path}')
                if path.is_file():
                    if '.git' in path.relative_to(source).parts:
                        raise ValueError('Nested .git metadata found')
                    if path.stat().st_size >= 100 * 1024 * 1024:
                        raise ValueError(f'File exceeds GitHub limit: {path}')
                    digest = hashlib.sha256()
                    with path.open('rb') as stream:
                        for block in iter(lambda: stream.read(1024 * 1024), b''):
                            digest.update(block)
                    actual[relative] = digest.hexdigest()
            if actual != manifest:
                missing = set(manifest) - set(actual)
                extra = set(actual) - set(manifest)
                changed = {p for p in actual.keys() & manifest.keys() if actual[p] != manifest[p]}
                raise ValueError(f'Snapshot mismatch {slug}: missing={len(missing)}, extra={len(extra)}, changed={len(changed)}')
        elif (folder / 'source').exists():
            raise ValueError(f'guide-only entry has source files: {slug}')
        rows.append((url, item))
    existing = {p.name for p in (root / 'tools').iterdir() if p.is_dir()}
    if existing != slugs:
        raise ValueError(f'Unregistered or missing tool directories: {existing ^ slugs}')
    return sorted(rows, key=lambda x: (x[1]['category'], x[1]['tool_name']))


def render(rows):
    result = [START, '', f'已收藏 **{len(rows)}** 个工具。版本为收录时快照，实际使用请查看官方发行页。', '',
              '| 分类 | 工具 | 核心功能 | 使用场景 | 平台 | 收藏版本 | 详细说明 |',
              '| :--- | :--- | :--- | :--- | :--- | :--- | :--- |']
    for url, item in rows:
        values = [cell(item[k]) for k in ('category', 'display_name', 'summary', 'scenario')]
        values += [cell(' / '.join(item['platforms'])), cell(item['ref']), f"[👉 使用指南](tools/{item['tool_name']}/README.md)"]
        result.append('| ' + ' | '.join(values) + ' |')
    return '\n'.join(result + ['', END])


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'render'))
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        rows = validate(root)
        path = root / 'README.md'
        raw = path.read_bytes()
        text = raw.decode('utf-8')
        if text.count(START) != 1 or text.count(END) != 1 or text.index(START) >= text.index(END):
            raise ValueError('README requires one ordered catalog marker pair')
        newline = '\r\n' if b'\r\n' in raw else '\n'
        expected = render(rows).replace('\n', newline)
        old = text[text.index(START):text.index(END) + len(END)]
        if args.action == 'render':
            if old != expected:
                path.write_bytes(text.replace(old, expected, 1).encode('utf-8'))
        elif old != expected:
            raise ValueError('Catalog is stale; run render')
        print(f'OK: {args.action}; {len(rows)} tool(s); registry and snapshots validated')
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f'ERROR: {error}\n')


if __name__ == '__main__':
    run()
