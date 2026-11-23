#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Unit tests for event-retrospective-report embed_event_photos script."""

import os
import shutil
import tempfile
import unittest
import importlib.util
from pathlib import Path
from PIL import Image

# Dynamically import embed_event_photos from scripts
script_path = Path(__file__).resolve().parents[1] / "scripts" / "embed_event_photos.py"
spec = importlib.util.spec_from_file_location("embed_event_photos", script_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
embed_photos = module.embed_photos

class TestEmbedEventPhotos(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.photo_dir = os.path.join(self.temp_dir, "photos")
        os.makedirs(self.photo_dir, exist_ok=True)
        
        # Create 2 mock test images
        img1 = Image.new("RGB", (600, 400), color=(7, 110, 225))
        img1.save(os.path.join(self.photo_dir, "01.jpg"))
        
        img2 = Image.new("RGB", (400, 600), color=(16, 185, 129))
        img2.save(os.path.join(self.photo_dir, "02.jpg"))
        
        # Create a mock target HTML file
        self.html_path = os.path.join(self.temp_dir, "report.html")
        sample_html = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
  <main>
    <div id="overview">Overview</div>
    <!-- 报告尾部 -->
    <footer>Footer</footer>
  </main>
</body>
</html>"""
        with open(self.html_path, "w", encoding="utf-8") as f:
            f.write(sample_html)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_embed_photos_success(self):
        result = embed_photos(self.photo_dir, self.html_path, max_dim=800, quality=75)
        self.assertTrue(result)
        
        with open(self.html_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        self.assertIn("id=\"photos\"", content)
        self.assertIn("data:image/jpeg;base64,", content)
        self.assertIn("01", content)
        self.assertIn("02", content)

    def test_nonexistent_dir(self):
        result = embed_photos("non_existent_dir_12345", self.html_path)
        self.assertFalse(result)

if __name__ == "__main__":
    unittest.main()
