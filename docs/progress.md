# Progress

Legend: ✅ done · 🟡 in progress · ⬜ not started · ⛔ blocked (external)

| Phase | Status | Notes |
|---|---|---|
| 1. Inspection & plan | ✅ | Empty repo; see `implementation-plan.md` |
| 2. Database | ✅ | 44 tables, Alembic `0001_initial` (up/down verified, `alembic check` clean), pgvector HNSW + FTS GIN + trigram indexes, synthetic seed (81 products, 12 sellers, 60 buyers, ~800 orders/180 days, ~390 reviews, 9 offers, 4 coupons, 8 bundles, ~12.7k events) |
| 3. Backend foundation | ✅ | Settings, JSON logging w/ redaction, structured errors, Argon2 + JWT + rotating refresh tokens (reuse detection), RBAC with DB-backed permissions, rate limiting, audit log |
| 4. Marketplace APIs | ✅ | 93 REST paths: auth, catalog, hybrid search, cart/pricing engine, checkout (per-seller orders, idempotency, payment compensation), order state machine, reviews + moderation, offers/coupons/bundles, negotiation, sellers, admin, analytics, recommendations, media |
| 8. GenOra core | ✅ | LangGraph engine (guard→intent→route→execute→validate→respond), guarded tool executor (agent allow-list, permissions, confirmation, validation, budget, audit), session memory, rule + LLM intent classifiers, injection guard, grounding validation, SSE progress streaming |
| 9. GenOra Nova | ✅ | Discovery, search, comparison, image search (vision provider or honest unavailable), bundles/accessories, offers, negotiation (confirmed), reviews, external prices (no fabrication), add-to-cart (confirmed), conversational memory |
| 10. GenOra Astra | ✅ | Listing assistant (draft → confirm), inventory, sales analytics, product performance, discount strategy, price/stock/offer changes (confirmed), forecasting |
| 11. Analytics & forecasting | ✅ | Holt-Winters baseline + seasonal-naive benchmark with backtests; TimesFM provider reports unavailable unless installed; results persisted |
| 12. Recommendations | ✅ | popular / similar / also-bought / category / semantic / for-you (built early; needed by product pages) |
| 5. Frontend marketplace | ⬜ | |
| 6. Seller dashboard | ⬜ | |
| 7. Admin dashboard | ⬜ | |
| 13. Security hardening | 🟡 | Token forgery / alg=none / role-claim / IDOR / ownership / upload tests in place |
| 14. Testing | 🟡 | 117 backend + agent + AI tests passing |
| 15. Docker | ⬜ | |
| 16. Final review | ⬜ | |

## Log
- Seed insert of analytics events switched from executemany to chunked multi-row VALUES (2m40s → 30s).
- Fixed: product update mutated state before validating sale price (found by tests).
- Fixed: env list parsing (`NoDecode`) for `CORS_ORIGINS` / `EXTERNAL_PRICE_PROVIDERS`.
- Apex: architecture/extension points only (`ai/genora/agents/apex`), API returns 501 `APEX_NOT_IMPLEMENTED`.
- Fixed: honest 'brand not sold here' message in Nova search; product-name extraction rewritten (intent-vocabulary stripping).
