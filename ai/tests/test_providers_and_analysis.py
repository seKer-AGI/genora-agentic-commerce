"""Unit tests for AI providers and review analysis (no network, no database)."""

from __future__ import annotations

import json

import httpx
import pytest

from genora.analysis.reviews import ReviewInput, analyze_reviews
from genora.errors import ProviderUnavailableError
from genora.providers.embeddings import HashingEmbeddingProvider, OpenAICompatibleEmbeddingProvider, cosine
from genora.providers.llm import NullLLMProvider, OpenAICompatibleLLMProvider
from genora.providers.vision import UnavailableVisionProvider


def test_hashing_embeddings_are_deterministic_normalised_and_lexically_meaningful():
    p = HashingEmbeddingProvider(384)
    a, b, c = p.embed(["noise cancelling headphones", "wireless earbuds with noise cancelling", "espresso machine"])
    assert len(a) == 384 and abs(sum(x * x for x in a) - 1) < 1e-6
    assert p.embed_one("noise cancelling headphones") == a
    assert cosine(a, b) > cosine(a, c)
    assert p.describe()["neural"] is False


def test_synonyms_bridge_vocabulary():
    p = HashingEmbeddingProvider(384)
    shoe, sneaker, kettle = p.embed(["running shoes", "sneakers for jogging", "gooseneck kettle"])
    assert cosine(shoe, sneaker) > cosine(shoe, kettle)


def test_null_llm_and_vision_fail_loudly():
    assert NullLLMProvider().available is False
    with pytest.raises(ProviderUnavailableError):
        NullLLMProvider().complete([{"role": "user", "content": "hi"}])
    with pytest.raises(ProviderUnavailableError):
        UnavailableVisionProvider().analyze_product_image(b"x", "image/png")


def test_openai_compatible_llm_parses_tool_calls_and_usage():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "test-model" and request.headers["Authorization"] == "Bearer k"
        return httpx.Response(200, json={
            "model": "test-model",
            "choices": [{"message": {"content": None, "tool_calls": [
                {"id": "c1", "function": {"name": "search_products", "arguments": "{\"query\": \"tent\"}"}}]}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3},
        })

    llm = OpenAICompatibleLLMProvider("k", "https://llm.test/v1", "test-model", transport=httpx.MockTransport(handler))
    resp = llm.complete([{"role": "user", "content": "find a tent"}], tools=[{"name": "search_products"}])
    assert resp.tool_calls[0].name == "search_products" and resp.tool_calls[0].arguments == {"query": "tent"}
    assert resp.prompt_tokens == 12


def test_openai_compatible_llm_errors_become_provider_unavailable():
    llm = OpenAICompatibleLLMProvider("k", "https://llm.test/v1", "m",
                                      transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(ProviderUnavailableError):
        llm.complete([{"role": "user", "content": "x"}])


def test_openai_compatible_embeddings_request_dimensions():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["dimensions"] == 4
        return httpx.Response(200, json={"data": [{"index": 1, "embedding": [0, 1, 0, 0]},
                                                  {"index": 0, "embedding": [1, 0, 0, 0]}]})

    p = OpenAICompatibleEmbeddingProvider("k", "https://e.test/v1", "m", 4, transport=httpx.MockTransport(handler))
    assert p.embed(["a", "b"]) == [[1, 0, 0, 0], [0, 1, 0, 0]]


def test_review_analysis_is_extractive():
    reviews = [
        ReviewInput(5, "Love it", "Battery life is excellent and build quality feels premium."),
        ReviewInput(2, "Meh", "Disappointed: battery drains faster than advertised and fan noise is noticeable."),
        ReviewInput(4, "Good", "Great value for the price. Only complaint: the charger is bulky."),
    ]
    ins = analyze_reviews(reviews)
    assert ins.review_count == 3 and ins.average_rating == 3.67
    battery = next(t for t in ins.themes if t.name == "Battery life")
    assert battery.positive >= 1 and battery.negative >= 1
    corpus = " ".join(r.body for r in reviews)
    for t in ins.themes:
        for s in t.snippets_positive + t.snippets_negative:
            assert s in corpus
    assert "3 reviews" in ins.summary


def test_review_analysis_empty():
    assert analyze_reviews([]).summary.startswith("There are no published reviews")
