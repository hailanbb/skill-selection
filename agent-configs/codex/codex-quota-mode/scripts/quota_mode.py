"""Reversible global Codex defaults; no network calls and no credential output."""
from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).parent / 'vendor'))
import tomlkit

BEGIN = '<!-- codex-quota-mode:v1:begin -->'
END = '<!-- codex-quota-mode:v1:end -->'
KEYS = {
    'model': 'gpt-6-astra', 'model_reasoning_effort': 'high',
    'agents.enabled': True, 'agents.max_concurrent_threads_per_session': 2,
    'agents.default_subagent_model': 'gpt-5.6-luna',
    'agents.default_subagent_reasoning_effort': 'medium',
}


class ModeError(Exception):
    pass


def read(path):
    if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
        raise ModeError(f'拒绝链接路径：{path.name}')
    return path.read_bytes() if path.exists() else None


def unpack(raw):
    raw = raw or b''
    for bom, encoding in ((b'\xef\xbb\xbf', 'utf-8'), (b'\xff\xfe', 'utf-16-le'), (b'\xfe\xff', 'utf-16-be')):
        if raw.startswith(bom):
            return raw[len(bom):].decode(encoding), encoding, bom
    return raw.decode('utf-8'), 'utf-8', b''


def pack(text, raw):
    _, encoding, bom = unpack(raw)
    return bom + text.encode(encoding)


def digest(raw):
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def encode(raw):
    return base64.b64encode(raw).decode('ascii') if raw is not None else None


def decode(value):
    return base64.b64decode(value, validate=True) if value is not None else None


def atomic(path, data):
    # Individual replacement is atomic. Journal permits recovery between files.
    path.parent.mkdir(parents=True, exist_ok=True)
    if data is None:
        path.unlink(missing_ok=True)
        return
    descriptor, temporary = tempfile.mkstemp(prefix='.quota-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if read(path) != data:
            raise ModeError(f'回读失败：{path.name}')
    finally:
        Path(temporary).unlink(missing_ok=True)


def document(raw):
    try:
        return tomlkit.parse(unpack(raw)[0])
    except Exception as exc:
        raise ModeError('config.toml 编码或解析失败；为避免泄露内容不输出解析上下文') from exc


def get(doc, key):
    cursor = doc
    for part in key.split('.'):
        if not isinstance(cursor, dict) or part not in cursor:
            return None
        cursor = cursor[part]
    return cursor.unwrap() if hasattr(cursor, 'unwrap') else cursor


def assign(doc, key, value):
    pieces = key.split('.')
    cursor = doc
    for part in pieces[:-1]:
        if part not in cursor:
            cursor[part] = tomlkit.table()
        cursor = cursor[part]
        if not isinstance(cursor, dict):
            raise ModeError('agents 配置不是表，不能自动合并')
    if value is None:
        cursor.pop(pieces[-1], None)
    else:
        cursor[pieces[-1]] = value


def patch_config(raw, values, remove_empty_agents=False):
    text = unpack(raw)[0]
    doc = document(raw)
    for key, value in values.items():
        assign(doc, key, value)
    if remove_empty_agents and 'agents' in doc and not doc['agents']:
        del doc['agents']
    rendered = tomlkit.dumps(doc)
    # Existing style is retained by tomlkit; new lines follow existing CRLF style.
    if '\r\n' in text and '\n' not in text.replace('\r\n', ''):
        rendered = rendered.replace('\r\n', '\n').replace('\n', '\r\n')
    result = pack(rendered, raw)
    parsed = document(result)
    if any(get(parsed, key) != value for key, value in values.items()):
        raise ModeError('配置语义回读不一致')
    return result


class Controller:
    def __init__(self, home):
        self.home = Path(home).absolute()
        for item in (self.home, *self.home.parents):
            if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
                raise ModeError('Codex home 不可经由链接或 junction')
        self.storage = self.home / 'quota-mode'
        self.state_path = self.storage / 'state.json'
        self.journal_path = self.storage / 'pending.json'
        for item in (self.storage, self.state_path, self.journal_path):
            if item.exists() and (item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction())):
                raise ModeError('状态路径不可为链接')

    def state(self):
        data = read(self.state_path)
        if data is None:
            return {'version': 1, 'mode': 'off'}
        state = json.loads(data.decode('utf-8'))
        if state.get('version') != 1 or state.get('mode') not in ('on', 'off'):
            raise ModeError('未知状态格式，停止写入')
        return state

    @contextlib.contextmanager
    def lock(self):
        self.storage.mkdir(parents=True, exist_ok=True)
        path = self.storage / 'switch.lock'
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise ModeError('切换锁已存在；先核实进程是否仍在运行，不自动抢锁') from exc
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(str(os.getpid()))
            yield
        finally:
            path.unlink(missing_ok=True)

    def check_override(self):
        raw = read(self.home / 'AGENTS.override.md')
        return bool(raw and unpack(raw)[0].strip())

    def status(self):
        state = self.state()
        config = document(read(self.home / 'config.toml'))
        agents = unpack(read(self.home / 'AGENTS.md'))[0]
        conflicts = []
        if state['mode'] == 'on':
            conflicts = [key for key, value in KEYS.items() if get(config, key) != value]
            block = state.get('block', '')
            if not block or agents.count(block) != 1 or agents.count(BEGIN) != 1 or agents.count(END) != 1:
                conflicts.append('AGENTS.md:managed-block')
        elif BEGIN in agents or END in agents:
            conflicts.append('AGENTS.md:orphan-block')
        return {
            'saved_mode': state['mode'], 'pending': self.journal_path.exists(),
            'consistent': not conflicts, 'conflicts': conflicts,
            'global_override': self.check_override(),
            'global_defaults': {key: get(config, key) for key in KEYS},
            'runtime_verified': False,
            'reload': '新会话/重启后加载；现有会话、项目、profile 或 UI 可能覆盖全局默认',
        }

    def transaction(self, updates, new_state):
        rows = []
        for name, before, after in updates:
            if name not in ('config.toml', 'AGENTS.md'):
                raise ModeError('不支持的事务目标')
            if read(self.home / name) != before:
                raise ModeError(f'文件已被其他进程修改：{name}')
            rows.append({'name': name, 'before': encode(before), 'after': encode(after)})
        old_state = read(self.state_path)
        journal = {'version': 1, 'rows': rows, 'old_state': encode(old_state)}
        payload = (json.dumps(journal, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        backups = self.storage / 'backups'
        if backups.is_symlink() or (hasattr(backups, 'is_junction') and backups.is_junction()):
            raise ModeError('备份目录不可为链接')
        backup = backups / (uuid.uuid4().hex + '.json')
        atomic(backup, payload)
        atomic(self.journal_path, payload)
        try:
            for row in rows:
                path = self.home / row['name']
                if read(path) != decode(row['before']):
                    raise ModeError(f'检测到并发改动：{row["name"]}')
                atomic(path, decode(row['after']))
            atomic(self.state_path, (json.dumps(new_state, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
            self.journal_path.unlink()
        except Exception:
            # Leave the durable journal; recover only known before/after bytes.
            raise ModeError('切换未完成；pending 快照已保存，请运行 status 后 recover')

    def recover(self):
        with self.lock():
            data = read(self.journal_path)
            if data is None:
                return {'changed': False, **self.status()}
            journal = json.loads(data.decode('utf-8'))
            if journal.get('version') != 1:
                raise ModeError('未知恢复格式')
            rows = journal['rows']
            if sorted(row['name'] for row in rows) != ['AGENTS.md', 'config.toml']:
                raise ModeError('恢复目标不合法')
            for row in rows:
                if read(self.home / row['name']) not in (decode(row['before']), decode(row['after'])):
                    raise ModeError(f'恢复检测到用户修改，未覆盖：{row["name"]}')
            for row in rows:
                atomic(self.home / row['name'], decode(row['before']))
            atomic(self.state_path, decode(journal['old_state']))
            self.journal_path.unlink()
            return {'recovered': True, **self.status()}

    def switch(self, action):
        with self.lock():
            if self.journal_path.exists():
                raise ModeError('存在未完成事务；先 status，再 recover')
            status = self.status()
            if not status['consistent']:
                raise ModeError('受管内容发生冲突：' + ', '.join(status['conflicts']))
            state = self.state()
            if state['mode'] == action:
                return {'changed': False, **status}
            config = read(self.home / 'config.toml')
            agents = read(self.home / 'AGENTS.md')
            if action == 'on':
                if self.check_override():
                    raise ModeError('非空 AGENTS.override.md 将屏蔽规则；未修改它，暂不能开启')
                before_doc = document(config)
                # Never overwrite the legacy concurrency alias: preserve it, report ambiguity.
                if get(before_doc, 'agents.max_threads') is not None:
                    raise ModeError('存在旧别名 agents.max_threads；先单独迁移，避免两个上限并存')
                changed_config = patch_config(config, KEYS)
                text = unpack(agents)[0]
                match = re.search(r'\r\n|\n|\r', text)
                newline = match.group() if match else '\n'
                asset = (Path(__file__).resolve().parents[1] / 'assets' / 'mode-block.md').read_text(encoding='utf-8')
                block = newline * 2 + BEGIN + newline + asset.rstrip().replace('\n', newline) + newline + END + newline
                changed_agents = pack(text + block, agents)
                new_state = {
                    'version': 1, 'mode': 'on', 'block': block,
                    'before_config': encode(config), 'after_config': encode(changed_config),
                    'before_agents': encode(agents), 'after_agents': encode(changed_agents),
                    'baseline': {key: get(before_doc, key) for key in KEYS},
                    'had_agents_table': 'agents' in before_doc,
                }
            else:
                if config == decode(state['after_config']):
                    changed_config = decode(state['before_config'])
                else:
                    changed_config = patch_config(config, state['baseline'], not state['had_agents_table'])
                if agents == decode(state['after_agents']):
                    changed_agents = decode(state['before_agents'])
                else:
                    changed_agents = pack(unpack(agents)[0].replace(state['block'], '', 1), agents)
                new_state = {'version': 1, 'mode': 'off'}
            self.transaction([('config.toml', config, changed_config), ('AGENTS.md', agents, changed_agents)], new_state)
            return {'changed': True, **self.status()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['on', 'off', 'status', 'recover'])
    parser.add_argument('--codex-home', type=Path, default=Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex'))
    args = parser.parse_args()
    try:
        controller = Controller(args.codex_home)
        if args.action == 'status':
            result = controller.status()
        elif args.action == 'recover':
            result = controller.recover()
        else:
            result = controller.switch(args.action)
        # ASCII JSON avoids locale-dependent decoding by Windows parent processes.
        print(json.dumps(result, ensure_ascii=True))
    except Exception as exc:
        # Do not echo TOML/JSON parser excerpts: config and snapshots may contain secrets.
        message = str(exc) if isinstance(exc, ModeError) else f'{type(exc).__name__}：操作失败，未输出私有文件内容'
        print(json.dumps({'error': message}, ensure_ascii=True))
        return 1
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
