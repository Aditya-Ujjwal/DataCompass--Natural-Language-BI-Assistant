import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from llm import _ask_gemini


def test_missing_api_key():
    with patch("llm.GEMINI_API_KEY", None):
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            _ask_gemini("Hello")


def test_llm_returns_text():
    class FakeResponse:
        text = "  Hello from Gemini.  "

    class FakeChat:
        def send_message(self, prompt):
            assert prompt == "Hello"
            return FakeResponse()

    class FakeChats:
        def create(self, model):
            assert model == "test-model"
            return FakeChat()

    class FakeClient:
        def __init__(self, api_key):
            assert api_key == "test-key"
            self.chats = FakeChats()

    with patch("llm.GEMINI_API_KEY", "test-key"), patch("llm.genai.Client", FakeClient):
        result = _ask_gemini("Hello", model="test-model")

    assert result == "Hello from Gemini."


def test_empty_llm_response():
    class FakeResponse:
        text = ""

    class FakeChat:
        def send_message(self, prompt):
            return FakeResponse()

    class FakeChats:
        def create(self, model):
            return FakeChat()

    class FakeClient:
        def __init__(self, api_key):
            self.chats = FakeChats()

    with patch("llm.GEMINI_API_KEY", "test-key"), patch("llm.genai.Client", FakeClient):
        with pytest.raises(RuntimeError, match="empty response"):
            _ask_gemini("Hello")
