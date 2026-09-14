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

    def add_entity(self, name="甲", object_id="E-1", source_refs=None, body_refs=None, extra=""):
        if source_refs is None:
            source_refs = ["04 wiki/sources/中文 摘要.md"]
        if body_refs is None:
            body_refs = ["sources/中文 摘要"]
        refs = "\n".join(f"  - \"{ref}\"" for ref in source_refs)
        body = "\n".join(f"- [[{ref}]]" for ref in body_refs)
        text = (f"---\ntype: entity\nlast_updated: 2026-09-07\nknowledge_schema: 1\n"
                f"object_id: {object_id}\nidentity_evidence:\n  - registry\naliases: []\n"
                f"source_refs:\n{refs}\nsource_count: {len(source_refs)}\n---\n# {name}\n\n{body}\n{extra}")
        path = self.root / f"04 wiki/entities/{name}.md"
        path.parent.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_entity_schema_and_multi_source_deduplicates_body_links(self):
        self.add_entity(extra="[[sources/中文 摘要]]\n")
        result = self.audit()
        self.assertNotIn("source_count_mismatch", {x["code"] for x in result["issues"]})
        self.assertEqual(result["canonical_page_count"], 1)
        self.assertEqual(result["redirect_page_count"], 0)

    def test_old_entity_source_count_remains_compatible(self):
        path = self.root / "04 wiki/entities/旧实体.md"
        path.parent.mkdir(exist_ok=True)
        path.write_text('---\ntype: entity\nlast_updated: 2026-09-07\nsource_count: 1\n---\n[[sources/中文 摘要]]\n', encoding="utf-8")
        self.assertNotIn("invalid_knowledge_schema", self.codes())
        self.assertNotIn("source_count_mismatch", self.codes())

    def test_two_sources_and_entity_health_aggregate(self):
        source2 = self.root / "06 已归档/分类/第二原文.md"
        source2.write_text(self.source.read_text(encoding="utf-8"), encoding="utf-8")
        summary2 = self.root / "04 wiki/sources/第二摘要.md"
        summary2.write_text(self.good.replace("中文 摘要.md", "第二摘要.md").replace("中文 原文.md", "第二原文.md").replace("中文 摘要", "第二摘要"), encoding="utf-8")
        entity = self.add_entity(source_refs=["04 wiki/sources/中文 摘要.md", "04 wiki/sources/第二摘要.md"], body_refs=["sources/中文 摘要", "sources/第二摘要"])
        index = self.root / "04 wiki/index.md"
        index.write_text(index.read_text(encoding="utf-8") + "\n[[entities/甲]]\n", encoding="utf-8")
        result = self.audit()
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["content_gate_passed"], 2)

    def test_same_name_different_object_ids_are_allowed(self):
        self.add_entity("同名", "E-1")
        self.add_entity("同名-副本", "E-2")
        self.assertNotIn("duplicate_object_id", self.codes())

    def test_duplicate_object_id_is_reported(self):
        self.add_entity("甲一", "E-1")
        self.add_entity("甲二", "E-1")
        self.assertIn("duplicate_object_id", self.codes())

    def test_new_schema_rejects_bad_lists_and_paths(self):
        self.add_entity(source_refs=["../outside.md"], body_refs=["sources/中文 摘要"])
        codes = self.codes()
        self.assertIn("invalid_source_refs", codes)
        self.assertIn("source_count_mismatch", codes)

    def test_source_refs_must_match_body_links(self):
        self.add_entity(source_refs=[], body_refs=["sources/中文 摘要"])
        self.assertIn("source_count_mismatch", self.codes())

    def test_valid_redirect_and_counts(self):
        self.add_entity("新", "E-new")
        path = self.root / "04 wiki/entities/旧.md"
        path.write_text('---\ntype: redirect\nlast_updated: 2026-09-07\nknowledge_schema: 1\ncanonical_path: "04 wiki/entities/新.md"\naliases: [旧称]\n---\n[[04 wiki/entities/新]]\n', encoding="utf-8")
        result = self.audit()
        codes = {x["code"] for x in result["issues"]}
        self.assertNotIn("invalid_canonical_target", codes)
        self.assertNotIn("invalid_type", codes)
        self.assertEqual(result["redirect_page_count"], 1)

    def test_redirect_bad_target_and_forbidden_identity(self):
        path = self.root / "04 wiki/entities/旧.md"
        path.parent.mkdir(exist_ok=True)
        path.write_text('---\ntype: redirect\nlast_updated: 2026-09-07\nknowledge_schema: 1\ncanonical_path: "../x.md"\nobject_id: bad\n---\n', encoding="utf-8")
        codes = self.codes()
        self.assertIn("invalid_canonical_path", codes)
        self.assertIn("redirect_forbidden_field", codes)

    def test_redirect_self_is_rejected(self):
        path = self.root / "04 wiki/entities/自己.md"
        path.parent.mkdir(exist_ok=True)
        path.write_text('---\ntype: redirect\nlast_updated: 2026-09-07\nknowledge_schema: 1\ncanonical_path: "04 wiki/entities/自己.md"\n---\n[[04 wiki/entities/自己]]\n', encoding="utf-8")
        self.assertIn("redirect_self", self.codes())

    def test_two_audits_are_read_only(self):
        self.add_entity()
        self.add_redirect("旧甲", "04 wiki/entities/甲.md")
        before = {p: p.read_bytes() for p in self.root.rglob("*.md")}
        first, second = self.audit(), self.audit()
        self.assertEqual(first, second)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*.md")})

    def change_metadata(self, path, **updates):
        data, body = module.read_note(path)
        data.update(updates)
        path.write_text("---\n" + module.yaml.safe_dump(data, allow_unicode=True) + "---\n" + body, encoding="utf-8")

    def add_redirect(self, name, target, body=None, directory="entities"):
        path = self.root / f"04 wiki/{directory}/{name}.md"
        path.parent.mkdir(exist_ok=True)
        data = {"type": "redirect", "knowledge_schema": 1, "last_updated": "2026-09-07", "canonical_path": target}
        path.write_text("---\n" + module.yaml.safe_dump(data, allow_unicode=True) + "---\n"
                        + (f"[[{target}]]\n" if body is None else body), encoding="utf-8")
        return path

    def test_schema_type_empty_and_duplicate_values(self):
        cases = [
            ("knowledge_schema", True, "invalid_knowledge_schema"),
            ("knowledge_schema", "1", "invalid_knowledge_schema"),
            ("object_id", [], "invalid_object_id"),
            ("identity_evidence", [], "invalid_identity_evidence"),
            ("identity_evidence", [None], "invalid_identity_evidence"),
            ("aliases", [" "], "invalid_aliases"),
            ("aliases", ["旧称", "旧称"], "invalid_aliases"),
            ("aliases", [{}], "invalid_aliases"),
            ("source_refs", [], "invalid_source_refs"),
            ("source_refs", {}, "invalid_source_refs"),
            ("source_refs", [{}], "invalid_source_refs"),
            ("source_refs", ["04 wiki/sources/中文 摘要.md"] * 2, "invalid_source_refs"),
            ("source_count", True, "invalid_source_count"),
            ("source_count", -1, "invalid_source_count"),
        ]
        for field, value, code in cases:
            with self.subTest(field=field, value=value):
                path = self.add_entity()
                self.change_metadata(path, **{field: value})
                self.assertIn(code, self.codes())

    def test_partial_schema_does_not_bypass_validation(self):
        path = self.add_entity()
        path.write_text(path.read_text(encoding="utf-8").replace("knowledge_schema: 1\n", ""), encoding="utf-8")
        self.assertIn("invalid_knowledge_schema", self.codes())

    def test_old_source_count_mismatch_still_detected(self):
        path = self.add_entity()
        path.write_text('---\ntype: entity\nlast_updated: 2026-09-07\nsource_count: 2\naliases: [旧称]\n---\n[[sources/中文 摘要]]\n', encoding="utf-8")
        self.assertIn("source_count_mismatch", self.codes())
        self.assertNotIn("invalid_knowledge_schema", self.codes())

    def test_source_target_and_portable_path_validation(self):
        for ref in ["/tmp/x.md", "C:/notes/x.md", "C:\\notes\\x.md", "../x.md", "a//x.md", "a/./x.md", "x\x00.md", "x#heading.md", "x|alias.md"]:
            with self.subTest(ref=ref):
                path = self.add_entity()
                self.change_metadata(path, source_refs=[ref])
                self.assertIn("invalid_source_refs", self.codes())
        for ref in ["04 wiki/sources/missing.md", "04 wiki/index.md", "06 已归档/分类/中文 原文.md"]:
            with self.subTest(ref=ref):
                path = self.add_entity()
                self.change_metadata(path, source_refs=[ref])
                self.assertIn("invalid_source_ref", self.codes())
        self.change_metadata(self.summary, type="entity")
        self.add_entity()
        self.assertIn("invalid_source_ref", self.codes())

    def test_redirect_cycles_chains_and_nonentity_targets(self):
        self.add_entity()
        self.add_redirect("入口甲", "04 wiki/entities/入口乙.md")
        self.add_redirect("入口乙", "04 wiki/entities/入口甲.md")
        self.assertIn("redirect_chain", self.codes())
        self.add_redirect("入口乙", "04 wiki/entities/甲.md")
        self.assertIn("redirect_chain", self.codes())
        for target in ["04 wiki/sources/中文 摘要.md", "04 wiki/index.md", "04 wiki/entities/不存在.md"]:
            with self.subTest(target=target):
                self.add_redirect("错误入口", target)
                self.assertIn("invalid_canonical_target", self.codes())

    def test_redirect_requires_body_link_and_correct_location(self):
        self.add_entity()
        self.add_redirect("无链接", "04 wiki/entities/甲.md", body="迁移说明但没有双链")
        self.assertIn("redirect_body_link_missing", self.codes())
        self.add_redirect("错误位置", "04 wiki/entities/甲.md", directory="insights")
        self.assertIn("invalid_redirect_location", self.codes())

    def test_healthy_redirect_has_no_issues(self):
        self.add_entity()
        self.add_redirect("旧甲", "04 wiki/entities/甲.md")
        index = self.root / "04 wiki/index.md"
        index.write_text(index.read_text(encoding="utf-8") + "\n[[entities/旧甲]]\n", encoding="utf-8")
        self.assertEqual(self.audit()["issues"], [])


if __name__ == "__main__":
    unittest.main()
