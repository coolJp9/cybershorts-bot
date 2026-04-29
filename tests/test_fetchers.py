"""Tests for fetcher modules."""

import pytest
from unittest.mock import patch, MagicMock

from app.fetchers.rss import _parse_feed_time, _xml_text
from app.summarizer.story_selector import (
    story_category,
    heuristic_story_score,
    dedupe_stories,
)


class TestParseFeedTime:
    def test_rfc2822_format(self):
        ts = _parse_feed_time("Mon, 29 Apr 2024 10:00:00 +0000")
        assert isinstance(ts, int)
        assert ts > 0

    def test_iso8601_format(self):
        ts = _parse_feed_time("2024-04-29T10:00:00Z")
        assert isinstance(ts, int)
        assert ts > 0

    def test_empty_string_returns_zero(self):
        assert _parse_feed_time("") == 0

    def test_invalid_returns_zero(self):
        assert _parse_feed_time("not-a-date") == 0


class TestStoryCategory:
    def test_ransomware(self):
        assert story_category("Major ransomware attack hits UK hospitals") == "ransomware"

    def test_vulnerability(self):
        assert story_category("CVE-2024-1234 critical zero-day in OpenSSL") == "vulnerability"

    def test_breach(self):
        assert story_category("Data breach exposes 10 million user records") == "breach"

    def test_malware(self):
        assert story_category("New trojan targets banking apps") == "malware"

    def test_general_fallback(self):
        assert story_category("Interesting tech news today") == "general"


class TestHeuristicStoryScore:
    def _make_story(self, source, title, score=50, time=0):
        return {"source": source, "title": title, "score": score, "time": time}

    def test_high_trust_source_scores_higher(self):
        bc = self._make_story("BleepingComputer", "ransomware breach exploit")
        hn = self._make_story("HackerNews", "ransomware breach exploit")
        assert heuristic_story_score(bc) > heuristic_story_score(hn)

    def test_severity_words_boost_score(self):
        severe = self._make_story("HackerNews", "critical ransomware zero-day exploit breach")
        mild = self._make_story("HackerNews", "new security policy announced")
        assert heuristic_story_score(severe) > heuristic_story_score(mild)

    def test_returns_integer(self):
        result = heuristic_story_score(self._make_story("HackerNews", "hack"))
        assert isinstance(result, int)


class TestDedupeStories:
    def test_removes_duplicates(self):
        stories = [
            {"source": "A", "title": "Big Hack Attack", "score": 10, "time": 0},
            {"source": "B", "title": "Big hack attack!", "score": 5, "time": 0},
        ]
        result = dedupe_stories(stories)
        assert len(result) == 1

    def test_keeps_best_scored_duplicate(self):
        stories = [
            {"source": "LowQuality", "title": "Big Hack", "score": 5, "time": 0},
            {"source": "BleepingComputer", "title": "Big Hack", "score": 10, "time": 0},
        ]
        result = dedupe_stories(stories)
        assert len(result) == 1
        assert result[0]["source"] == "BleepingComputer"

    def test_adds_agent_score_and_category(self):
        stories = [{"source": "HackerNews", "title": "ransomware hits hospital", "score": 50, "time": 0}]
        result = dedupe_stories(stories)
        assert "agent_score" in result[0]
        assert "category" in result[0]
