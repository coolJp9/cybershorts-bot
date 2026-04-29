"""Tests for utility modules."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.utils.deduplication import story_hash, load_used_titles, mark_used_title
from app.utils.retry import retry_call
from app.utils.models import VideoJob


class TestStoryHash:
    def test_same_title_produces_same_hash(self):
        assert story_hash("Big Hack Attack!") == story_hash("Big Hack Attack!")

    def test_stop_words_ignored(self):
        h1 = story_hash("the big hack")
        h2 = story_hash("a big hack")
        assert h1 == h2

    def test_hash_length(self):
        assert len(story_hash("anything")) == 12

    def test_different_titles_differ(self):
        assert story_hash("ransomware hits hospital") != story_hash("phishing scam exposed")


class TestRetryCall:
    def test_succeeds_on_first_attempt(self):
        calls = []
        def fn():
            calls.append(1)
            return "ok"
        result = retry_call("test", fn, attempts=3)
        assert result == "ok"
        assert len(calls) == 1

    def test_retries_on_failure(self):
        calls = []
        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise ValueError("transient")
            return "ok"
        result = retry_call("test", fn, attempts=3, delay=0.0)
        assert result == "ok"
        assert len(calls) == 3

    def test_raises_after_all_attempts(self):
        def fn():
            raise RuntimeError("always fails")
        with pytest.raises(RuntimeError):
            retry_call("test", fn, attempts=2, delay=0.0)


class TestVideoJob:
    def test_from_dict_roundtrip(self):
        job = VideoJob(job_id="test_123", story={"title": "Test"})
        from dataclasses import asdict
        job2 = VideoJob.from_dict(asdict(job))
        assert job2.job_id == job.job_id
        assert job2.story == job.story

    def test_fail_sets_status(self):
        job = VideoJob(job_id="x", story={})
        job.fail("something went wrong")
        assert job.status == "failed"
        assert "something went wrong" in job.errors

    def test_touch_updates_status(self):
        job = VideoJob(job_id="x", story={})
        job.touch("scripting")
        assert job.status == "scripting"

    def test_from_dict_ignores_unknown_fields(self):
        data = {"job_id": "abc", "story": {}, "unknown_future_field": True}
        job = VideoJob.from_dict(data)
        assert job.job_id == "abc"
