"""Regression tests use synthetic notes only; never publish personal vault data."""
import datetime as dt
import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("validate_wiki", Path(__file__).parents[1] / "scripts" / "validate_wiki.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class WikiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "06 已归档/分类/中文 原文.md"
        self.summary = self.root / "04 wiki/sources/中文 摘要.md"
        self.source.parent.mkdir(parents=True)
        self.summary.parent.mkdir(parents=True)
        self.source.write_text('---\ndescription: |\n  多行中文摘要：含冒号\n  第二行\nkey_points:\n  - "引号与路径 C:\\\\资料"\nauthor: 作者甲\n---\n完整原文\n', encoding="utf-8")
        self.good = '---\ntype: source\nlast_updated: 2026-09-07\noriginal_path: "06 已归档/分类/中文 原文.md"\n---\n# 中文 摘要\n\n## 核心摘要\n\n多行中文摘要：含冒号。\n\n## 关键要点\n\n- 从正文提炼的要点。\n\n## 来源\n\n- 作者：作者甲\n- [[06 已归档/分类/中文 原文]]\n'
        self.summary.write_text(self.good, encoding="utf-8")
        (self.root / "04 wiki/index.md").write_text('---\ntype: wiki_index\nlast_updated: 2026-09-07\n---\n[[sources/中文 摘要]]\n', encoding="utf-8")

    def audit(self):
        return module.audit(self.root, today=dt.date(2026, 9, 7))

    def codes(self):
        return {x["code"] for x in self.audit()["issues"]}

    def test_healthy_read_only_and_unicode(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*.md")}
        result = self.audit()
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["content_gate_passed"], 1)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*.md")})

    def test_bom_crlf_multiline_and_quoted_paths(self):
        data, _ = module.read_note(self.source)
        self.assertIn("第二行", data["description"])
        self.assertIn("C:\\资料", data["key_points"][0])
        self.summary.write_bytes(b"\xef\xbb\xbf" + self.good.replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(self.audit()["issues"], [])

    def test_placeholder_not_complete(self):
        self.summary.write_text(self.good.replace("多行中文摘要：含冒号。", "原始资料未提供摘要。"), encoding="utf-8")
        self.assertIn("placeholder_content", self.codes())
        self.assertEqual(self.audit()["content_gate_passed"], 0)

    def test_empty_keypoints_not_complete(self):
        self.summary.write_text(self.good.replace("- 从正文提炼的要点。", ""), encoding="utf-8")
        self.assertIn("missing_content", self.codes())

    def test_parse_error_is_not_missing_metadata(self):
        self.source.write_text("---\ndescription: [broken\n---\n正文", encoding="utf-8")
        self.assertIn("original_parse_error", self.codes())
        self.assertEqual(self.audit()["content_gate_passed"], 0)

    def test_duplicate_yaml_keys_rejected(self):
        self.summary.write_text(self.good.replace("type: source", "type: source\ntype: entity"), encoding="utf-8")
        self.assertIn("parse_error", self.codes())

    def test_duplicate_mapping_is_not_coverage(self):
        self.summary.with_name("重复.md").write_text(self.good, encoding="utf-8")
        self.assertIn("duplicate_original", self.codes())
        self.assertEqual(self.audit()["content_gate_passed"], 0)
        self.assertEqual(self.audit()["mapped_original_count"], 1)

    def test_outside_archive_rejected(self):
        self.summary.write_text(self.good.replace("06 已归档/分类/中文 原文.md", "../outside.md"), encoding="utf-8")
        self.assertIn("missing_original", self.codes())

    def test_dropped_existing_metadata_rejected(self):
        self.summary.write_text(self.good.replace("作者：作者甲", "作者：—"), encoding="utf-8")
        self.assertIn("metadata_dropped", self.codes())

    def test_conflict_without_status_reported(self):
        self.summary.write_text(self.good + "\n> [!WARNING] 观点分歧\n> - 两种观点\n", encoding="utf-8")
        self.assertIn("conflict_status_missing", self.codes())
        self.assertEqual(self.audit()["warnings"][0]["code"], "unresolved_conflict")

    def test_broken_link_and_code_example(self):
        self.summary.write_text(self.good + "\n`[[示例]]`\n[[不存在]]\n", encoding="utf-8")
        broken = [x["detail"] for x in self.audit()["issues"] if x["code"] == "broken_link"]
        self.assertEqual(broken, ["不存在"])

    def test_missing_original_detected_even_when_counts_equal(self):
        self.source.with_name("第二篇.md").write_bytes(self.source.read_bytes())
        self.summary.with_name("重复.md").write_text(self.good, encoding="utf-8")
        result = self.audit()
        self.assertEqual(result["source_page_count"], result["archive_count"])
        self.assertEqual(len(result["unmapped_originals"]), 1)

    def test_index_placeholder(self):
        index = self.root / "04 wiki/index.md"
        index.write_text(index.read_text(encoding="utf-8") + "原始资料未提供摘要。", encoding="utf-8")
        self.assertIn("index_placeholder", self.codes())

    def test_stale_date(self):
        self.summary.write_text(self.good.replace("2026-09-07", "2025-01-01"), encoding="utf-8")
        self.assertIn("stale", {x["code"] for x in self.audit()["warnings"]})

    def test_home_counts(self):
        (self.root / "04 wiki/_home.md").write_text("---\ntype: wiki_home\nlast_updated: 2026-09-07\n---\n| 原始资料 | 内容门禁通过 | 待处理 |\n|---|---|---|\n| **1** | **0** | **1** |\n", encoding="utf-8")
        self.assertIn("home_counts_mismatch", self.codes())


if __name__ == "__main__":
    unittest.main()
