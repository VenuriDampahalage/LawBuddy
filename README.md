# LawBuddy

AI assistant that explains Sri Lankan legislation in plain language, with citations to the
exact section and page. Admins upload legislation PDFs; users chat with the assistant.

Two deployable parts:

```
frontend/     React + Vite + Tailwind (navy #142D4E, white, teal #2A9D8F)
backend/      one FastAPI app: API + the RAG agent, in one process
  src/backend/
    main.py       app, routers, startup
    core/         settings (one .env), database pool, auth/security, rate limits
    api/          HTTP routes: auth, chat (streaming), documents, laws, admin, amendments
    models/ schemas/   users, conversations, messages
    rag/          the agent: ingestion (LlamaParse, hierarchical chunking), retrieval
                  (hybrid search), graph (LangGraph), amendments, llm; rag/api.py is the
                  only entry point the routes use
  alembic/        database migrations (all tables)
  tests/          API tests + rag/ engine tests
  eval/           answer-quality test set
  scripts/        command-line tools
  data/           raw_pdfs/ (uploaded PDFs) and parsed/ (LlamaParse cache), not in git
```

## Setup

Requirements: [uv](https://docs.astral.sh/uv/), Python 3.13 (uv installs it), a Postgres
database with the `vector` extension (e.g. Neon), OpenAI and LlamaCloud API keys.
All backend commands run inside `backend/`.

```bash
cd backend
uv sync                                   # install everything
cp .env.example .env                      # then fill in the keys and DATABASE_URL
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste as JWT_SECRET in .env
uv run alembic upgrade head                                     # create tables
uv run python -m backend.cli create-admin you@example.com      # first admin account
```

## Run

```bash
cd backend  && uv run uvicorn backend.main:app --reload --port 8000   # API docs: /docs
cd frontend && npm install && npm run dev                             # http://localhost:5173
```

The frontend finds the backend through `VITE_API_URL` in `frontend/.env`
(`http://localhost:8000` locally; see `frontend/.env.example`). The backend allows the
frontend's address through `CORS_ORIGINS` in `backend/.env`. When deployed, set both in the
host's environment variables instead.

## Useful scripts (in `backend/`)

```bash
uv run python scripts/ingest_folder.py                 # ingest data/raw_pdfs/*.pdf
uv run python scripts/show_tree.py constitution.pdf    # detected legal structure
uv run python scripts/search.py "your question"        # what retrieval returns
uv run python scripts/chat.py                          # chat in the terminal
uv run pytest                                          # tests
```

## Answer quality checks

`backend/eval/golden.jsonl` holds test questions with the sections a correct answer must
use. Run it (in `backend/`) after changing prompts, retrieval or ingestion:

```bash
uv run python eval/run_eval.py                       # retrieval check (~1 min)
uv run python eval/run_eval.py --mode full           # real answers (~2-3 min)
uv run python eval/run_eval.py --mode full --repeat 3 --only custody-24h
uv run python eval/import_feedback.py                # 👎 answers -> draft cases
```

Each run is compared with the previous one of the same mode; the exit code is 1 if a question
that passed before now fails. Results and feedback drafts stay local (git-ignored).

## Amendments

Amendment Acts are scanned automatically after ingestion (or with **Scan for amendments** in
Admin → Amendments). Each change is proposed with the exact before/after text; nothing affects
answers until an admin approves it, and approvals can be reverted.

## API overview (`/api`)

| | Endpoint | Access |
|---|---|---|
| Auth | `POST /auth/register`, `POST /auth/login` (form: username=email, password), `GET /auth/me` | public / user |
| Documents | `POST /admin/documents` (PDF upload), `GET /admin/documents[/{id}]`, `POST /admin/documents/{id}/reprocess`, `DELETE /admin/documents/{id}` | admin |
| | `GET /documents/{id}/file` (source PDF; open at `#page=N`) | user |
| Chat | `POST/GET /conversations`, `GET /conversations/{id}/messages`, `DELETE /conversations/{id}` | owner |
| | `POST /conversations/{id}/messages` → Server-Sent Events: `status`, `token`, `done`, `error` | owner |

LawBuddy provides general legal information, not legal advice.
