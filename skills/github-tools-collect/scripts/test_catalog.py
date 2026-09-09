import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('catalog', Path(__file__).with_name('catalog.py'))
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / '中文 收藏库'
        self.folder = self.root / 'tools/example'
        (self.folder / 'source').mkdir(parents=True)
        for name in ('README.md', 'UPSTREAM.md'):
            (self.folder / name).write_text('中文说明', encoding='utf-8')
        data = '原始源码\r\n'.encode('utf-8')
        (self.folder / 'source/example.txt').write_bytes(data)
        (self.folder / 'snapshot-manifest.json').write_text(json.dumps({'example.txt': hashlib.sha256(data).hexdigest()}), encoding='utf-8')
        self.item = dict(tool_name='example', display_name='示例', category='开发辅助', summary='示例说明', scenario='示例场景', platforms=['Windows'], mode='snapshot', ref='v1', commit='a'*40, license='MIT', verification='文档核验', imported_at='2026-09-09T12:00:00+08:00', checked_at='2026-09-09T12:00:00+08:00')
        self.entries = {'https://github.com/example/tool': self.item}
        self.save()

    def save(self):
        (self.root / 'imported_sources.json').write_text(json.dumps({'schema_version': 1, 'imported_urls': self.entries}, ensure_ascii=False), encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def test_valid_unicode_snapshot(self):
        self.assertEqual(len(catalog.validate(self.root)), 1)

    def test_tampered_source(self):
        (self.folder / 'source/example.txt').write_text('改动', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Snapshot mismatch'):
            catalog.validate(self.root)

    def test_extra_source(self):
        (self.folder / 'source/extra.txt').write_text('extra', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Snapshot mismatch'):
            catalog.validate(self.root)

    def test_missing_source(self):
        (self.folder / 'source/example.txt').unlink()
        with self.assertRaisesRegex(ValueError, 'Snapshot mismatch'):
            catalog.validate(self.root)

    def test_duplicate_url_variants(self):
        self.entries['https://github.com/Example/Tool.git'] = dict(self.item, tool_name='other')
        self.save()
        with self.assertRaisesRegex(ValueError, 'Duplicate source'):
            catalog.validate(self.root)

    def test_path_traversal(self):
        self.item['tool_name'] = '../outside'
        self.save()
        with self.assertRaisesRegex(ValueError, 'Invalid or duplicate directory'):
            catalog.validate(self.root)

    def test_url_normalization(self):
        self.assertEqual(catalog.canonical('git@github.com:Example/Tool.git'), 'https://github.com/example/tool')
        self.assertEqual(catalog.canonical('https://github.com/Example/Tool.git/'), 'https://github.com/example/tool')
        with self.assertRaises(ValueError):
            catalog.canonical('https://github.com/Example/Tool/tree/main')

    def test_unsafe_link(self):
        path = self.folder / 'source/link'
        path.write_text('../../../../outside', encoding='utf-8')
        manifest = json.loads((self.folder / 'snapshot-manifest.json').read_text(encoding='utf-8'))
        manifest['link'] = {'type': 'symlink', 'target': '../../../../outside', 'sha256': 'x'}
        (self.folder / 'snapshot-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Unsafe or missing link'):
            catalog.validate(self.root)


if __name__ == '__main__':
    unittest.main()
