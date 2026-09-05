from __future__ import annotations
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from extract_keyframes import probe_duration

try:
    import yaml
except ImportError:
    yaml = None


class PackageTests(unittest.TestCase):
    def test_text_files_are_utf8_without_bom_or_private_developer_data(self):
        for path in ROOT.rglob("*"):
            if path.suffix not in {".md", ".py", ".yaml", ".txt"}:
                continue
            with self.subTest(file=path.name):
                raw = path.read_bytes()
                self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
                text = raw.decode("utf-8", errors="strict")
                self.assertNotIn("\ufffd", text)
                self.assertNotRegex(text, r"ghp_[A-Za-z0-9]{36}")
                self.assertNotIn("E:" + "\\hailan", text)
                self.assertNotIn("C:" + "\\Users\\HiWin11", text)

    def test_relative_documentation_links_resolve(self):
        for path in ROOT.rglob("*.md"):
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                if "://" in target or target.startswith("#"):
                    continue
                self.assertTrue((path.parent / target.split("#")[0]).is_file(), (path, target))

    @unittest.skipIf(yaml is None, "Install requirements-dev.txt for YAML parser checks")
    def test_skill_and_interface_parse_and_roundtrip(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        attributes = yaml.safe_load(skill.split("---", 2)[1])
        self.assertEqual(set(attributes), {"name", "description"})
        self.assertEqual(attributes["name"], ROOT.name)
        self.assertIn("小红书", attributes["description"])
        interface = yaml.safe_load((ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8"))["interface"]
        self.assertEqual(interface["display_name"], "小红书转笔记")
        self.assertIn("$" + ROOT.name, interface["default_prompt"])
        self.assertTrue(25 <= len(interface["short_description"]) <= 64)
        self.assertEqual(yaml.safe_load(yaml.safe_dump(attributes, allow_unicode=True)), attributes)

    @unittest.skipIf(yaml is None, "Install requirements-dev.txt for YAML parser checks")
    def test_json_quoted_yaml_values_roundtrip(self):
        values = {"title": '中文 "引号" 与冒号: 标题', "author": "作者\n换行", "publishTime": ""}
        frontmatter = "\n".join(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in values.items())
        self.assertEqual(yaml.safe_load(frontmatter), values)

    def test_cli_entrypoints_from_arbitrary_cwd(self):
        for script in ("sources.py", "configure.py", "run_workspace.py", "fetch_asset.py",
                       "extract_keyframes.py", "publish_note.py", "validate_note.py"):
            with self.subTest(script=script):
                result = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / script), "--help"],
                                        cwd=ROOT.parent, encoding="utf-8", capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_video_probe_uses_argument_array_and_explicit_utf8(self):
        video = Path("中文目录 & O'Brien") / "视频.mp4"
        with patch("extract_keyframes.subprocess.run", return_value=subprocess.CompletedProcess([], 0, '{"format":{"duration":"138.0"}}')) as run:
            self.assertEqual(probe_duration(video, "C:/tools with spaces/ffprobe.exe"), 138.0)
        args, kwargs = run.call_args
        self.assertIsInstance(args[0], list)
        self.assertEqual(args[0][-1], str(video))
        self.assertEqual(kwargs["encoding"], "utf-8")
        self.assertFalse(kwargs.get("shell", False))


if __name__ == "__main__":
    unittest.main()
