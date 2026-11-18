import sys
from pathlib import Path
from unittest.mock import patch
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from intent import QueryIntent, understand_question, parse_question_rules


def test_query_intent_model():
    intent = QueryIntent(intent="ranking", metric="revenue", dimension="city", time_period="last quarter", sort_order="descending", limit=1)
    assert intent.intent == "ranking" and intent.metric == "revenue" and intent.limit == 1


def test_common_question_is_parsed_without_api_key():
    with patch("intent.GEMINI_API_KEY", None):
        intent = understand_question("Which city generated the highest revenue?")
    assert intent.intent == "ranking" and intent.dimension == "city" and intent.limit == 1


def test_top_four_cities_is_parsed():
    intent = parse_question_rules("What are the top 4 cities with highest revenue?")
    assert intent.intent == "ranking" and intent.metric == "revenue" and intent.dimension == "city" and intent.limit == 4


def test_row_lookup_is_parsed():
    intent = parse_question_rules("Show me 10 rows of the dataset")
    assert intent.intent == "lookup" and intent.metric is None and intent.limit == 10


def test_llm_fallback_uses_structured_output():
    class Response: text = '{"intent":"ranking","metric":"revenue","dimension":"city","filters":[],"time_period":null,"sort_order":"descending","limit":1}'
    class Models:
        def generate_content(self, **kwargs):
            assert kwargs["config"]["response_schema"] is QueryIntent
            return Response()
    class Client:
        def __init__(self, api_key): self.models = Models()
    with patch("intent.GEMINI_API_KEY", "test-key"), patch("intent.genai.Client", Client):
        result = understand_question("An unfamiliar analytical phrase", force_llm=True)
    assert result.intent == "ranking"
