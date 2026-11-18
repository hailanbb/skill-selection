import unittest
import sys
import os

# Add scripts directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
from pikpak_organizer_pro import parse_code_and_check_ad

class TestCodeParser(unittest.TestCase):
    def test_standard_codes(self):
        code, is_ad = parse_code_and_check_ad("IPX-123.mp4")
        self.assertFalse(is_ad)
        self.assertEqual(code, "IPX-123")

        code, is_ad = parse_code_and_check_ad("sone-210.restored.mp4")
        self.assertFalse(is_ad)
        self.assertEqual(code, "SONE-210")

    def test_fc2_codes(self):
        code, is_ad = parse_code_and_check_ad("FC2-PPV-1234567.mp4")
        self.assertFalse(is_ad)
        self.assertEqual(code, "FC2-PPV-1234567")

    def test_ad_filtering(self):
        code, is_ad = parse_code_and_check_ad("澳门新葡京免费送.mp4")
        self.assertTrue(is_ad)

        code, is_ad = parse_code_and_check_ad("IPX-123_台妹子福利.mp4")
        self.assertTrue(is_ad)

if __name__ == "__main__":
    unittest.main()
