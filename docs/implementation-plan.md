# GenOra Marketplace — Implementation Plan

## 1. Repository inspection (Phase 1 findings)

| Item | Finding |
|---|---|
| Existing code | None — the repository was empty. Greenfield build; nothing to preserve. |
| Toolchain | Python 3.13, Node 22, npm 10, uv, Docker 29 + Compose v5, Git. |
| Database | A host PostgreSQL 18 exists on :5432 (credentials unknown, no pgvector). We run our own `pgvector/pgvector:pg16` container on **:5433** to avoid conflicts. |
| AI providers | **No LLM API key and no local LLM server are available.** GenOra must therefore work end-to-end in a deterministic *rule-based* mode, with the OpenAI-compatible LLM path as a configurable enhancement (tested with a mocked HTTP transport). |
| Machine | 4 cores, low free RAM → avoid running many heavy processes concurrently. |

## 2. Architecture decisions

| Decision | Choice | Rationale |
|---|---|---|
| Monorepo | `frontend/`, `backend/`, `ai/`, `database/`, `infrastructure/`, `docs/`, `tests/` | Mandated layout, clear ownership. |
| Backend | FastAPI + SQLAlchemy 2 (sync, psycopg 3) + Alembic + Pydantic v2 | Sync SQLAlchemy in FastAPI's threadpool is simple, robust and production-proven; row locking (`SELECT … FOR UPDATE`) for stock. |
| AI package | `ai/genora` — standalone Python package (no FastAPI/SQLAlchemy imports) | Keeps AI logic separate from business logic. The backend *implements* tool contracts; the AI layer only knows tool names + schemas. |
| Agent graph | LangGraph `StateGraph`: `guard → detect_intent → route → execute_workflow → validate → respond` | Real LangGraph usage, deterministic nodes, easy to extend. |
| NLU | Pluggable `IntentClassifier`: `RuleBasedIntentClassifier` (default) and `LLMIntentClassifier` (structured JSON output, falls back to rules on failure) | Works with no API key; improves when a model is configured. |
| Response generation | Template renderer grounded on tool results (default); optional LLM phrasing with **grounding validation** (prices/products in text must appear in tool results, else template fallback) | Prevents hallucinated prices/products. |
| Embeddings | `EmbeddingProvider`: `hashing` (lexical, non-neural, zero-dependency), `fastembed` (local neural BGE-small, 384-d, if installed), `openai` (OpenAI-compatible) | Real vector search in every environment, honestly labelled. |
| Vector store | `VectorStore` interface → `PgVectorStore` | Another vector DB can be dropped in later. |
| Search | Postgres full-text (`tsvector` + GIN) + trigram + pgvector, fused with Reciprocal Rank Fusion | Hybrid search with graceful degradation. |
| Auth | Argon2 password hashing, JWT access tokens (15 min), opaque rotating refresh tokens stored **hashed** in DB, httpOnly cookie | Revocable sessions, logout, reuse detection. |
| RBAC | `roles`, `permissions`, `role_permissions`, `user_roles`; `require_roles` / `require_permission` dependencies | Admin can manage permissions. |
| Orders | Checkout splits a cart into **one order per seller** (shared `checkout_group_id`) | Sellers own their order lifecycle cleanly. |
| Pricing | Server-side `PricingEngine`: base/sale price → best active offer → bundle discount → negotiated price → coupon → tax → shipping | Frontend never supplies prices. |
| Payments | `PaymentProvider` interface → `SandboxPaymentProvider` (dev/test, clearly labelled), `StripePaymentProvider` (HTTP, requires key) | No provider hard-coded in business logic. |
| Storage | `StorageProvider` → `LocalStorageProvider` (S3 extension point) | Product images/uploads. |
| Forecasting | `ForecastingProvider` → `BaselineForecastProvider` (Holt-Winters additive, numpy), `TimesFMForecastProvider` (only if `timesfm` is installed — otherwise reports *unavailable*) | Never fabricates forecasts. |
| External prices | `ExternalMarketplaceProvider` → `StaticFeedProvider` (licensed JSON feed), `MockMarketplaceProviderA/B` (tests only, labelled *mock*) | No scraping, no fabricated prices in production. |
| Frontend | Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + TanStack Query + Recharts; `/api/v1/*` proxied to FastAPI (same-origin cookies) | Modern, responsive, typed. |
| Images | Generated SVG product art stored via the storage provider (no hard-coded data in the frontend) | Works offline, deterministic. |

## 3. GenOra tool & safety model

- Every tool declares: `name`, `description`, `input_schema`, `output_schema`, `allowed_roles`, `side_effect` (`read` / `write` / `destructive`), `requires_confirmation`.
- `ToolExecutor` enforces: agent allow-list (Nova ≠ Astra tools), role checks, Pydantic input validation, timeouts, structured errors, and records every call in `agent_tool_calls` (with redacted inputs).
- Principal (user id, roles, seller id) is injected server-side into `ToolContext`; tools **never** accept identity/ownership from model or user input.
- Write/destructive actions create a **pending action** in the session; they run only after explicit confirmation (`POST /agents/sessions/{id}/confirm`).
- Prompt-injection guard flags known patterns; retrieved content (reviews, descriptions) is wrapped as data and never interpreted as instructions.

## 4. Phases

| # | Phase | Key deliverables |
|---|---|---|
| 1 | Inspection & plan | This document, `docs/progress.md` |
| 2 | Database | SQLAlchemy models, Alembic migration, pgvector/pg_trgm, seed script |
| 3 | Backend foundation | Config, logging, errors, auth, RBAC, repositories/services |
| 4 | Marketplace APIs | products, categories, search, cart, orders, reviews, offers, bundles, sellers, admin (+tests) |
| 5 | Frontend marketplace | Home, search, products, details, cart, checkout, auth, buyer dashboard |
| 6 | Seller dashboard | Products CRUD, inventory, orders, analytics, offers, Astra |
| 7 | Admin dashboard | Users, sellers, products, orders, categories, reviews, offers, analytics, agent monitoring, settings |
| 8 | GenOra core | Sessions, memory, intent routing, LangGraph engine, tool registry/executor, safety |
| 9 | Nova | Discovery, search, comparison, image search, bundles, offers, negotiation, reviews, external prices, context |
| 10 | Astra | Listing assistant, inventory, sales analytics, performance, offer strategy |
| 11 | Analytics & forecasting | Event tracking, metrics, forecasting providers + persistence |
| 12 | Recommendations | Popular, similar, category, behavioural (co-purchase), semantic |
| 13 | Security hardening | Authz/escalation/token/injection/leakage tests |
| 14 | Testing | Full backend + AI + frontend test runs |
| 15 | Docker | Dockerfiles, compose, fresh-setup verification |
| 16 | Final review | Links, API calls, env vars, docs |

## 5. Dependencies

- Backend: fastapi, uvicorn, sqlalchemy, psycopg[binary], alembic, pydantic-settings, pyjwt, argon2-cffi, httpx, pgvector, numpy, structlog-style JSON logging (stdlib), python-multipart, langgraph.
- Optional: fastembed (local neural embeddings), timesfm (forecasting), stripe key.
- Frontend: next, react, tailwindcss, shadcn/ui (radix), @tanstack/react-query, recharts, react-hook-form, zod, sonner, lucide-react, vitest + testing-library.

## 6. Risks & mitigations

| Risk | Mitigation |
|---|---|
| No LLM available locally | Rule-based NLU + template responses are first-class; LLM path tested with mocked transport; UI shows the active mode. |
| Vision model unavailable | Image search returns a clear *unavailable* result; tested with a fake vision provider. |
| TimesFM heavy / not installable | Provider reports unavailable; baseline model is real and tested. |
| Low RAM | Run services sequentially during verification; production builds only when needed. |
| Scope size | Strict modularity; tests alongside each phase; progress tracked in `docs/progress.md`. |
