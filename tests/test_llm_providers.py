import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from llm import _ask_openai, ask_llm


def test_unsupported_provider():
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        ask_llm("Hello", provider="unknown")


def test_gemini_provider_routing():
    with patch("llm._ask_gemini", return_value="Gemini response") as mock:
        result = ask_llm("Hello", provider="gemini", model="gemini-test")
    mock.assert_called_once_with("Hello", "gemini-test")
    assert result == "Gemini response"


def test_openai_provider_routing():
    with patch("llm._ask_openai", return_value="OpenAI response") as mock:
        result = ask_llm("Hello", provider="openai", model="openai-test")
    mock.assert_called_once_with("Hello", "openai-test")
    assert result == "OpenAI response"


def test_openai_missing_key():
    with patch("llm.OPENAI_API_KEY", None):
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            _ask_openai("Hello")


def test_openai_response_is_returned():
    class FakeResponse:
        output_text = "  Hello from OpenAI.  "

    class FakeResponses:
        def create(self, **kwargs):
            assert kwargs["model"] == "test-model"
            assert kwargs["input"] == "Hello"
            return FakeResponse()

    class FakeClient:
        def __init__(self, api_key):
            assert api_key == "test-key"
            self.responses = FakeResponses()

    with patch("llm.OPENAI_API_KEY", "test-key"), patch("llm.OpenAI", FakeClient):
        result = _ask_openai("Hello", model="test-model")

    assert result == "Hello from OpenAI."


def test_openai_empty_response():
    class FakeResponse:
        output_text = ""

    class FakeResponses:
        def create(self, **kwargs):
            return FakeResponse()

    class FakeClient:
        def __init__(self, api_key):
            self.responses = FakeResponses()

    with patch("llm.OPENAI_API_KEY", "test-key"), patch("llm.OpenAI", FakeClient):
        with pytest.raises(RuntimeError, match="empty response"):
            _ask_openai("Hello")
