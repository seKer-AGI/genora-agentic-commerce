"""Astra tool definitions. Every tool is scoped to the calling seller via the server-side ToolContext."""

from __future__ import annotations

from genora.contracts.seller import (
    CreateOfferInput,
    CreateProductInput,
    DiscountStrategyInput,
    DiscountStrategyOutput,
    DraftListingInput,
    ForecastInput,
    ForecastOutput,
    InventoryInput,
    InventoryOutput,
    ListingDraftOutput,
    OfferCreatedOutput,
    PeriodInput,
    ProductChangeOutput,
    ProductPerformanceInput,
    ProductPerformanceOutput,
    ResolveSellerProductInput,
    ResolveSellerProductOutput,
    SalesSummaryOutput,
    UpdatePriceInput,
    UpdateStockInput,
)
from genora.core.tools import SideEffect, Tool

ASTRA = "astra"


class SellerInventoryTool(Tool[InventoryInput, InventoryOutput]):
    name = "seller_inventory"
    description = "List the seller's inventory, optionally only products at or below their low-stock threshold."
    input_model = InventoryInput
    output_model = InventoryOutput
    agents = frozenset({ASTRA})
    required_permissions = frozenset({"inventory:manage_own"})


class SellerSalesSummaryTool(Tool[PeriodInput, SalesSummaryOutput]):
    name = "seller_sales_summary"
    description = "Revenue, orders, units, AOV, conversion and top/low products for the seller over a period."
    input_model = PeriodInput
    output_model = SalesSummaryOutput
    agents = frozenset({ASTRA})
    required_permissions = frozenset({"analytics:read_own"})


class SellerProductPerformanceTool(Tool[ProductPerformanceInput, ProductPerformanceOutput]):
    name = "seller_product_performance"
    description = "Rank the seller's products by revenue (best or worst) with views and conversion."
    input_model = ProductPerformanceInput
    output_model = ProductPerformanceOutput
    agents = frozenset({ASTRA})
    required_permissions = frozenset({"analytics:read_own"})


class ResolveSellerProductTool(Tool[ResolveSellerProductInput, ResolveSellerProductOutput]):
    name = "resolve_seller_product"
    description = "Find one of the seller's own products by name or SKU."
    input_model = ResolveSellerProductInput
    output_model = ResolveSellerProductOutput
    agents = frozenset({ASTRA})
    required_permissions = frozenset({"products:manage_own"})


class DraftListingTool(Tool[DraftListingInput, ListingDraftOutput]):
    name = "draft_listing"
    description = "Generate a product listing draft (title, description, SEO text, tags, category). Does not publish."
    input_model = DraftListingInput
    output_model = ListingDraftOutput
    agents = frozenset({ASTRA})
    required_permissions = frozenset({"products:manage_own"})


class CreateProductTool(Tool[CreateProductInput, ProductChangeOutput]):
    name = "create_product"
    description = "Create a product in the seller's catalog."
    input_model = CreateProductInput
    output_model = ProductChangeOutput
    agents = frozenset({ASTRA})
    required_permissions = frozenset({"products:manage_own"})
    side_effect = SideEffect.WRITE
    requires_confirmation = True


class UpdatePriceTool(Tool[UpdatePriceInput, ProductChangeOutput]):
    name = "update_product_price"
    description = "Change the list price and/or sale price of one of the seller's products."
    input_model = UpdatePriceInput
    output_model = ProductChangeOutput
    agents = frozenset({ASTRA})
    required_permissions = frozenset({"products:manage_own"})
    side_effect = SideEffect.WRITE
    requires_confirmation = True


class UpdateStockTool(Tool[UpdateStockInput, ProductChangeOutput]):
    name = "update_stock"
    description = "Set the on-hand stock quantity of one of the seller's products."
    input_model = UpdateStockInput
    output_model = ProductChangeOutput
    agents = frozenset({ASTRA})
    required_permissions = frozenset({"inventory:manage_own"})
    side_effect = SideEffect.WRITE
    requires_confirmation = True


class CreateOfferTool(Tool[CreateOfferInput, OfferCreatedOutput]):
    name = "create_offer"
    description = "Create a time-limited percentage offer on one of the seller's products."
    input_model = CreateOfferInput
    output_model = OfferCreatedOutput
    agents = frozenset({ASTRA})
    required_permissions = frozenset({"offers:manage_own"})
    side_effect = SideEffect.WRITE
    requires_confirmation = True


class DiscountStrategyTool(Tool[DiscountStrategyInput, DiscountStrategyOutput]):
    name = "discount_strategy"
    description = "Data-driven discount/pricing suggestions for the seller's products (no changes are made)."
    input_model = DiscountStrategyInput
    output_model = DiscountStrategyOutput
    agents = frozenset({ASTRA})
    required_permissions = frozenset({"analytics:read_own"})


class ForecastTool(Tool[ForecastInput, ForecastOutput]):
    name = "run_forecast"
    description = "Forecast the seller's revenue, order volume or product demand from historical data."
    input_model = ForecastInput
    output_model = ForecastOutput
    agents = frozenset({ASTRA})
    required_permissions = frozenset({"forecasting:run_own"})
