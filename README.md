# Multi-LLM Research Chat

Implements `multi-llm-research-chat-implementation-plan.md` (V1, phases 1–8).

Core principle: **Store everything, send only what is useful.**
PostgreSQL (SQLite for zero-setup dev) holds the FULL TRANSCRIPT; the
ContextBuilder sends each LLM only ACTIVE CONTEXT
(original question + summary of old history + last N complete turns + role).

## Quickstart (dev, no Postgres needed)

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python seed_demo.py
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
# docs: http://localhost:8000/docs
```

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173 (proxies API to :8000)
```

## Production (Postgres)

```bash
docker compose up --build
# backend :8000, frontend :5173, postgres :5432
# set DATABASE_URL=postgresql+psycopg2://research:research@db:5432/research_chat
# migrations: alembic upgrade head
```

Set real keys in `backend/.env` (copy from `.env.example`):
`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`.
Without keys, `mock` provider models work end-to-end (used by tests/seed).

## API (plan §19)

```
POST   /groups | GET /groups | GET /groups/{id}
POST   /groups/{id}/models | DELETE /groups/{id}/models/{model_id}
POST   /models | GET /models
POST   /conversations | GET /conversations/{id}
POST   /conversations/{id}/start | /pause | /stop | /continue
POST   /conversations/{id}/turn        # single turn (Phase 2 check)
POST   /conversations/{id}/summarize
POST   /conversations/{id}/retry/{turn_number}
GET    /conversations/{id}/turns       # full transcript (never truncated)
GET    /conversations/{id}/stream      # SSE streaming (Phase 8)
GET    /conversations/{id}/context-preview
```

## Architecture (plan §21)

```
React -> FastAPI -> Conversation/TurnManager -> ContextBuilder -> LLMManager
                        |                          |                   |
                     PostgreSQL              summary+recent turns   OpenAI/Anthropic/
                                              (sliding window)     Gemini/OpenRouter/Local/Mock
```

## Tests

```bash
cd backend
.\.venv\Scripts\python -m pytest tests -v   # 9 tests: sliding window, round-robin, errors, API
```
