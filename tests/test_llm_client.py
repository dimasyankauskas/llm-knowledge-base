"""Tests for LLM client module."""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


class TestCompletionWithRetry:
    """Test retry logic and backoff behavior."""

    def test_retry_on_rate_limit(self):
        """Should retry on 429 and eventually succeed."""
        from llm_client import completion_with_retry

        attempt_count = 0

        def fake_completion(prompt, system_prompt=None, model=None,
                           temperature=None, max_tokens=None, timeout=None):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                # Simulate 429 error with status_code attribute
                exc = Exception()
                exc.status_code = 429
                raise exc
            return "Success!"

        with patch("llm_client.completion", side_effect=fake_completion):
            result = completion_with_retry(prompt="test")
            assert result == "Success!"
            assert attempt_count == 3

    def test_no_retry_on_auth_error(self):
        """Should not retry on 401."""
        from llm_client import completion_with_retry

        def fake_completion(prompt, **kwargs):
            exc = Exception()
            exc.status_code = 401
            raise exc

        with patch("llm_client.completion", side_effect=fake_completion):
            with pytest.raises(Exception):
                completion_with_retry(prompt="test")

    def test_no_retry_on_bad_request(self):
        """Should not retry on 400."""
        from llm_client import completion_with_retry

        def fake_completion(prompt, **kwargs):
            exc = Exception()
            exc.status_code = 400
            raise exc

        with patch("llm_client.completion", side_effect=fake_completion):
            with pytest.raises(Exception):
                completion_with_retry(prompt="test")

    def test_max_retries_respected(self):
        """Should stop after max_retries attempts."""
        from llm_client import completion_with_retry

        attempt_count = 0

        def fake_completion(prompt, **kwargs):
            nonlocal attempt_count
            attempt_count += 1
            exc = Exception()
            exc.status_code = 500
            raise exc

        with patch("llm_client.completion", side_effect=fake_completion):
            with pytest.raises(Exception):
                completion_with_retry(prompt="test", max_retries=3)
            assert attempt_count == 4  # initial + 3 retries


class TestCountTokens:
    """Test token counting."""

    def test_count_tokens_fallback(self):
        """Should use heuristic when SDK unavailable."""
        from llm_client import count_tokens

        text = "Hello world this is a test string"
        result = count_tokens(text)
        # Fallback heuristic: len/4
        assert result == len(text) // 4