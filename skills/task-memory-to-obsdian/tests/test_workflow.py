import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import configure
import recall
import save_notes
from test_save_notes import content


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.vault = self.root / "中文 主库"
        self.vault.mkdir()
        (self.vault / ".obsidian").mkdir()
        self.old = self.vault / "用户原笔记.md"
        self.old.write_bytes(b"user content\r\n")
        self.destination = self.vault / "09 任务与经验"
        self.config = self.root / "shared-config" / "config.json"

    def setup_config(self):
        return configure.setup(str(self.destination), explicit=str(self.config))

    def cli(self, script, *args):
        env = dict(os.environ, TASK_MEMORY_CONFIG=str(self.config), PYTHONIOENCODING="utf-8")
        completed = subprocess.run([sys.executable, str(SCRIPTS / script), *args], env=env, capture_output=True)
        self.assertTrue(completed.stdout, completed.stderr.decode("utf-8", errors="replace"))
        return completed.returncode, json.loads(completed.stdout.decode("utf-8"))

    def notes(self):
        return {"notes": [{"path": "会话/2026/09/任务-a1.md", "content": content()}]}

    def test_first_use_reports_setup_without_creating_anything(self):
        code, result = self.cli("configure.py", "show")
        self.assertEqual(code, 0)
        self.assertTrue(result["needs_setup"])
        self.assertFalse(self.config.exists())
        self.assertFalse(self.destination.exists())
        with self.assertRaises(save_notes.Invalid):
            save_notes.run_auto(self.notes(), str(self.config))

    def test_setup_detects_vault_and_roundtrips_chinese(self):
        result = self.setup_config()
        self.assertTrue(result["saved"])
        self.assertEqual(configure.load(str(self.config))["archive_root"], "09 任务与经验")
        self.assertEqual(configure.load(str(self.config))["vault_root"], str(self.vault))
        self.assertFalse(self.destination.exists())
        self.assertFalse(self.config.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_explicit_vault_without_obsidian_marker(self):
        other_vault = self.root / "另一个库"
        other_vault.mkdir()
        target = other_vault / "经验"
        with self.assertRaises(save_notes.Invalid):
            configure.build(str(target))
        config = configure.build(str(target), str(other_vault))
        self.assertEqual(config["archive_root"], "经验")

    def test_shared_config_is_read_by_independent_processes(self):
        code, setup = self.cli("configure.py", "setup", "--destination", str(self.destination))
        self.assertEqual(code, 0, setup)
        code, second_agent = self.cli("configure.py", "show")
        self.assertEqual(code, 0)
        self.assertFalse(second_agent["needs_setup"])
        manifest = self.root / "draft.json"
        manifest.write_text(json.dumps(self.notes(), ensure_ascii=False), encoding="utf-8")
        code, saved = self.cli("save_notes.py", str(manifest), "--auto")
        self.assertEqual(code, 0, saved)
        self.assertTrue(saved["verified"])
        code, found = self.cli("recall.py", "--task-id", "task-1")
        self.assertEqual(code, 0, found)
        self.assertEqual(found["candidates"][0]["path"], saved["created"][0])
        self.assertEqual(self.old.read_bytes(), b"user content\r\n")

    def test_auto_retry_does_not_duplicate_notes(self):
        self.setup_config()
        first = save_notes.run_auto(self.notes(), str(self.config))
        second = save_notes.run_auto(self.notes(), str(self.config))
        self.assertTrue(first["verified"] and second["verified"])
        self.assertEqual(second["created"], [])
        self.assertEqual(len(second["unchanged"]), 1)

    def test_default_cli_is_preview_for_explicit_review_requests(self):
        self.setup_config()
        manifest = self.root / "draft.json"
        manifest.write_text(json.dumps(self.notes(), ensure_ascii=False), encoding="utf-8")
        code, result = self.cli("save_notes.py", str(manifest))
        self.assertEqual(code, 0)
        self.assertEqual(result["mode"], "preview")
        self.assertFalse(self.destination.exists())

    def test_one_off_target_does_not_change_persistent_default(self):
        self.setup_config()
        before = self.config.read_bytes()
        manifest = {**self.notes(), "vault_root": str(self.vault), "archive_root": "仅本次"}
        result = save_notes.run_auto(manifest, str(self.config))
        self.assertTrue(result["verified"])
        self.assertIn("仅本次", result["created"][0])
        self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse(self.destination.exists())

    def test_default_change_requires_explicit_replace_and_preserves_notes(self):
        self.setup_config()
        result = save_notes.run_auto(self.notes(), str(self.config))
        target = Path(result["created"][0])
        original = target.read_bytes()
        new_destination = self.vault / "新的归档"
        with self.assertRaises(save_notes.Invalid):
            configure.setup(str(new_destination), explicit=str(self.config))
        configure.setup(str(new_destination), explicit=str(self.config), replace=True)
        self.assertEqual(configure.load(str(self.config))["archive_root"], "新的归档")
        self.assertEqual(target.read_bytes(), original)

    def test_invalid_and_unavailable_config_never_guesses_path(self):
        self.setup_config()
        data = json.loads(self.config.read_text(encoding="utf-8"))
        data["vault_root"] = str(self.root / "disconnected")
        self.config.write_text(json.dumps(data), encoding="utf-8")
        result = configure.describe(str(self.config))
        self.assertTrue(result["needs_setup"])
        self.assertIn("error", result)
        with self.assertRaises(save_notes.Invalid):
            save_notes.run_auto(self.notes(), str(self.config))
        self.assertFalse(self.destination.exists())

    def test_rejects_wrong_target_and_config_inside_vault(self):
        for destination, vault in ((str(self.root / "outside"), str(self.vault)), (str(self.vault), str(self.vault)), (str(self.old), str(self.vault)), ("relative/path", str(self.vault))):
            with self.subTest(destination=destination):
                with self.assertRaises(save_notes.Invalid):
                    configure.build(destination, vault)
        with self.assertRaises(save_notes.Invalid):
            configure.setup(str(self.destination), explicit=str(self.vault / "local.json"))

    def test_recall_only_headers_and_only_archive(self):
        self.setup_config()
        private_body = "PRIVATE_BODY_SENTINEL"
        notes = self.notes()
        notes["notes"][0]["content"] += private_body
        result = save_notes.run_auto(notes, str(self.config))
        before = {str(x): x.read_bytes() for x in self.vault.rglob("*.md")}
        found = recall.search(str(self.config), query="中文")
        self.assertEqual(found["scanned_headers"], 1)
        self.assertEqual(len(found["candidates"]), 1)
        self.assertNotIn(private_body, json.dumps(found))
        self.assertEqual(recall.search(str(self.config), note_type="lesson")["candidates"], [])
        self.assertEqual(recall.search(str(self.config), task_id="unknown")["candidates"], [])
        self.assertEqual(before, {str(x): x.read_bytes() for x in self.vault.rglob("*.md")})

    def test_recall_reports_bad_headers_without_hiding_valid_results(self):
        self.setup_config()
        save_notes.run_auto(self.notes(), str(self.config))
        (self.destination / "broken.md").write_text("no yaml header", encoding="utf-8")
        found = recall.search(str(self.config))
        self.assertEqual(len(found["candidates"]), 1)
        self.assertEqual(found["issue_count"], 1)

    def test_config_path_precedence_and_no_vendor_default(self):
        custom = self.root / "environment-config.json"
        with patch.dict(os.environ, {"TASK_MEMORY_CONFIG": str(custom)}):
            self.assertEqual(configure.config_path(), custom)
            self.assertEqual(configure.config_path(str(self.config)), self.config)
        with patch.dict(os.environ, {}, clear=True), patch.object(Path, "home", return_value=self.root):
            self.assertEqual(configure.config_path(), self.root / ".config/task-memory-to-obsdian/config.json")


if __name__ == "__main__":
    unittest.main()
