import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "backend"),
)

from conversation import (
    Conversation,
    Message,
    RewrittenQuestion,
    rewrite_follow_up,
)


def test_conversation_stores_messages():
    conversation = Conversation()

    conversation.add_user_message("What was revenue in Delhi?")
    conversation.add_assistant_message("Delhi had the highest revenue.")

    history = conversation.get_history()

    assert len(history) == 2
    assert history[0] == Message(
        role="user",
        content="What was revenue in Delhi?",
    )
    assert history[1].role == "assistant"


def test_conversation_clear():
    conversation = Conversation()

    conversation.add_user_message("Hello")
    conversation.clear()

    assert conversation.get_history() == []


def test_rewritten_question_model():
    result = RewrittenQuestion(
        rewritten_question="What was revenue in Mumbai?"
    )

    assert result.rewritten_question == "What was revenue in Mumbai?"


def test_missing_api_key():
    conversation = [
        Message(role="user", content="What was revenue in Delhi?")
    ]

    with patch("conversation.GEMINI_API_KEY", None):
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            rewrite_follow_up("What about Mumbai?", conversation)


def test_rewrite_follow_up_uses_history():
    class FakeResponse:
        text = '{"rewritten_question":"What was revenue in Mumbai last quarter?"}'

    class FakeModels:
        def generate_content(self, **kwargs):
            assert kwargs["model"] == "test-model"
            assert "What was revenue in Delhi last quarter?" in kwargs["contents"]
            assert "What about Mumbai?" in kwargs["contents"]
            assert kwargs["config"]["response_mime_type"] == "application/json"
            assert kwargs["config"]["response_schema"] is RewrittenQuestion
            return FakeResponse()

    class FakeClient:
        def __init__(self, api_key):
            assert api_key == "test-key"
            self.models = FakeModels()

    history = [
        Message(
            role="user",
            content="What was revenue in Delhi last quarter?",
        ),
        Message(
            role="assistant",
            content="Delhi generated revenue of ₹190,000 last quarter.",
        ),
    ]

    with patch("conversation.GEMINI_API_KEY", "test-key"),          patch("conversation.GEMINI_MODEL", "test-model"),          patch("conversation.genai.Client", FakeClient):

        result = rewrite_follow_up(
            "What about Mumbai?",
            history,
        )

    assert result.rewritten_question == (
        "What was revenue in Mumbai last quarter?"
    )
