"""Tests for Cookie-Editor multi-format parsing and Douyin compilation link resolution."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import sys
SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from manage_cookies import normalize_cookie_to_netscape, save_cookie_text, inspect_cookies, cookie_file_path
from sources import classify, extract


class CookieAndCompilationTests(unittest.TestCase):

    def test_cookie_editor_json_array_conversion(self):
        sample_json = json.dumps([
            {
                "domain": ".douyin.com",
                "expirationDate": 1822546640.635,
                "name": "sessionid",
                "path": "/",
                "secure": True,
                "value": "fake_session_12345"
            },
            {
                "domain": "www.douyin.com",
                "name": "s_v_web_id",
                "path": "/",
                "secure": False,
                "value": "verify_abc_xyz"
            }
        ])
        formatted = normalize_cookie_to_netscape(sample_json, platform="douyin")
        self.assertIn("# Netscape HTTP Cookie File", formatted)
        self.assertIn("sessionid\tfake_session_12345", formatted)
        self.assertIn("s_v_web_id\tverify_abc_xyz", formatted)
        self.assertIn(".douyin.com\tTRUE\t/\tTRUE\t1822546640\tsessionid", formatted)

    def test_cookie_header_string_conversion(self):
        header = "ttwid=test_ttwid_val; passport_csrf_token=csrf_123"
        formatted = normalize_cookie_to_netscape(header, platform="douyin")
        self.assertIn("# Netscape HTTP Cookie File", formatted)
        self.assertIn("ttwid\ttest_ttwid_val", formatted)
        self.assertIn("passport_csrf_token\tcsrf_123", formatted)

    def test_cookie_netscape_raw_preservation(self):
        raw_netscape = (
            "# Netscape HTTP Cookie File\n"
            ".douyin.com\tTRUE\t/\tTRUE\t2147483647\tmykey\tmyval\n"
        )
        formatted = normalize_cookie_to_netscape(raw_netscape, platform="douyin")
        self.assertIn("mykey\tmyval", formatted)

    def test_douyin_compilation_with_vid_classified_as_note(self):
        url = (
            "https://www.douyin.com/user/MS4wLjABAAAArrcjvD5kKlYsUGAlSO8QGrbtMTQA-n9Ts_-tQUJht5rp-zc_szHoITuNi1n3ZhJ_"
            "?from_tab_name=main&showSubTab=compilation&vid=7709104772577627455"
        )
        result = classify(url)
        self.assertEqual(result["kind"], "note")
        self.assertEqual(result["platform"], "douyin")
        self.assertEqual(result["note_id"], "7709104772577627455")
        self.assertEqual(result["canonical_url"], "https://www.douyin.com/video/7709104772577627455")
        self.assertEqual(result.get("compilation_context"), "douyin_user_compilation")

    def test_douyin_collection_direct_url(self):
        url = "https://www.douyin.com/collection/7709104772577627455"
        result = classify(url)
        self.assertEqual(result["kind"], "compilation")
        self.assertEqual(result["platform"], "douyin")
        self.assertEqual(result["mix_id"], "7709104772577627455")
        self.assertEqual(result["canonical_url"], "https://www.douyin.com/collection/7709104772577627455")

    def test_douyin_compilation_without_vid_classified_as_compilation(self):
        url = (
            "https://www.douyin.com/user/MS4wLjABAAAArrcjvD5kKlYsUGAlSO8QGrbtMTQA-n9Ts_-tQUJht5rp-zc_szHoITuNi1n3ZhJ_"
            "?from_tab_name=main&showSubTab=compilation"
        )
        result = classify(url)
        self.assertEqual(result["kind"], "compilation")
        self.assertEqual(result["platform"], "douyin")

    def test_douyin_pure_profile_still_rejected(self):
        url = "https://www.douyin.com/user/MS4wLjABAAAArrcjvD5kKlYsUGAlSO8QGrbtMTQA-n9Ts_-tQUJht5rp-zc_szHoITuNi1n3ZhJ_"
        result = classify(url)
        self.assertEqual(result["kind"], "profile")


if __name__ == "__main__":
    unittest.main()
