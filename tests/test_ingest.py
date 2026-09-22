"""Tests for ingest's extract/annotate steps: MultiQC unwrap + generic JSON passthrough.

Uses stdlib unittest (no extra dependency). Run with:
    python3 -m unittest discover tests
"""

from __future__ import annotations

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from ingest import (
    extract_report_saved_raw_data,
    annotate,
    split_text_sections,
    looks_like_multiqc_llms_full,
    split_multiqc_llms_full,
)


class TestExtractReportSavedRawData(unittest.TestCase):
    def test_extract_multiqc_wrapper_key(self):
        """MultiQC input is unwrapped to a flat {section: payload} dict."""
        data = {
            "report_saved_raw_data": {
                "multiqc_foo": {"sample_1": {"metric": 1}},
            },
            "report_plot_data": {},
        }
        reduced = extract_report_saved_raw_data(data)
        self.assertEqual(reduced, {"multiqc_foo": {"sample_1": {"metric": 1}}})

    def test_extract_multiqc_legacy_wrapper_key(self):
        """The legacy 'report_raw_saved_data' spelling is also unwrapped."""
        data = {"report_raw_saved_data": {"multiqc_bar": {"sample_1": {"metric": 2}}}}
        reduced = extract_report_saved_raw_data(data)
        self.assertEqual(reduced, {"multiqc_bar": {"sample_1": {"metric": 2}}})

    def test_extract_generic_passthrough(self):
        """JSON without a MultiQC wrapper key is treated as already section-keyed."""
        data = {
            "some_section": {"sample_1": {"metric_a": 1.2}, "sample_2": {"metric_a": 3.4}},
        }
        reduced = extract_report_saved_raw_data(data)
        self.assertEqual(reduced, data)


class TestAnnotate(unittest.TestCase):
    def setUp(self):
        self.reduced = {
            "some_section": {"sample_1": {"metric_a": 1.2}},
        }

    def test_annotate_without_descriptor(self):
        """Omitting the descriptor doesn't crash; sections get bare 'data'."""
        annotated = annotate(self.reduced)
        self.assertEqual(
            annotated,
            {"some_section": {"data": {"sample_1": {"metric_a": 1.2}}}},
        )

    def test_annotate_unmatched_section_passthrough(self):
        """A section with no matching descriptor entry keeps its key and gets bare 'data'."""
        descriptor = {"other_section": {"description": "not used"}}
        annotated = annotate(self.reduced, descriptor)
        self.assertIn("some_section", annotated)
        self.assertNotIn("other_section", annotated)
        self.assertEqual(annotated["some_section"], {"data": {"sample_1": {"metric_a": 1.2}}})


class TestSplitTextSections(unittest.TestCase):
    def test_splits_on_markdown_headings(self):
        text = "## Section One\nbody one\n## Section Two\nbody two\n"
        sections = split_text_sections(text)
        self.assertEqual(sections["Section One"], {"data": "body one"})
        self.assertEqual(sections["Section Two"], {"data": "body two"})

    def test_captures_preamble_before_first_heading(self):
        text = "intro text\n## Section One\nbody one\n"
        sections = split_text_sections(text)
        self.assertEqual(sections["Preamble"], {"data": "intro text"})
        self.assertEqual(sections["Section One"], {"data": "body one"})

    def test_duplicate_headings_get_suffixed(self):
        text = "## Section\nfirst\n## Section\nsecond\n"
        sections = split_text_sections(text)
        self.assertEqual(sections["Section"], {"data": "first"})
        self.assertEqual(sections["Section (2)"], {"data": "second"})

    def test_preamble_heading_collision_gets_suffixed(self):
        text = "intro text\n## Preamble\nbody text\n"
        sections = split_text_sections(text)
        self.assertEqual(sections["Preamble"], {"data": "intro text"})
        self.assertEqual(sections["Preamble (2)"], {"data": "body text"})

    def test_no_headings_falls_back_to_full_report(self):
        text = "just plain text with no headings\n"
        sections = split_text_sections(text)
        self.assertEqual(sections, {"Full report": {"data": "just plain text with no headings"}})

    def test_empty_input_returns_empty_dict(self):
        self.assertEqual(split_text_sections(""), {})
        self.assertEqual(split_text_sections("   \n  "), {})


class TestMultiqcLlmsFull(unittest.TestCase):
    SAMPLE = (
        "You are an expert bioinformatician. Summarize the findings.\n"
        "----------------------\n\n"
        "Tools used in the report:\n\n"
        "1. Sample Sheet\n"
        "Description: <p>The sample sheet provided as input.</p>\n\n"
        "----------------------\n\n"
        "2. Atlas Summary\n"
        "Description: <p>Summary of cells and genes.</p>\n\n"
        "----------------------\n\n"
        "----------------------\n\n"
        "Tool: Sample Sheet\n"
        "Section: \n"
        "Title: Sample Sheet\n\n"
        "Plot type: violin plot\n\n"
        "|sample|type|\n|---|---|\n|S1|visium|\n\n"
        "----------------------\n\n"
        "Tool: Unmatched Tool\n"
        "Section: \n"
        "Title: Unmatched Tool\n\n"
        "Plot type: violin plot\n\n"
        "|sample|value|\n|---|---|\n|S1|1|\n"
    )

    def test_looks_like_multiqc_llms_full_detects_layout(self):
        self.assertTrue(looks_like_multiqc_llms_full(self.SAMPLE))
        self.assertFalse(looks_like_multiqc_llms_full("## Section One\nbody\n"))

    def test_splits_one_chunk_per_tool_block(self):
        sections, leading = split_multiqc_llms_full(self.SAMPLE)
        self.assertIn("Sample Sheet", sections)
        self.assertIn("Unmatched Tool", sections)
        self.assertEqual(
            leading, "You are an expert bioinformatician. Summarize the findings."
        )

    def test_attaches_matching_index_description(self):
        sections, _ = split_multiqc_llms_full(self.SAMPLE)
        self.assertIn(
            "Description: The sample sheet provided as input.",
            sections["Sample Sheet"]["data"],
        )

    def test_unmatched_tool_has_no_description_prefix(self):
        sections, _ = split_multiqc_llms_full(self.SAMPLE)
        self.assertFalse(sections["Unmatched Tool"]["data"].startswith("Description:"))
        self.assertTrue(sections["Unmatched Tool"]["data"].startswith("Tool: Unmatched Tool"))

    def test_non_blank_section_appended_to_chunk_name(self):
        text = (
            "instructions\n----------------------\n\n"
            "Tool: Foo\nSection: Bar\nTitle: Foo Bar\n\ndata here\n"
        )
        sections, _ = split_multiqc_llms_full(text)
        self.assertIn("Foo \u2014 Bar", sections)


if __name__ == "__main__":
    unittest.main()
