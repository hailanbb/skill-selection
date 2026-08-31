from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import extract_metadata  # noqa: E402


class ExtractMetadataTests(unittest.TestCase):
    def test_foreground_uses_argument_array_and_removes_sensitive_urls(self) -> None:
        source_url = "https://example.invalid/video?id=中文&from=$env:SOURCE"
        raw = {
            "id": "123",
            "title": "中文标题",
            "uploader": "作者",
            "webpage_url": "https://example.invalid/video/123",
            "url": "https://signed.invalid/video.mp4?token=secret",
            "formats": [{"url": "https://signed.invalid/format?token=secret"}],
            "http_headers": {"Cookie": "secret"},
        }
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(raw, ensure_ascii=False), stderr=""
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "含 空格" / "metadata.json"
            with patch("extract_metadata.subprocess.run", return_value=completed) as run:
                result = extract_metadata.extract_metadata(source_url, output, "yt-dlp.exe")

            command = run.call_args.args[0]
            options = run.call_args.kwargs
            self.assertIsInstance(command, list)
            self.assertEqual(command[-2:], ["--", source_url])
            self.assertFalse(options["shell"])
            self.assertEqual(options["encoding"], "utf-8")
            self.assertEqual(result["title"], "中文标题")
            self.assertEqual(result["source_url"], source_url)
            self.assertNotIn("url", result)
            self.assertNotIn("formats", result)
            self.assertNotIn("http_headers", result)
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(saved["uploader"], "作者")

    def test_background_command_does_not_launch_nested_powershell(self) -> None:
        source_url = "https://example.invalid/$env:SOURCE?a=1&b=2"
        output = Path(r"E:\含 空格\metadata.json")
        status = Path(r"E:\含 空格\metadata.status.json")
        command = extract_metadata.background_command(source_url, output, status, r"C:\Tools\yt-dlp.exe")

        self.assertIsInstance(command, list)
        self.assertEqual(command[0], sys.executable)
        self.assertNotIn("powershell", " ".join(command).lower())
        self.assertNotIn("-command", [part.lower() for part in command])
        self.assertIn(source_url, command)
        self.assertIn(str(output), command)
        self.assertIn(r"C:\Tools\yt-dlp.exe", command)

    def test_background_process_uses_shell_false(self) -> None:
        process = Mock(pid=4321)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "含 空格"
            with patch("extract_metadata.subprocess.Popen", return_value=process) as popen:
                pid = extract_metadata.start_background(
                    "https://example.invalid/video?a=1&b=$env:VALUE",
                    root / "metadata.json",
                    root / "metadata.status.json",
                    root / "metadata.log",
                    "yt-dlp.exe",
                )

        command = popen.call_args.args[0]
        options = popen.call_args.kwargs
        self.assertEqual(pid, 4321)
        self.assertIsInstance(command, list)
        self.assertFalse(options["shell"])
        self.assertNotIn("powershell", " ".join(command).lower())


if __name__ == "__main__":
    unittest.main()
