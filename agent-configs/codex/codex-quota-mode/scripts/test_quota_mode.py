import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('quota_mode', Path(__file__).with_name('quota_mode.py'))
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)


class ModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='中文 开关 [测试] ')
        self.home = Path(self.temp.name)
        self.cfg = self.home / 'config.toml'
        self.ag = self.home / 'AGENTS.md'
        self.cfg.write_bytes(b'\xef\xbb\xbf' + ('# 中文配置\r\nmodel = "gpt-6-astra"\r\nmodel_reasoning_effort = "medium"\r\nsandbox_mode = "workspace-write"\r\n[unrelated]\r\nname = "用户保留"\r\n').encode('utf-8'))
        self.ag.write_bytes(b'\xef\xbb\xbf' + '# 中文规则\r\n保留原文\n'.encode('utf-8'))
        self.controller = q.Controller(self.home)
        self.before = self.cfg.read_bytes(), self.ag.read_bytes()

    def tearDown(self):
        self.temp.cleanup()

    def test_roundtrip_bytes_and_six_values(self):
        status = self.controller.switch('on')
        self.assertTrue(status['changed'])
        self.assertEqual(status['global_defaults'], q.KEYS)
        self.assertFalse(status['runtime_verified'])
        self.assertEqual(q.document(self.cfg.read_bytes())['sandbox_mode'], 'workspace-write')
        self.assertEqual(q.document(self.cfg.read_bytes())['unrelated']['name'], '用户保留')
        self.assertTrue(self.cfg.read_bytes().startswith(b'\xef\xbb\xbf'))
        self.assertTrue(self.ag.read_bytes().startswith(self.before[1]))
        self.controller.switch('off')
        self.assertEqual((self.cfg.read_bytes(), self.ag.read_bytes()), self.before)

    def test_idempotence(self):
        self.assertFalse(self.controller.switch('off')['changed'])
        self.controller.switch('on')
        enabled = self.cfg.read_bytes(), self.ag.read_bytes()
        self.assertFalse(self.controller.switch('on')['changed'])
        self.assertEqual((self.cfg.read_bytes(), self.ag.read_bytes()), enabled)
        self.controller.switch('off')
        self.assertFalse(self.controller.switch('off')['changed'])

    def test_preserve_intervening_user_edits(self):
        self.controller.switch('on')
        doc = q.document(self.cfg.read_bytes())
        doc['unrelated']['name'] = '用户新增改动'
        doc['agents']['interrupt_message'] = False
        self.cfg.write_bytes(q.pack(q.tomlkit.dumps(doc), self.cfg.read_bytes()))
        self.ag.write_bytes(self.ag.read_bytes() + '\n追加用户规则'.encode('utf-8'))
        self.controller.switch('off')
        doc = q.document(self.cfg.read_bytes())
        self.assertEqual(doc['model_reasoning_effort'], 'medium')
        self.assertEqual(doc['unrelated']['name'], '用户新增改动')
        self.assertFalse(doc['agents']['interrupt_message'])
        self.assertNotIn('default_subagent_model', doc['agents'])
        self.assertEqual(self.ag.read_bytes(), self.before[1] + '\n追加用户规则'.encode('utf-8'))

    def test_managed_key_conflict_is_non_destructive(self):
        self.controller.switch('on')
        self.cfg.write_bytes(self.cfg.read_bytes().replace(b'"high"', b'"xhigh"'))
        current = self.cfg.read_bytes(), self.ag.read_bytes()
        with self.assertRaises(q.ModeError):
            self.controller.switch('off')
        self.assertEqual((self.cfg.read_bytes(), self.ag.read_bytes()), current)

    def test_block_conflict(self):
        self.controller.switch('on')
        self.ag.write_bytes(self.ag.read_bytes().replace(b'Luna', b'LUNA', 1))
        current = self.ag.read_bytes()
        with self.assertRaises(q.ModeError):
            self.controller.switch('off')
        self.assertEqual(self.ag.read_bytes(), current)

    def test_override_blocks_enable_but_not_disable(self):
        override = self.home / 'AGENTS.override.md'
        override.write_text('覆盖规则', encoding='utf-8')
        with self.assertRaises(q.ModeError):
            self.controller.switch('on')
        self.assertEqual((self.cfg.read_bytes(), self.ag.read_bytes()), self.before)
        override.write_text('', encoding='utf-8')
        self.controller.switch('on')
        override.write_text('后加覆盖', encoding='utf-8')
        self.controller.switch('off')
        self.assertEqual(override.read_text(encoding='utf-8'), '后加覆盖')

    def test_missing_files_restored_as_missing(self):
        self.cfg.unlink()
        self.ag.unlink()
        self.controller.switch('on')
        self.controller.switch('off')
        self.assertFalse(self.cfg.exists())
        self.assertFalse(self.ag.exists())

    def test_existing_agents_and_no_final_newline(self):
        raw = b'model = "previous"\n[agents]\nenabled = false\nmax_concurrent_threads_per_session = 1\n'
        self.cfg.write_bytes(raw)
        self.ag.write_bytes('没有尾换行'.encode('utf-8'))
        self.controller.switch('on')
        self.controller.switch('off')
        self.assertEqual(self.cfg.read_bytes(), raw)
        self.assertEqual(self.ag.read_bytes(), '没有尾换行'.encode('utf-8'))

    def test_utf16_agents_roundtrip(self):
        raw = b'\xff\xfe' + '中文\r\n规则'.encode('utf-16-le')
        self.ag.write_bytes(raw)
        self.controller.switch('on')
        self.controller.switch('off')
        self.assertEqual(self.ag.read_bytes(), raw)

    def test_crash_recovery(self):
        real_atomic = q.atomic
        def fail_agents(path, data):
            if path == self.ag:
                raise OSError('模拟磁盘写失败')
            real_atomic(path, data)
        with patch.object(q, 'atomic', side_effect=fail_agents):
            with self.assertRaises(q.ModeError):
                self.controller.switch('on')
        self.assertTrue(self.controller.journal_path.exists())
        self.controller.recover()
        self.assertEqual((self.cfg.read_bytes(), self.ag.read_bytes()), self.before)
        self.assertFalse(self.controller.journal_path.exists())

    def test_recovery_refuses_new_edits(self):
        real_atomic = q.atomic
        def fail_state(path, data):
            if path == self.controller.state_path:
                raise OSError('模拟状态写失败')
            real_atomic(path, data)
        with patch.object(q, 'atomic', side_effect=fail_state):
            with self.assertRaises(q.ModeError):
                self.controller.switch('on')
        self.ag.write_bytes(self.ag.read_bytes() + b'\nnew edits')
        before = self.cfg.read_bytes(), self.ag.read_bytes()
        with self.assertRaises(q.ModeError):
            self.controller.recover()
        self.assertEqual((self.cfg.read_bytes(), self.ag.read_bytes()), before)

    def test_lock_refuses_concurrent_switch(self):
        with self.controller.lock():
            with self.assertRaises(q.ModeError):
                self.controller.switch('on')

    def test_legacy_alias_rejected_without_changes(self):
        raw = self.cfg.read_bytes() + b'\r\n[agents]\r\nmax_threads = 6\r\n'
        self.cfg.write_bytes(raw)
        with self.assertRaises(q.ModeError):
            self.controller.switch('on')
        self.assertEqual(self.cfg.read_bytes(), raw)

    def test_invalid_toml_untouched(self):
        self.cfg.write_bytes(b'broken = [')
        with self.assertRaises(q.ModeError):
            self.controller.switch('on')
        self.assertEqual(self.cfg.read_bytes(), b'broken = [')


if __name__ == '__main__':
    unittest.main(verbosity=2)
