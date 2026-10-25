"""Tests for the LLM fallback chain in config/llm_config.hocon."""

from pathlib import Path

import pytest
from pyhocon import ConfigFactory

from neuro_san.internals.run_context.langchain.llms.default_llm_factory import DefaultLlmFactory

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "llm_config.hocon"
KEY_VARIABLES = ("OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "MISTRAL_API_KEY")
MISTRAL_CLASS = "langchain_mistralai.chat_models.ChatMistralAI"


@pytest.fixture(name="llm_config")
def llm_config_fixture():
    return dict(ConfigFactory.parse_file(str(CONFIG_PATH))["llm_config"])


@pytest.fixture(name="factory")
def factory_fixture():
    factory = DefaultLlmFactory()
    factory.load()
    return factory


def build_chain(factory, llm_config, monkeypatch, **env):
    """Build the model chain with fake API keys (no network) and return the models in call order."""
    for name in KEY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    model = factory.create_llm_with_fallbacks(llm_config, {}).get_model()
    return [model.runnable, *model.fallbacks] if hasattr(model, "fallbacks") else [model]


def names(chain):
    return [type(model).__name__ for model in chain]


def test_providers_are_listed_in_the_intended_order(llm_config):
    classes = [entry["class"] for entry in llm_config["fallbacks"]]
    assert classes == ["gemini"] * 4 + [MISTRAL_CLASS, "openai"]


def test_every_gemini_entry_uses_a_different_model_so_each_has_its_own_free_quota(llm_config):
    gemini_models = [entry["model_name"] for entry in llm_config["fallbacks"] if entry["class"] == "gemini"]
    assert len(gemini_models) == len(set(gemini_models)) >= 2


def test_only_mistral_keeps_retries(llm_config):
    for entry in llm_config["fallbacks"]:
        if entry["class"] == MISTRAL_CLASS:
            assert "max_retries" not in entry, "Mistral rides out short rate limits with its retries"
        else:
            assert entry["max_retries"] == 0, f"{entry['model_name']} must hand over immediately"


def test_empty_openai_account_is_not_the_first_thing_tried(llm_config):
    assert llm_config["fallbacks"][0]["class"] != "openai"


def test_all_keys_give_the_full_chain_in_order(factory, llm_config, monkeypatch):
    chain = build_chain(
        factory, llm_config, monkeypatch, OPENAI_API_KEY="sk-fake", GEMINI_API_KEY="fake", MISTRAL_API_KEY="fake"
    )
    assert names(chain) == ["ChatGoogleGenerativeAI"] * 4 + ["ChatMistralAI", "ChatOpenAI"]


def test_providers_without_a_key_are_skipped(factory, llm_config, monkeypatch):
    chain = build_chain(factory, llm_config, monkeypatch, MISTRAL_API_KEY="fake", OPENAI_API_KEY="sk-fake")
    assert names(chain) == ["ChatMistralAI", "ChatOpenAI"]
