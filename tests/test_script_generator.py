"""Tests for script generation and normalisation."""

import pytest
from unittest.mock import patch, MagicMock

from app.script_generator.generator import (
    normalize_script,
    heuristic_script_review,
    _static_script,
)


class TestNormalizeScript:
    def test_adds_breaking_prefix(self):
        result = normalize_script("Some important news here. Follow for daily cyber updates")
        assert result.startswith("BREAKING:")

    def test_preserves_existing_breaking(self):
        result = normalize_script("BREAKING: hack happened. Follow for daily cyber updates")
        assert result.startswith("BREAKING:")
        assert "BREAKING: BREAKING:" not in result

    def test_preserves_alert_prefix(self):
        result = normalize_script("ALERT: zero-day found. Follow for daily cyber updates")
        assert result.startswith("ALERT:")

    def test_adds_cta_when_missing(self):
        result = normalize_script("BREAKING: bad news here.")
        assert "Follow for daily cyber updates" in result

    def test_strips_label_prefix(self):
        result = normalize_script("Script: BREAKING: important news. Follow for daily cyber updates")
        assert not result.lower().startswith("script:")

    def test_truncates_long_scripts(self):
        long_text = "BREAKING: " + ("a " * 300) + "Follow for daily cyber updates"
        result = normalize_script(long_text)
        assert len(result) <= 430


class TestHeuristicReview:
    def _good_script(self):
        return "BREAKING: Critical vulnerability found in popular software. Patch immediately. Follow for daily cyber updates"

    def test_good_script_passes(self):
        review = heuristic_script_review(self._good_script(), "vulnerability found", "")
        assert review["approved"] is True
        assert review["score"] >= 7

    def test_missing_hook_penalized(self):
        script = "Some news happened today. Follow for daily cyber updates"
        review = heuristic_script_review(script, "news", "")
        assert "weak hook" in review["reason"]

    def test_missing_cta_penalized(self):
        script = "BREAKING: major hack detected worldwide"
        review = heuristic_script_review(script, "hack", "")
        assert "missing CTA" in review["reason"]

    def test_too_long_penalized(self):
        long_script = "BREAKING: " + ("x" * 410) + " Follow for daily cyber updates"
        review = heuristic_script_review(long_script, "hack", "")
        assert "too long" in review["reason"]

    def test_score_within_bounds(self):
        review = heuristic_script_review("", "title", "")
        assert 1 <= review["score"] <= 10


class TestStaticScript:
    def test_contains_breaking(self):
        result = _static_script("Ransomware hits hospital chain")
        assert result.startswith("BREAKING:")

    def test_contains_cta(self):
        result = _static_script("Ransomware hits hospital chain")
        assert "Follow for daily cyber updates" in result

    def test_truncates_long_title(self):
        long_title = "a" * 200
        result = _static_script(long_title)
        assert len(result) < 400
