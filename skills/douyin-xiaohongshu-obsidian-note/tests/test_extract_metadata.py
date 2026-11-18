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
        source_url = "https://www.douyin.com/video/7531234567890123456?from=$env:SOURCE"
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
        command = extract_metadata.background_command(source_url, output, status, r"C:\Tools\yt-dlp.exe", Path(r"E:\含 空格"))

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
                    root,
                )

        command = popen.call_args.args[0]
        options = popen.call_args.kwargs
        self.assertEqual(pid, 4321)
        self.assertIsInstance(command, list)
        self.assertFalse(options["shell"])
        self.assertNotIn("powershell", " ".join(command).lower())

    def test_cookies_from_browser_included_in_yt_dlp_command(self) -> None:
        source_url = "https://www.douyin.com/video/7531234567890123456"
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps({"id": "123", "title": "测试"}, ensure_ascii=False), stderr=""
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "metadata.json"
            with patch("extract_metadata.subprocess.run", return_value=completed) as run:
                extract_metadata.extract_metadata(source_url, output, "yt-dlp.exe", cookies_from_browser="edge")

            command = run.call_args.args[0]
            self.assertIn("--cookies-from-browser", command)
            self.assertIn("edge", command)
            self.assertEqual(command[-2:], ["--", source_url])

    def test_metadata_fallback_to_ssr_when_yt_dlp_fails_403(self) -> None:
        import io
        source_url = "https://www.douyin.com/video/7531234567890123456"
        completed = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="HTTP Error 403: Forbidden: Fresh cookies needed"
        )
        fake_router_data = {
            "loaderData": {
                "video_(id)/page": {
                    "itemInfo": {
                        "desc": "SSR回退测试标题",
                        "aweme_id": "7531234567890123456",
                        "author": {"nickname": "测试博主", "sec_uid": "sec123"},
                        "duration": 45000,
                        "create_time": 1700000000,
                    }
                }
            }
        }
        fake_html = f"<html><script>window._ROUTER_DATA = {json.dumps(fake_router_data)};</script></html>".encode("utf-8")
        mock_response = io.BytesIO(fake_html)
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "metadata.json"
            with patch("extract_metadata.subprocess.run", return_value=completed), \
                 patch("urllib.request.urlopen", return_value=mock_response):
                result = extract_metadata.extract_metadata(source_url, output, "yt-dlp.exe")

            self.assertEqual(result["title"], "SSR回退测试标题")
            self.assertEqual(result["uploader"], "测试博主")
            self.assertEqual(result["duration"], 45.0)
            self.assertEqual(result["extractor"], "douyin:html_ssr_fallback")
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(saved["id"], "7531234567890123456")

    def test_auto_uses_local_cookie_file_if_present(self) -> None:
        source_url = "https://www.douyin.com/video/7531234567890123456"
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps({"id": "123", "title": "测试"}, ensure_ascii=False), stderr=""
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            cookie_file = Path(temp_dir) / "douyin.txt"
            cookie_file.write_text("test cookie content", encoding="utf-8")
            output = Path(temp_dir) / "metadata.json"
            with patch("extract_metadata.cookie_file_path", return_value=cookie_file), \
                 patch("extract_metadata.subprocess.run", return_value=completed) as run:
                extract_metadata.extract_metadata(source_url, output, "yt-dlp.exe")

            command = run.call_args.args[0]
            self.assertIn("--cookies", command)
            self.assertIn(str(cookie_file), command)

    def test_manage_cookies_roundtrip(self) -> None:
        import manage_cookies
        with tempfile.TemporaryDirectory() as temp_dir:
            test_cookie_file = Path(temp_dir) / "douyin.txt"
            with patch("manage_cookies.cookie_file_path", return_value=test_cookie_file):
                self.assertFalse(manage_cookies.inspect_cookies()["exists"])
                res = manage_cookies.save_cookie_text("ttwid=123; sessionid=abc")
                self.assertTrue(res["saved"])
                status = manage_cookies.inspect_cookies()
                self.assertTrue(status["exists"])
                self.assertEqual(status["cookie_count"], 2)
                clear_res = manage_cookies.clear_cookies()
                self.assertTrue(clear_res["cleared"])
                self.assertFalse(manage_cookies.inspect_cookies()["exists"])

    def test_manage_cookies_xiaohongshu_platform(self) -> None:
        import manage_cookies
        with tempfile.TemporaryDirectory() as temp_dir:
            xhs_cookie = Path(temp_dir) / "xiaohongshu.txt"
            with patch("manage_cookies.cookie_file_path", return_value=xhs_cookie):
                res = manage_cookies.save_cookie_text("a1=xyz; web_session=def", platform="xiaohongshu")
                self.assertTrue(res["saved"])
                self.assertEqual(res["platform"], "xiaohongshu")
                self.assertIn(".xiaohongshu.com", xhs_cookie.read_text(encoding="utf-8"))
                header = manage_cookies.load_cookie_header("xiaohongshu", explicit_file=xhs_cookie)
                self.assertIn("a1=xyz", header)
                self.assertIn("web_session=def", header)

    def test_xiaohongshu_ssr_gallery_and_download_media(self) -> None:
        import io
        source_url = "https://www.xiaohongshu.com/explore/0123456789abcdef01234567?xsec_token=SECRET"
        fake_state = {
            "note": {
                "noteDetailMap": {
                    "0123456789abcdef01234567": {
                        "note": {
                            "noteId": "0123456789abcdef01234567",
                            "title": "小红书无浏览器测试",
                            "desc": "第一段正文",
                            "type": "normal",
                            "time": 1700000000000,
                            "user": {"nickname": "小红书作者", "userId": "u123"},
                            "imageList": [
                                {"urlDefault": "https://sns-webpic-qc.xhscdn.com/test1.jpg"},
                                {"urlDefault": "https://sns-webpic-qc.xhscdn.com/test2.jpg"},
                            ],
                        }
                    }
                }
            }
        }
        fake_html = (
            f"<html><script>window.__INITIAL_STATE__ = {json.dumps(fake_state)};</script></html>"
        ).encode("utf-8")
        mock_response = io.BytesIO(fake_html)
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            output = run_dir / "metadata.json"
            with patch("urllib.request.urlopen", return_value=mock_response), \
                 patch("extract_metadata.download_single_asset", side_effect=lambda asset, rd, default_platform=None: {"filename": asset["filename"]}) as dl:
                result = extract_metadata.extract_metadata(
                    source_url, output, run_dir=run_dir, download_media=True
                )

            self.assertEqual(result["title"], "小红书无浏览器测试")
            self.assertEqual(result["uploader"], "小红书作者")
            self.assertEqual(result["media_type"], "gallery")
            self.assertEqual(result["image_count"], 2)
            self.assertEqual(result["downloaded_assets"], ["page-01.jpg", "page-02.jpg"])
            self.assertEqual(dl.call_count, 2)
            self.assertNotIn("SECRET", output.read_text(encoding="utf-8"))
            self.assertTrue((run_dir / "metadata.assets.json").is_file())


if __name__ == "__main__":
    unittest.main()
