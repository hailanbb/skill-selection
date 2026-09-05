from __future__ import annotations

import contextlib
import io
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

from PIL import Image
from common import CONFIG_ENV, load_config, split_frontmatter, validation_issues, write_json
from configure import main as configure_main
from fetch_asset import fetch, validate_url
from publish_note import existing_notes, publish
from run_workspace import create_workspace, validate_workspace
from sources import canonical_note, classify, extract

NOTE_ID = "0123456789abcdef01234567"
SOURCE = f"https://www.xiaohongshu.com/explore/{NOTE_ID}"


class SourceTests(unittest.TestCase):
    def test_share_text_and_signature_redaction(self):
        result = extract(f"小红书分享 看看这篇 {SOURCE}?xsec_token=SECRET&xsec_source=pc_share 。")
        self.assertEqual(result[0]["canonical_url"], SOURCE)
        self.assertNotIn("SECRET", json.dumps(result))

    def test_note_routes_and_case(self):
        for path in (f"explore/{NOTE_ID.upper()}", f"discovery/item/{NOTE_ID}",
                     f"user/profile/{'f' * 24}/{NOTE_ID}"):
            self.assertEqual(classify("https://www.xiaohongshu.com/" + path)["note_id"], NOTE_ID)

    def test_short_links_remain_unresolved(self):
        for host in ("xhslink.com", "xhslink.cn"):
            self.assertEqual(classify(f"http://{host}/a/Example")["kind"], "short")

    def test_profile_and_favorites_are_not_collected(self):
        profile = f"https://www.xiaohongshu.com/user/profile/{'f' * 24}"
        self.assertEqual(classify(profile)["kind"], "profile")
        self.assertEqual(classify(profile + "?tab=fav&subTab=note")["action"],
                         "request_a_specific_note_link_do_not_collect_profile")
        with self.assertRaises(ValueError):
            canonical_note(profile)

    def test_reject_lookalike_credential_port_and_malformed(self):
        for url in (SOURCE.replace(".com/", ".com.evil.test/"),
                    SOURCE.replace("https://", "https://name:secret@"),
                    SOURCE.replace(".com/", ".com:8080/"), "https://[broken", "file:///C:/note"):
            self.assertEqual(classify(url)["kind"], "unsupported")

    def test_asset_url_blocks_non_cdn_before_dns(self):
        with patch("socket.getaddrinfo") as dns:
            for url in ("http://img.xhscdn.com/a.jpg", "https://xhscdn.com.evil.test/a.jpg",
                        "https://127.0.0.1/a.jpg", "https://user:pass@img.xhscdn.com/a.jpg"):
                with self.assertRaises(ValueError):
                    validate_url(url)
            dns.assert_not_called()

    def test_asset_url_rejects_private_dns(self):
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
            with self.assertRaises(ValueError):
                validate_url("https://img.xhscdn.com/a.jpg")


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="xhs-test-")
        self.root = Path(self.temporary.name)
        self.vault = self.root / "中文库 [样例] & O'Brien"
        (self.vault / ".obsidian").mkdir(parents=True)
        self.notes = self.vault / "01 笔记"
        self.images = self.vault / "98 图片"
        self.notes.mkdir()
        self.images.mkdir()
        self.config = self.root / "私有配置.json"
        self.env = patch.dict(os.environ, {CONFIG_ENV: str(self.config)})
        self.env.start()
        write_json(self.config, {"vault_root": str(self.vault), "note_dir": str(self.notes), "image_dir": str(self.images)})
        self.run = create_workspace(self.root)
        Image.new("RGB", (1200, 800), "#336699").save(self.run / "原图 一.png")
        self.meta = {
            "source_url": SOURCE, "title": "种植方法：土壤与光照", "author": "示例作者：小林",
            "publish_time": "", "media_type": "gallery", "content_basis": "text_and_images",
            "gallery_coverage": {"expected_count": 1, "reviewed_positions": [1]}, "limitations": [],
            "assets": [{"path": "原图 一.png", "role": "image", "position": 1,
                        "inspected": True, "caption": "第 1 图：土壤观察位置。"}],
        }
        self.manifest = self.run / "evidence.json"
        self.draft = self.run / "draft.md"
        self.draft.write_text("# 种植方法\n\n观察土壤和光照后调整浇水。\n\n{{image:1}}\n", encoding="utf-8")

    def tearDown(self):
        self.env.stop()
        self.temporary.cleanup()

    def save(self, **kwargs):
        write_json(self.manifest, self.meta)
        return publish(self.manifest, self.draft, self.run, **kwargs)

    def test_gallery_end_to_end_unicode_dimensions_and_links(self):
        result = self.save()
        self.assertEqual(result["status"], "published")
        note = Path(result["note"])
        raw = note.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        text = raw.decode("utf-8")
        attrs, _ = split_frontmatter(text)
        self.assertEqual(attrs["title"], self.meta["title"])
        self.assertEqual(attrs["author"], self.meta["author"])
        self.assertEqual(len(attrs), 8)
        self.assertEqual(attrs["origin"], "小红书")
        self.assertFalse(validation_issues(text, note, self.vault))
        target = self.vault / result["images"][0]
        self.assertRegex(target.name, r"^[a-f0-9]{32}_0\.png$")
        with Image.open(target) as image:
            self.assertEqual(image.size, (1200, 800))
            self.assertFalse(image.getexif())
        self.assertFalse((self.vault / ".xiaohongshu-obsidian-note.publish.lock").exists())
        self.assertEqual(len(list(self.notes.iterdir())), 1)

    def test_duplicate_note_skipped_despite_new_title_and_token(self):
        first = self.save()
        renamed = Path(first["note"]).with_name("用户手动重命名.md")
        Path(first["note"]).rename(renamed)
        self.meta["title"] = "完全不同的主题名称"
        self.meta["source_url"] = SOURCE + "?xsec_token=SECRET"
        second = self.save()
        self.assertEqual(second["status"], "skipped_existing")
        self.assertEqual(Path(second["note"]), renamed)
        self.assertEqual(len(list(self.images.iterdir())), 1)

    def test_same_title_different_note_does_not_overwrite(self):
        first = self.save()
        old = Path(first["note"]).read_bytes()
        self.meta["source_url"] = SOURCE[:-1] + "8"
        second = self.save()
        self.assertNotEqual(first["note"], second["note"])
        self.assertEqual(Path(first["note"]).read_bytes(), old)
        self.assertEqual(len(list(self.images.iterdir())), 1)

    def test_missing_page_rejected_unless_explicit_partial_with_reason(self):
        self.meta["gallery_coverage"]["expected_count"] = 18
        with self.assertRaisesRegex(ValueError, "Incomplete evidence"):
            self.save()
        with self.assertRaisesRegex(ValueError, "concrete reason"):
            self.save(allow_partial=True)
        self.meta["limitations"] = ["其余图片无法加载，用户接受仅整理已核实部分。"]
        result = self.save(allow_partial=True)
        self.assertIn("18 张", Path(result["note"]).read_text(encoding="utf-8"))

    def test_video_frames_and_visual_only_boundary(self):
        self.meta.update(media_type="video", content_basis="visual_only", video_reviewed_to_end=True, video_duration_seconds=60)
        self.meta["assets"][0].update(role="frame", timestamp_seconds=12.5)
        result = self.save(frame_width=640)
        self.assertIn("未核实口播", Path(result["note"]).read_text(encoding="utf-8"))
        with Image.open(self.vault / result["images"][0]) as image:
            self.assertEqual(image.width, 640)
        self.assertTrue(result["images"][0].endswith("_640.jpg"))

    def test_incomplete_video_cannot_claim_complete(self):
        self.meta.update(media_type="video", content_basis="asr_and_frames", video_reviewed_to_end=False, video_duration_seconds=60)
        self.meta["assets"][0].update(role="frame", timestamp_seconds=1)
        with self.assertRaisesRegex(ValueError, "Incomplete evidence"):
            self.save()

    def test_uninspected_image_rejected(self):
        self.meta["assets"][0]["inspected"] = False
        with self.assertRaises(ValueError):
            self.save()
        self.assertEqual(list(self.images.iterdir()), [])

    def test_frame_outside_video_duration_rejected(self):
        self.meta.update(media_type="video", content_basis="asr_and_frames", video_reviewed_to_end=True, video_duration_seconds=5)
        self.meta["assets"][0].update(role="frame", timestamp_seconds=6)
        with self.assertRaisesRegex(ValueError, "duration"):
            self.save()

    def test_transparency_is_preserved(self):
        path = self.run / "原图 一.png"
        Image.new("RGBA", (40, 40), (12, 34, 56, 0)).save(path)
        result = self.save()
        with Image.open(self.vault / result["images"][0]) as image:
            self.assertEqual(image.mode, "RGBA")
            self.assertEqual(image.getpixel((0, 0)), (12, 34, 56, 0))

    def test_mixed_media_requires_both_kinds_of_evidence(self):
        self.meta.update(media_type="mixed", content_basis="visual_only", video_reviewed_to_end=True, video_duration_seconds=30)
        with self.assertRaisesRegex(ValueError, "both"):
            self.save()
        self.meta["assets"].append({"path": "原图 一.png", "role": "frame", "timestamp_seconds": 2,
                                    "inspected": True, "caption": "动态片段第 2 秒的动作细节。"})
        self.draft.write_text("# 混合示例\n\n静态条件与动态步骤。\n{{image:1}}\n{{image:2}}", encoding="utf-8")
        result = self.save()
        self.assertEqual(len(result["images"]), 2)

    def test_source_lookup_cli_returns_existing_note_without_token(self):
        result = self.save()
        process = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / "sources.py"),
                                  "--stdin", "--check-existing"], input=SOURCE + "?xsec_token=SECRET",
                                 encoding="utf-8", capture_output=True, check=True)
        self.assertNotIn("SECRET", process.stdout + process.stderr)
        item = json.loads(process.stdout)["items"][0]
        self.assertEqual(item["note"], result["note"])
        self.assertEqual(item["status"], "already_saved")

    def test_download_mocked_response_creates_media_without_overwrite(self):
        from email.message import Message
        from unittest.mock import MagicMock
        request = self.run / "request.json"
        write_json(request, {"url": "https://img.xhscdn.com/observed", "kind": "image", "filename": "下载图.jpg"})
        response = MagicMock()
        response.headers = Message()
        response.headers["Content-Type"] = "image/jpeg"
        response.read.side_effect = [b"synthetic bytes", b""]
        response.__enter__.return_value = response
        opener = MagicMock()
        opener.open.return_value = response
        with patch("fetch_asset.validate_url", side_effect=lambda value: value), patch("fetch_asset.build_opener", return_value=opener):
            result = fetch(request, self.run)
            self.assertEqual(Path(result["path"]).read_bytes(), b"synthetic bytes")
            with self.assertRaises(FileExistsError):
                fetch(request, self.run)
        self.assertEqual(list(self.run.glob("*.part")), [])

    def test_download_html_response_removes_partial_file(self):
        from email.message import Message
        from unittest.mock import MagicMock
        request = self.run / "request.json"
        write_json(request, {"url": "https://img.xhscdn.com/observed", "kind": "image", "filename": "下载图.jpg"})
        response = MagicMock()
        response.headers = Message()
        response.headers["Content-Type"] = "text/html"
        response.__enter__.return_value = response
        opener = MagicMock()
        opener.open.return_value = response
        with patch("fetch_asset.validate_url", side_effect=lambda value: value), patch("fetch_asset.build_opener", return_value=opener):
            with self.assertRaises(ValueError):
                fetch(request, self.run)
        self.assertFalse((self.run / "下载图.jpg").exists())
        self.assertEqual(list(self.run.glob("*.part")), [])

    def test_html_disguised_as_jpeg_rejected(self):
        bad = self.run / "login.jpg"
        bad.write_text("<html>请登录</html>", encoding="utf-8")
        self.meta["assets"][0]["path"] = bad.name
        with self.assertRaises(OSError):
            self.save()
        self.assertEqual(list(self.notes.iterdir()), [])

    def test_asset_outside_run_rejected(self):
        outside = self.root / "用户原件.png"
        Image.new("RGB", (16, 16)).save(outside)
        self.meta["assets"][0]["path"] = str(outside)
        with self.assertRaisesRegex(ValueError, "inside"):
            self.save()
        self.assertTrue(outside.exists())

    def test_reject_transcript_checklist_private_link_and_unresolved_image(self):
        for body in ("## 附录：完整逐字稿\n\n{{image:1}}", "- [ ] 做一遍\n{{image:1}}",
                     "访问 ?xsec_token=SECRET\n{{image:1}}", "无图摘要", "{{image:2}}", "{{image:1}} {{image:bad}}"):
            with self.subTest(body=body):
                self.draft.write_text(body, encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.save()
                self.assertEqual(list(self.images.iterdir()), [])

    def test_publish_failure_rolls_back_only_new_assets(self):
        old = self.images / "用户既有图片.png"
        old.write_bytes(b"existing-user-data")
        with patch("publish_note.os.link", side_effect=OSError("Simulated unsupported filesystem")):
            with self.assertRaises(OSError):
                self.save()
        self.assertEqual(list(self.images.iterdir()), [old])
        self.assertEqual(old.read_bytes(), b"existing-user-data")
        self.assertEqual(list(self.notes.iterdir()), [])

    def test_existing_lock_is_not_removed(self):
        lock = self.vault / ".xiaohongshu-obsidian-note.publish.lock"
        lock.write_text("another task", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            self.save()
        self.assertEqual(lock.read_text(encoding="utf-8"), "another task")

    def test_cleanup_deletes_only_marked_workspace(self):
        published = self.save()
        note = Path(published["note"])
        note_bytes = note.read_bytes()
        final_images = [self.vault / path for path in published["images"]]
        for relative in ("source.mp4", "audio.wav", "asr/transcript.srt", "asr/result.json",
                         "candidates/frame.jpg", "logs/download.log", "cache/temporary.bin"):
            artifact = self.run / relative
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_bytes(b"test-only intermediate data")
        original = self.root / "用户视频.mp4"
        original.write_bytes(b"user-original")
        result = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / "run_workspace.py"),
                                 "cleanup", "--path", str(self.run)], capture_output=True,
                                encoding="utf-8", check=True)
        self.assertTrue(json.loads(result.stdout)["cleaned"])
        self.assertFalse(self.run.exists())
        self.assertTrue(original.exists())
        self.assertEqual(note.read_bytes(), note_bytes)
        self.assertTrue(all(path.is_file() for path in final_images))
        for target in (self.vault, self.root):
            with self.assertRaises(ValueError):
                validate_workspace(target)

    def test_failure_finally_cleanup_preserves_user_original(self):
        original = self.root / "用户原视频.mp4"
        original.write_bytes(b"user-original")
        (self.run / "source.mp4").write_bytes(b"temporary-video-copy")
        self.meta["assets"][0]["inspected"] = False
        try:
            with self.assertRaises(ValueError):
                self.save()
        finally:
            result = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / "run_workspace.py"),
                                     "cleanup", "--path", str(self.run)], cwd=self.root,
                                    capture_output=True, encoding="utf-8", check=True)
        self.assertTrue(json.loads(result.stdout)["cleaned"])
        self.assertFalse(self.run.exists())
        self.assertEqual(original.read_bytes(), b"user-original")
        self.assertEqual(list(self.notes.iterdir()), [])
        self.assertEqual(list(self.images.iterdir()), [])

    def test_config_invalid_path_does_not_create_external_directory(self):
        outside = self.root / "库外附件"
        argv = ["configure.py", "--note-dir", str(self.notes), "--image-dir", str(outside),
                "--vault-root", str(self.vault), "--create-dirs"]
        with patch.object(sys, "argv", argv), self.assertRaises(SystemExit):
            configure_main()
        self.assertFalse(outside.exists())

    def test_configure_roundtrip_via_cli(self):
        images = self.vault / "附件目录 空格"
        argv = ["configure.py", "--note-dir", str(self.notes), "--image-dir", str(images), "--create-dirs"]
        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(configure_main(), 0)
        self.assertTrue(json.loads(output.getvalue())["configured"])
        self.assertEqual(load_config()["image_dir"], str(images.resolve()))
        self.assertFalse(self.config.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_cli_from_arbitrary_working_directory(self):
        write_json(self.manifest, self.meta)
        command = [sys.executable, "-X", "utf8", str(SCRIPTS / "publish_note.py"),
                   "--manifest", str(self.manifest), "--draft", str(self.draft), "--run-dir", str(self.run)]
        result = subprocess.run(command, cwd=self.root, capture_output=True, encoding="utf-8", check=True)
        note = json.loads(result.stdout)["note"]
        result = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / "validate_note.py"),
                                 "--note", note], cwd=self.root, capture_output=True, encoding="utf-8", check=True)
        self.assertTrue(json.loads(result.stdout)["valid"])


if __name__ == "__main__":
    unittest.main()
