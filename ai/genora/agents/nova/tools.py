"""Nova tool definitions (metadata + contracts). The host application subclasses these and implements `run`."""

from __future__ import annotations

from genora.contracts.commerce import (
    AcceptCounterInput,
    AccessoriesInput,
    AccessoriesOutput,
    AddBundleToCartInput,
    AddToCartInput,
    AnalyzeImageInput,
    CartSummaryOutput,
    ExternalPricesOutput,
    ImageAnalysisOutput,
    NegotiationPolicyOutput,
    NegotiationResultOutput,
    ProductBundlesOutput,
    ProductDetailsOutput,
    ProductIdInput,
    ProductListOutput,
    ProductOffersOutput,
    RecommendationsInput,
    ResolveProductInput,
    ResolveProductOutput,
    ReviewInsightsOutput,
    SearchProductsInput,
    SubmitNegotiationInput,
)
from genora.core.tools import SideEffect, Tool

NOVA = "nova"
ASTRA = "astra"
PERM_NOVA = "agents:nova"
PERM_CART = "cart:manage"
PERM_NEGOTIATE = "negotiations:create"


class SearchProductsTool(Tool[SearchProductsInput, ProductListOutput]):
    name = "search_products"
    description = "Search the marketplace catalog with keyword/semantic search, filters and sorting."
    input_model = SearchProductsInput
    output_model = ProductListOutput
    agents = frozenset({NOVA})
    required_permissions = frozenset({PERM_NOVA})


class ResolveProductTool(Tool[ResolveProductInput, ResolveProductOutput]):
    name = "resolve_product"
    description = "Find catalog products matching a product name or description the user referred to."
    input_model = ResolveProductInput
    output_model = ResolveProductOutput
    agents = frozenset({NOVA})
    required_permissions = frozenset({PERM_NOVA})


class ProductDetailsTool(Tool[ProductIdInput, ProductDetailsOutput]):
    name = "get_product_details"
    description = "Get full catalog details (description, attributes, variants) for a product."
    input_model = ProductIdInput
    output_model = ProductDetailsOutput
    agents = frozenset({NOVA})
    required_permissions = frozenset({PERM_NOVA})


class ProductOffersTool(Tool[ProductIdInput, ProductOffersOutput]):
    name = "get_product_offers"
    description = "List currently active offers that apply to a product, with conditions."
    input_model = ProductIdInput
    output_model = ProductOffersOutput
    agents = frozenset({NOVA})
    required_permissions = frozenset({PERM_NOVA})


class ProductBundlesTool(Tool[ProductIdInput, ProductBundlesOutput]):
    name = "get_product_bundles"
    description = "List active bundles that contain a product."
    input_model = ProductIdInput
    output_model = ProductBundlesOutput
    agents = frozenset({NOVA})
    required_permissions = frozenset({PERM_NOVA})


class FindAccessoriesTool(Tool[AccessoriesInput, AccessoriesOutput]):
    name = "find_accessories"
    description = "Find catalog products that complement a product (compatible accessories)."
    input_model = AccessoriesInput
    output_model = AccessoriesOutput
    agents = frozenset({NOVA})
    required_permissions = frozenset({PERM_NOVA})


class ReviewInsightsTool(Tool[ProductIdInput, ReviewInsightsOutput]):
    name = "get_review_insights"
    description = "Summarise published customer reviews of a product (themes, pros, cons)."
    input_model = ProductIdInput
    output_model = ReviewInsightsOutput
    agents = frozenset({NOVA})
    required_permissions = frozenset({PERM_NOVA})


class NegotiationPolicyTool(Tool[ProductIdInput, NegotiationPolicyOutput]):
    name = "check_negotiation_policy"
    description = "Check whether the seller accepts price offers for a product."
    input_model = ProductIdInput
    output_model = NegotiationPolicyOutput
    agents = frozenset({NOVA})
    required_permissions = frozenset({PERM_NEGOTIATE})


class SubmitNegotiationTool(Tool[SubmitNegotiationInput, NegotiationResultOutput]):
    name = "submit_negotiation"
    description = "Submit a price offer to the seller; evaluated by the seller's negotiation rules."
    input_model = SubmitNegotiationInput
    output_model = NegotiationResultOutput
    agents = frozenset({NOVA})
    required_permissions = frozenset({PERM_NEGOTIATE})
    side_effect = SideEffect.WRITE
    requires_confirmation = True


class AcceptCounterOfferTool(Tool[AcceptCounterInput, NegotiationResultOutput]):
    name = "accept_counter_offer"
    description = "Accept a seller's counter-offer for a previous negotiation."
    input_model = AcceptCounterInput
    output_model = NegotiationResultOutput
    agents = frozenset({NOVA})
    required_permissions = frozenset({PERM_NEGOTIATE})
    side_effect = SideEffect.WRITE
    requires_confirmation = True


class ExternalPricesTool(Tool[ProductIdInput, ExternalPricesOutput]):
    name = "get_external_prices"
    description = "Get prices for the same product from configured external marketplace data providers."
    input_model = ProductIdInput
    output_model = ExternalPricesOutput
    agents = frozenset({NOVA})
    required_permissions = frozenset({PERM_NOVA})


class AddToCartTool(Tool[AddToCartInput, CartSummaryOutput]):
    name = "add_to_cart"
    description = "Add a product to the user's cart."
    input_model = AddToCartInput
    output_model = CartSummaryOutput
    agents = frozenset({NOVA})
    required_permissions = frozenset({PERM_CART})
    side_effect = SideEffect.WRITE
    requires_confirmation = True


class AddBundleToCartTool(Tool[AddBundleToCartInput, CartSummaryOutput]):
    name = "add_bundle_to_cart"
    description = "Add every product of a bundle to the user's cart at the bundle price."
    input_model = AddBundleToCartInput
    output_model = CartSummaryOutput
    agents = frozenset({NOVA})
    required_permissions = frozenset({PERM_CART})
    side_effect = SideEffect.WRITE
    requires_confirmation = True


class RecommendationsTool(Tool[RecommendationsInput, ProductListOutput]):
    name = "get_recommendations"
    description = "Personalised, popular or similar-product recommendations."
    input_model = RecommendationsInput
    output_model = ProductListOutput
    agents = frozenset({NOVA})
    required_permissions = frozenset({PERM_NOVA})


class AnalyzeImageTool(Tool[AnalyzeImageInput, ImageAnalysisOutput]):
    name = "analyze_product_image"
    description = "Extract product characteristics from an uploaded image with the configured vision model."
    input_model = AnalyzeImageInput
    output_model = ImageAnalysisOutput
    agents = frozenset({NOVA})
    required_permissions = frozenset({PERM_NOVA})
