"""GenOra Nova — the buyer agent."""

from __future__ import annotations

from genora.agents.nova.workflows import (
    NOVA_CAPABILITIES,
    AddToCartWorkflow,
    BundleWorkflow,
    CompareWorkflow,
    ExternalPricesWorkflow,
    HelpWorkflow,
    ImageSearchWorkflow,
    NegotiateWorkflow,
    OffersWorkflow,
    ProductDetailsWorkflow,
    ProductDiscoveryWorkflow,
    ProductSearchWorkflow,
    RecommendationsWorkflow,
    ReviewsWorkflow,
)
from genora.core.engine import AgentDefinition
from genora.nlu.intents import NOVA_INTENTS, IntentClassifier, LLMIntentClassifier, RuleBasedIntentClassifier
from genora.providers.llm import LLMProvider


def build_nova(llm: LLMProvider | None = None, *, use_llm: bool = True) -> AgentDefinition:
    rules = RuleBasedIntentClassifier(NOVA_INTENTS, default="product_search")
    classifier: IntentClassifier = (
        LLMIntentClassifier(llm, rules, NOVA_INTENTS) if llm is not None and llm.available and use_llm else rules
    )
    return AgentDefinition(
        name="nova",
        display_name="GenOra Nova",
        classifier=classifier,
        workflows=[
            ProductDiscoveryWorkflow(), ProductSearchWorkflow(), CompareWorkflow(), ImageSearchWorkflow(),
            BundleWorkflow(), OffersWorkflow(), NegotiateWorkflow(), ReviewsWorkflow(), ExternalPricesWorkflow(),
            AddToCartWorkflow(), ProductDetailsWorkflow(), RecommendationsWorkflow(), HelpWorkflow(),
        ],
        fallback_intent="help",
        capabilities=NOVA_CAPABILITIES,
        intents=[s.name for s in NOVA_INTENTS],
    )
