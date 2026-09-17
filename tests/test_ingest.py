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

from ingest import extract_report_saved_raw_data, annotate


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


if __name__ == "__main__":
    unittest.main()
