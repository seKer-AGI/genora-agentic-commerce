// Types mirroring the GenOra REST API (backend/app/schemas). Money values are JSON numbers with 2 decimals.

export type UUID = string;

export interface ApiErrorBody {
  success: false;
  error: { code: string; message: string; details?: unknown };
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ---------------------------------------------------------------- auth
export interface SellerSummary {
  id: UUID;
  store_name: string;
  slug: string;
  status: string;
}

export interface Me {
  id: UUID;
  email: string;
  full_name: string;
  roles: ("BUYER" | "SELLER" | "ADMIN")[];
  permissions: string[];
  is_email_verified: boolean;
  created_at: string;
  seller: SellerSummary | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: Me;
}

// ---------------------------------------------------------------- catalog
export interface CategoryNode {
  id: UUID;
  parent_id: UUID | null;
  name: string;
  slug: string;
  description: string | null;
  icon: string | null;
  sort_order: number;
  is_active: boolean;
  product_count: number;
  children: CategoryNode[];
}

export interface AppliedOffer {
  id: UUID;
  name: string;
  discount_type: "percentage" | "fixed";
  value: number;
  ends_at: string | null;
  min_quantity: number;
}

export interface ProductCard {
  id: UUID;
  slug: string;
  name: string;
  brand: string | null;
  price: number;
  sale_price: number | null;
  final_price: number;
  currency: string;
  rating_avg: number;
  rating_count: number;
  image_url: string | null;
  in_stock: boolean;
  stock: number;
  sold_count: number;
  seller: { id: UUID; store_name: string; slug: string; rating_avg: number };
  category: { id: UUID; name: string; slug: string } | null;
  offer: AppliedOffer | null;
  tags: string[];
  status: string;
  score: number | null;
}

export interface ProductDetail extends ProductCard {
  sku: string;
  description: string;
  seo_description: string | null;
  attributes: Record<string, unknown>;
  images: { id: UUID; url: string; alt_text: string | null; is_primary: boolean; sort_order: number }[];
  variants: { id: UUID; sku: string; name: string; attributes: Record<string, unknown>; price_override: number | null }[];
  low_stock: boolean;
  rating_distribution: Record<string, number>;
  negotiable: boolean;
  created_at: string;
  updated_at: string;
}

export interface Facet {
  value: string;
  label: string;
  count: number;
}

export interface SearchResponse {
  items: ProductCard[];
  total: number;
  page: number;
  page_size: number;
  query: string | null;
  mode: "keyword" | "semantic" | "hybrid";
  sort: string;
  facets: { brands: Facet[]; categories: Facet[] };
  price_range: { min: number | null; max: number | null };
  engine: Record<string, unknown>;
  latency_ms: number;
}

// ---------------------------------------------------------------- promotions
export interface OfferOut {
  id: UUID;
  name: string;
  description: string | null;
  discount_type: "percentage" | "fixed";
  value: number;
  scope: "product" | "category" | "seller" | "marketplace";
  seller_id: UUID | null;
  seller_name: string | null;
  product_id: UUID | null;
  product_name: string | null;
  category_id: UUID | null;
  min_quantity: number;
  starts_at: string | null;
  ends_at: string | null;
  is_active: boolean;
  status: "active" | "scheduled" | "expired" | "disabled";
  conditions: string[];
}

export interface ProductOffer extends OfferOut {
  eligible: boolean;
  discount_per_unit: number;
  price_after_offer: number;
}

export interface Bundle {
  id: UUID;
  name: string;
  slug: string;
  description: string | null;
  seller_id: UUID | null;
  seller_name: string | null;
  discount_type: string;
  value: number;
  products: ProductCard[];
  items_total: number;
  bundle_price: number;
  savings: number;
  is_active: boolean;
  available: boolean;
  starts_at: string | null;
  ends_at: string | null;
}

export interface Coupon {
  id: UUID;
  code: string;
  description: string | null;
  discount_type: string;
  value: number;
  min_subtotal: number;
  seller_id: UUID | null;
  starts_at: string | null;
  ends_at: string | null;
  usage_limit: number | null;
  per_user_limit: number;
  used_count: number;
  is_active: boolean;
}

export interface Negotiation {
  id: UUID;
  product_id: UUID;
  product_name: string;
  product_slug: string;
  status: "accepted" | "countered" | "rejected" | "expired" | "used";
  list_price: number;
  offered_price: number;
  counter_price: number | null;
  agreed_price: number | null;
  reason: string | null;
  expires_at: string | null;
  created_at: string;
}

// ---------------------------------------------------------------- reviews
export interface Review {
  id: UUID;
  product_id: UUID;
  product_name: string | null;
  author_name: string;
  rating: number;
  title: string | null;
  body: string;
  status: "pending" | "approved" | "rejected";
  is_verified_purchase: boolean;
  helpful_count: number;
  moderation_reason: string | null;
  created_at: string;
  is_mine: boolean;
}

export interface ReviewTheme {
  theme: string;
  mentions: number;
  positive: number;
  negative: number;
  sentiment: "positive" | "negative" | "mixed";
  examples_positive: string[];
  examples_negative: string[];
}

export interface ReviewInsights {
  review_count: number;
  average_rating: number;
  distribution: Record<string, number>;
  verified_share: number;
  themes: ReviewTheme[];
  top_positive: string[];
  top_negative: string[];
  summary: string;
  method: string;
}

export interface ReviewSummary {
  product_id: UUID;
  rating: { average: number; count: number; distribution: Record<string, number> };
  insights: ReviewInsights;
  disclaimer: string;
}

// ---------------------------------------------------------------- commerce
export interface CartLine {
  id: UUID;
  product_id: UUID;
  product_slug: string;
  product_name: string;
  image_url: string | null;
  seller_id: UUID;
  seller_name: string;
  variant_id: UUID | null;
  bundle_id: UUID | null;
  quantity: number;
  unit_price: number;
  list_price: number;
  subtotal: number;
  discounts: { source: string; description: string; amount: number }[];
  total: number;
  available: number;
  issues: string[];
}

export interface Cart {
  id: UUID;
  items: CartLine[];
  sellers: { seller_id: UUID; store_name: string; subtotal: number; discount_total: number; shipping: number; tax: number; total: number }[];
  coupon_code: string | null;
  coupon_message: string | null;
  coupon_discount: number;
  subtotal: number;
  discount_total: number;
  shipping_total: number;
  tax_total: number;
  total: number;
  currency: string;
  item_count: number;
  issues: string[];
}

export interface Address {
  id: UUID;
  label: string | null;
  recipient_name: string;
  line1: string;
  line2: string | null;
  city: string;
  state: string | null;
  postal_code: string;
  country: string;
  phone: string | null;
  is_default: boolean;
}

export type OrderStatus = "pending" | "confirmed" | "processing" | "shipped" | "delivered" | "cancelled" | "refunded";

export interface Order {
  id: UUID;
  order_number: string;
  checkout_group_id: UUID;
  status: OrderStatus;
  currency: string;
  subtotal: number;
  discount_total: number;
  tax_total: number;
  shipping_total: number;
  total: number;
  placed_at: string;
  seller: { id: string; store_name: string | null; slug: string | null };
  buyer: { id: string; full_name: string } | null;
  item_count: number;
  items: {
    id: UUID;
    product_id: UUID;
    product_name: string;
    sku: string;
    unit_price: number;
    quantity: number;
    discount_amount: number;
    line_total: number;
    image_url: string | null;
    product_slug: string | null;
  }[];
  payments: { id: UUID; provider: string; status: string; amount: number; currency: string; failure_reason: string | null; created_at: string }[];
  discounts: { source: string; description: string; amount: number }[];
  status_history: { from_status: string | null; to_status: string; note: string | null; created_at: string }[];
  shipping_address: Record<string, string | null> | null;
  tracking_number: string | null;
  notes: string | null;
  allowed_transitions: string[];
}

export interface CheckoutResponse {
  checkout_group_id: UUID;
  orders: Order[];
  total_charged: number;
  payment_status: string;
}

export interface InventoryRow {
  product_id: UUID;
  product_name: string;
  sku: string;
  status: string;
  quantity_on_hand: number;
  quantity_reserved: number;
  available: number;
  low_stock_threshold: number;
  is_low: boolean;
  sold_count: number;
  image_url: string | null;
}

// ---------------------------------------------------------------- analytics
export interface Kpi {
  value: number;
  previous: number;
  change_pct: number | null;
}

export interface SeriesPoint {
  date: string;
  revenue: number;
  orders: number;
  units: number;
}

export interface ProductPerf {
  product_id: UUID;
  name: string;
  slug: string;
  image_url: string | null;
  revenue: number;
  units: number;
  orders: number;
  views: number;
  conversion_rate: number | null;
  rating_avg: number;
  stock: number | null;
}

export interface SellerOverview {
  period_days: number;
  currency: string;
  revenue: Kpi;
  orders: Kpi;
  units_sold: Kpi;
  average_order_value: Kpi;
  views: Kpi;
  conversion_rate: Kpi;
  series: SeriesPoint[];
  top_products: ProductPerf[];
  low_performers: ProductPerf[];
  status_breakdown: Record<string, number>;
  low_stock_count: number;
  rating_avg: number;
  definitions: Record<string, string>;
}

export interface AdminOverview {
  period_days: number;
  totals: Record<string, number>;
  gmv: Kpi;
  revenue: Kpi;
  orders: Kpi;
  new_users: Kpi;
  series: SeriesPoint[];
  top_products: ProductPerf[];
  top_categories: { slug: string; name: string; revenue: number; units: number }[];
  seller_performance: { seller_id: string; store_name: string; rating_avg: number; revenue: number; orders: number; cancellation_rate: number }[];
  status_breakdown: Record<string, number>;
}

export interface AgentUsage {
  period_days: number;
  totals: { workflows: number; avg_latency_ms: number; prompt_tokens: number; completion_tokens: number; tool_calls: number };
  by_agent: { agent: string; workflows: number; avg_latency_ms: number; success_rate: number }[];
  by_intent: { agent: string; intent: string; count: number }[];
  by_status: Record<string, number>;
  tool_calls: { tool: string; calls: number; errors: number; denied: number; avg_latency_ms: number }[];
  series: { date: string; workflows: number }[];
  runtime: AiRuntime;
}

export interface AiRuntime {
  llm: { provider: string; model: string | null; available: boolean };
  nlu_mode: string;
  embeddings: { provider: string; model: string; dimensions: number; neural: boolean };
  vision: { provider: string; available: boolean };
}

export interface SearchAnalytics {
  period_days: number;
  total_searches: number;
  zero_result_rate: number;
  top_queries: { query: string; count: number; avg_results: number }[];
  zero_result_queries: { query: string; count: number }[];
  by_source: Record<string, number>;
  series: { date: string; searches: number }[];
}

export interface Recommendations {
  strategy: string;
  items: ProductCard[];
  reasons: Record<string, string>;
}

export interface Forecast {
  id: UUID | null;
  target: string;
  entity_id: UUID | null;
  provider: string;
  model_name: string;
  status: "completed" | "failed";
  horizon: number;
  frequency: string;
  interval: number | null;
  history: { date: string; value: number }[];
  points: { date: string; value: number; lower: number | null; upper: number | null }[];
  metrics: Record<string, unknown>;
  params: Record<string, unknown>;
  error: string | null;
  created_at: string | null;
}

// ---------------------------------------------------------------- agents
export type AgentName = "nova" | "astra";

export interface AgentBlock {
  type: string;
  [key: string]: unknown;
}

export interface PendingAction {
  id: string;
  tool: string;
  args: Record<string, unknown>;
  summary: string;
  details: string[];
  workflow: string;
  created_at: string;
  expires_at: string;
}

export interface AgentMessagePayload {
  blocks?: AgentBlock[];
  suggestions?: string[];
  steps?: string[];
  status?: string;
  intent?: string;
  workflow?: string;
  nlu_mode?: string;
  phrased_by?: string;
  safety_flags?: string[];
  pending_action?: PendingAction | null;
  attachments?: { name: string; mime: string; size: number }[];
  action?: { id: string; decision: "approve" | "decline" };
}

export interface AgentMessage {
  id: UUID;
  role: "user" | "assistant" | "system";
  content: string;
  payload: AgentMessagePayload;
  created_at: string;
}

export interface Conversation {
  id: UUID;
  agent: AgentName;
  title: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface AgentMemory {
  slots: Record<string, unknown>;
  focus_product: { id: string; name: string; price: number | null } | null;
  referenced_products: { id: string; name: string; price: number | null }[];
  pending_action: PendingAction | null;
  awaiting: string | null;
}

export interface ConversationDetail extends Conversation {
  messages: AgentMessage[];
  memory: AgentMemory;
}

export interface TurnResponse {
  conversation_id: UUID;
  user_message: AgentMessage;
  message: AgentMessage;
  workflow: {
    id: UUID;
    intent: string;
    name: string;
    status: string;
    confidence: number | null;
    nlu_mode: string;
    steps: string[];
    latency_ms: number | null;
    tool_calls: { tool: string; status: string; latency_ms: number | null }[];
  };
  memory: AgentMemory;
}

export interface AgentStatus {
  agents: {
    agent: string;
    display_name: string;
    status: string;
    enabled: boolean;
    can_use: boolean;
    capabilities?: string[];
    planned_capabilities?: string[];
    label?: string;
    tools?: { name: string; description: string; side_effect: string; requires_confirmation: boolean }[];
  }[];
  runtime: AiRuntime;
}
