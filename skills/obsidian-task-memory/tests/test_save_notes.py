import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import save_notes as save


def content(identity="memo-1", body="# 中文交接\n\n尚未解决，下一步核对证据。\n"):
    meta = dict(id=identity, task_id="task-1", type="session", created="2026-09-10T12:00:00+08:00", status="blocked", summary="中文：问题与证据", source_scope="仅当前可见对话", tags=["任务交接"])
    return "---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + "---\n" + body


class SaveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Path(self.temp.name) / "中文 主库"
        self.vault.mkdir()
        self.existing = self.vault / "原有笔记.md"
        self.existing.write_bytes(b"keep existing\r\n")
        self.manifest = dict(vault_root=str(self.vault), archive_root="09 任务与经验", notes=[dict(path="会话/2026/09/中文任务-a1.md", content=content())])

    def apply(self, manifest=None):
        manifest = manifest or self.manifest
        return save.run(manifest, True, save.run(manifest)["digest"])

    def test_preview_has_no_side_effects(self):
        result = save.run(self.manifest)
        self.assertEqual(result["mode"], "preview")
        self.assertEqual(list(self.vault.iterdir()), [self.existing])

    def test_chinese_roundtrip_and_retry(self):
        result = self.apply()
        self.assertTrue(result["verified"])
        target = Path(result["created"][0])
        before = target.stat().st_mtime_ns
        self.assertEqual(target.read_bytes(), self.manifest["notes"][0]["content"].encode("utf-8"))
        again = self.apply()
        self.assertEqual(again["created"], [])
        self.assertEqual(target.stat().st_mtime_ns, before)
        self.assertEqual(self.existing.read_bytes(), b"keep existing\r\n")

    def test_content_conflict_preserves_user_change(self):
        target = Path(self.apply()["created"][0])
        target.write_bytes(b"user edited")
        with self.assertRaises(save.Invalid):
            self.apply()
        self.assertEqual(target.read_bytes(), b"user edited")

    def test_digest_binds_draft(self):
        digest = save.run(self.manifest)["digest"]
        self.manifest["notes"][0]["content"] += "新信息\n"
        with self.assertRaises(save.Invalid):
            save.run(self.manifest, True, digest)
        self.assertFalse((self.vault / "09 任务与经验").exists())

    def test_paths_rejected(self):
        for bad in ("../原有笔记.md", "/outside.md", "C:/outside.md", "CON.md", "目录/NUL.txt.md", "目录/尾空格 .md/../a.md", "a\\b.md", ".obsidian/a.md", "trailing./x.md"):
            with self.subTest(path=bad):
                sample = copy.deepcopy(self.manifest)
                sample["notes"][0]["path"] = bad
                with self.assertRaises(save.Invalid):
                    save.run(sample)

    def test_archive_escape(self):
        self.manifest["archive_root"] = "../escape"
        with self.assertRaises(save.Invalid):
            save.run(self.manifest)

    def test_broken_links_and_code_fences(self):
        self.manifest["notes"][0]["content"] = content(body="# 标题\n[[不存在]]\n")
        with self.assertRaises(save.Invalid):
            save.run(self.manifest)
        self.manifest["notes"][0]["content"] = content(body='# 标题\n[[原有笔记]]\n```text\n[[示例不用解析]]\n```\n')
        self.assertTrue(self.apply()["verified"])

    def test_yaml_duplicate_and_missing_fields(self):
        for text in (content().replace('type: session', 'type: session\ntype: code'), content().replace('id: memo-1\n', ''), '---\n[bad yaml\n---\n# body\n'):
            self.manifest["notes"][0]["content"] = text
            with self.assertRaises((save.Invalid, yaml.YAMLError)):
                save.run(self.manifest)

    def test_unclosed_fence(self):
        self.manifest["notes"][0]["content"] = content(body="# 标题\n```python\nprint(1)\n")
        with self.assertRaises(save.Invalid):
            save.run(self.manifest)

    def test_case_colliding_paths(self):
        self.manifest["notes"] = [dict(path="A.md", content=content()), dict(path="a.md", content=content("memo-2"))]
        with self.assertRaises(save.Invalid):
            save.run(self.manifest)

    def test_batch_preflight_does_not_write_valid_first_note(self):
        self.manifest["notes"].append(dict(path="bad.md", content=content("memo-2", "[[失效目标]]")))
        with self.assertRaises(save.Invalid):
            self.apply()
        self.assertFalse((self.vault / "09 任务与经验").exists())

    def test_partial_failure_retry_completes_links(self):
        self.manifest["notes"] = [dict(path="first.md", content=content(body="# 第一页\n[[09 任务与经验/second]]\n")), dict(path="second.md", content=content("memo-2"))]
        original_link = os.link
        calls = 0

        def fail_second(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated interrupted commit")
            return original_link(source, target)

        with patch.object(save.os, "link", fail_second):
            result = self.apply()
        self.assertFalse(result["verified"])
        self.assertEqual(len(result["created"]), 1)
        self.assertFalse(list(self.vault.rglob(".task-memory-*")))
        retry = self.apply()
        self.assertTrue(retry["verified"])
        self.assertEqual(len(retry["unchanged"]), 1)
        self.assertEqual(len(retry["created"]), 1)

    def test_symlink_or_junction_rejected(self):
        link = self.vault / "09 任务与经验"
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        if os.name == "nt":
            import subprocess
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True)
            if result.returncode:
                self.skipTest("Junction creation unavailable")
            self.addCleanup(lambda: os.rmdir(link) if link.exists() else None)
        else:
            link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(save.Invalid):
            save.run(self.manifest)
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
