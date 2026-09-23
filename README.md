# GenOra — AI-powered multi-vendor marketplace

> 🚧 Work in progress — see [`docs/progress.md`](docs/progress.md) for the current status and
> [`docs/implementation-plan.md`](docs/implementation-plan.md) for the architecture plan.

GenOra is a multi-vendor e-commerce marketplace (buyers, sellers, admins) with an integrated
**agentic AI layer**:

| Agent | Audience | Status |
|---|---|---|
| **GenOra Nova** | Buyers — discovery, search, comparison, image search, bundles, offers, negotiation, review analysis, external price comparison | Implemented |
| **GenOra Astra** | Sellers — listing assistant, inventory, sales analytics, product performance, discount strategy, forecasting | Implemented |
| **GenOra Apex** | Enterprises | **Planned / Not implemented** (architecture only) |

## Stack
FastAPI · SQLAlchemy · Alembic · PostgreSQL + pgvector · LangGraph · Next.js · TypeScript · Tailwind · shadcn/ui · Docker

## Repository layout
```
backend/         FastAPI application (API, services, models, migrations, seed, tests)
ai/              `genora` package — agents, tools, NLU, safety, providers, forecasting
frontend/        Next.js application
database/        Postgres init scripts
infrastructure/  Dockerfiles
docs/            Architecture and operations documentation
tests/           Cross-cutting / end-to-end tests
```

Full setup instructions are added as the build progresses.
