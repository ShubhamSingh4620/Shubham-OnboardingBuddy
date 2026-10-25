"""Tests for the advice shown by scripts/check_providers.py (messages copied from real provider errors)."""

import pytest

from scripts.check_providers import explain
from scripts.check_providers import label

OPENAI_NO_CREDITS = (
    "Error code: 429 - {'error': {'message': 'You have no credits remaining.', 'type': 'insufficient_quota', "
    "'param': None, 'code': 'credit_balance_exhausted'}}"
)
GEMINI_QUOTA = (
    "429 RESOURCE_EXHAUSTED. You exceeded your current quota. Quota exceeded for metric: "
    "generate_content_free_tier_requests, limit: 20, model: gemini-3-flash"
)
GEMINI_WRONG_MODEL = "404 NOT_FOUND. models/gemini-3-flash is not found for API version v1beta"
MISTRAL_RATE_LIMIT = 'Error response 429 while fetching https://api.mistral.ai: {"message":"Rate limit exceeded"}'


@pytest.mark.parametrize(
    "error, expected",
    [
        (OPENAI_NO_CREDITS, "credits"),
        (GEMINI_QUOTA, "Free-tier quota"),
        (GEMINI_WRONG_MODEL, "cannot use that model"),
        (MISTRAL_RATE_LIMIT, "throttled"),
        ("Cannot connect to host generativelanguage.googleapis.com", "Network problem"),
        ("401 Unauthorized", "rejected"),
    ],
)
def test_known_errors_get_specific_advice(error, expected):
    assert expected in explain(error)


def test_unknown_errors_still_get_a_message():
    assert "Unrecognised" in explain("something nobody has seen before")


def test_label_shows_provider_and_model():
    assert label({"class": "gemini", "model_name": "gemini-2.5-flash"}) == "gemini / gemini-2.5-flash"
    assert label({"class": "langchain_mistralai.chat_models.ChatMistralAI", "model_name": "m"}) == "ChatMistralAI / m"
