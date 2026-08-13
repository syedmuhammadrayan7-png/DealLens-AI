# DealLens AI

**Multi-Agent Startup Due-Diligence & Venture Intelligence Platform.** DealLens structures company, market, technical, financial, and risk signals into an evidence-labelled investment memo. It is decision support, not an investment guarantee.

## Architecture

```mermaid
flowchart LR
  UI[Next.js investor interface] --> API[FastAPI API]
  API --> Flow[CrewAI Flow state]
  Flow --> Agents[Company · Market · Technical · Financial]
  Agents --> MCP[MCP client layer]
  MCP --> Finance[DealLens Finance MCP]
  Flow --> Risk[Risk Committee]
  Risk --> Memo[Investment Memo / Pydantic report]
```

## Production worker architecture

```mermaid
flowchart LR
  UI[Next.js frontend] --> API[FastAPI API]
  API --> DB[(Supabase PostgreSQL)]
  Worker[Render worker web service] --> DB
  Worker --> AI[CrewAI / OpenAI / MCP / GitHub]
  UI -->|polls| API
```

The API persists a case and queued job, then returns immediately. The worker claims one PostgreSQL job atomically and performs the long-running workflow. Report/PDF reads use stored report data and never rerun AI.

### Free-tier Render deployment

```text
Vercel
  -> Next.js frontend
Render Web Service #1
  -> FastAPI API (`uvicorn backend.main:app --host 0.0.0.0 --port $PORT`)
Render Web Service #2
  -> `python -m backend.worker_service`
  -> lightweight HTTP health server plus the durable PostgreSQL worker loop
Supabase PostgreSQL
  -> cases / jobs / reports / evidence
```

The second Render **Web Service** is a free-tier workaround for platforms that require every service to bind to `$PORT`. It exposes only `GET /` and `GET /health`, returning `{"status":"ok","service":"deallens-worker"}`. Its worker thread reuses `backend.worker.run_worker`, including atomic `FOR UPDATE SKIP LOCKED` claims, retries, report persistence, and stale-job recovery; it does not implement a second queue.

Set `PORT` only when running locally (the local default is `10000`), then run:

```powershell
$env:PORT="10000"
.\.venv\Scripts\python.exe -m backend.worker_service
```

Configure the worker service with the same backend-only environment variables as the API: `DATABASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `APP_ENV`, `WORKER_POLL_SECONDS`, `JOB_STALE_MINUTES`, `JOB_MAX_ATTEMPTS`, `OPENAI_TIMEOUT_SECONDS`, `OPENAI_MAX_RETRIES`, `DEALLENS_CACHE_TTL_SECONDS`, `DEALLENS_MAX_PITCH_DECK_MB`, and optionally `GITHUB_TOKEN`. Do not expose them to Vercel.

On SIGTERM/Ctrl+C, Uvicorn closes the HTTP service and the lifespan handler requests that polling stop. It never marks an in-progress job completed; an interrupted active job remains durable and is handled by existing stale-job recovery after its lease timeout. A free Render web service can still sleep or be restarted, so queue latency and recovery time are not suitable for low-latency or always-on production workloads. Multiple accidental worker instances are safe with respect to duplicate execution because PostgreSQL job claiming uses row locking and `SKIP LOCKED`.

CrewAI owns specialist-agent orchestration and bounded flow routing. MCP owns reusable integrations: deterministic finance tools, diligence frameworks as resources, and an investment-committee memo prompt. The flow allows at most one targeted retry before risk synthesis.

## Deterministic scoring

CrewAI classifies evidence and writes the narrative; it does not set the final numeric scores. `backend/services/scoring.py` converts inspectable research facts and classified evidence into bounded 0–100 scorecards. Overall category weights are Market **20%**, Technology **20%**, Traction **25%**, Financials **20%**, and Team **15%**.

Technology uses repository recency, recent commit depth, contributor ranges, releases, repository age, logarithmically scaled stars/forks, language, license, and a contextual issue flag. Market treats a company website as limited positioning evidence and prioritizes independent market and competitor signals. Traction distinguishes founder-supplied revenue/customers, capped public adoption, and independently supported commercial or growth evidence. Financials score only actual revenue, burn, cash/runway, growth, ARPU, concentration, and cash-flow inputs: Finance MCP availability alone earns **zero** points. Team separates public presence, named people, independently verifiable backgrounds, experience, and complementarity.

Each scorecard reports factor points/max points, deductions, evidence notes, and a separate confidence level based on coverage and independent support. Recommendation combines the weighted score with confidence, unavailable/conflicting evidence, red flags, and critical gaps in traction, financials, and team—not score alone. Historical persisted reports continue to load because the new factor maximum is optional-compatible.

## OpenAI configuration

All CrewAI agents use the same cost-efficient model, configured centrally in `backend/config.py`. The API key is read **only** from the backend process environment or local `.env`; it is never included in frontend code or API responses.

```bash
copy .env.example .env
# Edit .env and add OPENAI_API_KEY. Do not commit this file.
```

```dotenv
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
```

If `OPENAI_API_KEY` is missing, `POST /api/cases` returns a clear `503 OPENAI_CONFIGURATION_ERROR`; it does not substitute fake AI output. The dashboard's `/report` is a separately and visibly labelled static demo.

## Agents

- Company Intelligence: public claims, product, team and traction evidence.
- Market & Competition: market, competitors, substitutes and moat signals.
- Technical Due Diligence: public GitHub metadata only.
- Financial Analysis: interprets deterministic MCP metrics.
- Risk Committee: challenges gaps and contradictions.
- Investment Memo: structured decision-support output.

## Finance MCP

The custom server (`backend/mcp/servers/finance_server.py`) provides tools: `calculate_runway`, `calculate_monthly_burn`, `calculate_arpu`, `calculate_revenue_growth`, `calculate_customer_concentration`, and `calculate_basic_unit_economics`.

Resources: `deallens://frameworks/preseed`, `deallens://frameworks/saas-metrics`, and `deallens://risk-policy`. Prompt: `investment_committee_memo`.

## API

- `GET /api/health` — safe configuration status (no secret values)
- `GET /api/mcp/discovery` — server tools, resources and prompts
- `POST /api/cases` — queues a real CrewAI case; requires OpenAI config
- `POST /api/cases/with-pitch-deck` — accepts JSON and a size-limited PDF deck; text is founder-provided evidence
- `GET /api/cases/{case_id}/status` — safe stage/progress metadata only
- `GET /api/cases/{case_id}/report` — real structured result when complete
- `GET /api/cases/{case_id}/memo.pdf` — exported real investment memo
- `GET /api/cases/demo` — explicitly labelled static demo report

## Run locally

Backend (from repository root):

```bash
# CrewAI currently supports Python 3.10–3.13. Use a 3.13 environment.
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
pytest backend/tests -q
```

Frontend:

```bash
cd frontend
npm install
npm run dev
npm run typecheck
npm run build
```

## Evidence, security, and current MVP limits

Evidence is classified as verified, supported, founder-provided, unverified, conflicting, or unavailable. GitHub lookup validates public repository URLs, fetches metadata/activity/contributors/releases when available, uses a TTL cache, and has strict retry/backoff behavior. Public website research is a low-friction optional source; inaccessible sites become unavailable evidence. API keys remain server-side; `.env` is git-ignored. Jobs, cases, reports, score breakdowns, and evidence are durably stored in PostgreSQL.

## Roadmap

Add persistent case storage, approved search MCP connectors, authenticated GitHub rate-limit handling, and a deployment pipeline.
