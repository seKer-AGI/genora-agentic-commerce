"""GenOra Astra — the seller agent."""

from __future__ import annotations

from genora.agents.astra.workflows import (
    ASTRA_CAPABILITIES,
    AstraHelpWorkflow,
    CreateListingWorkflow,
    CreateOfferWorkflow,
    DiscountStrategyWorkflow,
    ForecastWorkflow,
    LowInventoryWorkflow,
    ProductPerformanceWorkflow,
    SalesPerformanceWorkflow,
    UpdatePriceWorkflow,
    UpdateStockWorkflow,
)
from genora.core.engine import AgentDefinition
from genora.nlu.intents import ASTRA_INTENTS, IntentClassifier, LLMIntentClassifier, RuleBasedIntentClassifier
from genora.providers.llm import LLMProvider


def build_astra(llm: LLMProvider | None = None, *, use_llm: bool = True) -> AgentDefinition:
    rules = RuleBasedIntentClassifier(ASTRA_INTENTS, default="help")
    classifier: IntentClassifier = (
        LLMIntentClassifier(llm, rules, ASTRA_INTENTS) if llm is not None and llm.available and use_llm else rules
    )
    return AgentDefinition(
        name="astra",
        display_name="GenOra Astra",
        classifier=classifier,
        workflows=[
            CreateListingWorkflow(), LowInventoryWorkflow(), SalesPerformanceWorkflow(), ProductPerformanceWorkflow(),
            DiscountStrategyWorkflow(), UpdatePriceWorkflow(), UpdateStockWorkflow(), CreateOfferWorkflow(),
            ForecastWorkflow(), AstraHelpWorkflow(),
        ],
        fallback_intent="help",
        capabilities=ASTRA_CAPABILITIES,
        intents=[s.name for s in ASTRA_INTENTS],
    )
