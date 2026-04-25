---
title: Ma Rag
emoji: 🤖
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 8000
pinned: false
license: mit
short_description: Multi-agent RAG chat over Dell product / policy / tech docs
---

# LangGraph Multi-Agent RAG — Mobile Web App

A mobile-responsive chat app that turns a LangGraph collaborative multi-agent
pipeline (planner → product / policy / tech / general specialists with RAG +
DuckDuckGo → synthesizer) into a production-style web application. The
bundled knowledge base is a set of **Dell laptop product / policy / tech
support documents**, but the ingestion pipeline is generic — swap the files
in `data/source/` to retarget the app to any domain.

- **Backend:** FastAPI + LangGraph + LangChain + Chroma + Groq LLM
- **Frontend:** Mobile-first responsive HTML + Tailwind (CDN) + vanilla JS
- **Features:**
  - Planner picks one or more specialist agents for a single question
  - Per-domain RAG collections (`product`, `policy`, `tech`, `general`)
  - DuckDuckGo search tool for fresh external info
  - Final synthesizer merges specialist answers
  - Collapsible **Planner Trace** and **Specialist Outputs** in the UI
  - File upload endpoint to extend the knowledge base at runtime
  - Single-container deploy (Docker) with Hugging Face Spaces / Cloud Run /
    Render / Railway recipes in [`DEPLOY.md`](./DEPLOY.md)

## Project layout

```
.
├── backend/
│   ├── app/
│   │   ├── config.py       # env + paths
│   │   ├── llm.py          # LLM, embeddings, Chroma singletons
│   │   ├── tools.py        # RAG tools + DuckDuckGo tool
│   │   ├── graph.py        # LangGraph: planner → agents → synthesizer
│   │   ├── ingest.py       # classify + chunk + index documents
│   │   └── main.py         # FastAPI app + routes + static frontend
│   └── requirements.txt
├── frontend/
│   ├── index.html          # mobile-first chat UI
│   ├── app.js              # chat logic, upload, health
│   └── styles.css
├── data/
│   ├── source/             # drop your .txt/.md/.pdf/.docx here
│   └── chroma/             # persistent vector store (gitignored)
├── scripts/
│   └── push-to-hf.sh       # deploy to a Hugging Face Space
├── Dockerfile
├── docker-compose.yml
├── DEPLOY.md               # per-platform deploy recipes
├── .env.example
└── run.sh
```

## Quick start

```bash
cp .env.example .env
# edit .env: set GROQ_API_KEY=...

./run.sh
# then open http://localhost:8000
```

On first run it will:
1. Install dependencies into `.venv/`
2. Drop sample documents into `data/source/` if empty
3. Build the Chroma index lazily on the first `/api/ingest` call (or auto on upload)

To trigger the initial ingest, open the app, click **Settings → Re-index existing
docs**, or call:

```bash
curl -X POST http://localhost:8000/api/ingest
```

## Endpoints

| Method | Path            | Purpose                                                        |
| ------ | --------------- | -------------------------------------------------------------- |
| GET    | `/`             | Serves the mobile chat UI                                      |
| GET    | `/api/health`   | Backend + API-key status                                       |
| POST   | `/api/chat`     | `{ "message": "..." }` → final answer + trace + per-agent logs |
| POST   | `/api/ingest`   | Rebuild Chroma collections from `data/source/`                 |
| POST   | `/api/upload`   | `multipart/form-data` files[] → saves + re-indexes             |

### Chat response shape

```json
{
  "response": "synthesized final answer (markdown)",
  "selected_agents": ["product_agent", "policy_agent"],
  "agent_labels": { "product_agent": "Product Agent", "...": "..." },
  "agent_outputs": { "product_agent": "...", "policy_agent": "..." },
  "debug_log": "Planner selected: ...\nProduct Agent contributed.\n..."
}
```

## Configuration

All settings live in `.env` (see `.env.example`). Key ones:

- `GROQ_API_KEY` — required
- `GROQ_MODEL` — default `openai/gpt-oss-120b`
- `EMBEDDING_MODEL` — default `sentence-transformers/all-mpnet-base-v2`
- `SOURCE_DATA_DIR`, `CHROMA_DB_PATH` — override storage locations
- `CHUNK_SIZE`, `CHUNK_OVERLAP` — splitter tuning

## How document classification works

Files are routed into a specialist collection by **filename keyword**:

| Keywords in filename                                 | Collection            |
| ---------------------------------------------------- | --------------------- |
| `product`, `catalog`, `inventory`, `price`           | `product_collection`  |
| `policy`, `return`, `shipping`, `warranty`, `faq`    | `policy_collection`   |
| `tech`, `repair`, `support`, `troubleshoot`          | `tech_collection`     |
| anything else                                        | `general_collection`  |

Name your uploaded files accordingly to keep specialists sharp.

## Mobile responsiveness notes

- `100dvh` layout (no iOS URL-bar jump)
- Safe-area padding on the input footer
- Tap-sized buttons and single-column chat stream
- Textarea auto-grows and submits on Enter (Shift+Enter = newline)
- Collapsible trace / specialist panes so the screen stays clean on small devices

## Deployment

For production deploys (Docker, Hugging Face Spaces, Cloud Run, Render,
Railway, or a plain VPS), see **[DEPLOY.md](./DEPLOY.md)**. TL;DR for any
Docker host:

```bash
cp .env.example .env    # set GROQ_API_KEY=gsk_...
docker compose up -d --build
curl -X POST http://localhost:8000/api/ingest
```

### Hugging Face Spaces

This repo is Spaces-ready — the YAML frontmatter at the top of this README
configures it as a Docker Space on port 8000. A helper script handles the
one-off push:

```bash
# 1. Create an empty Docker Space at https://huggingface.co/new-space
# 2. In the Space's Settings → Variables and secrets, add:
#      Secret: GROQ_API_KEY = gsk_...
# 3. Push the code:
HF_USER=your_hf_username \
HF_SPACE=your_space_name \
HF_TOKEN=hf_your_write_token \
  ./scripts/push-to-hf.sh
```

The first build takes ~5–8 minutes (it pre-downloads the embedding model into
the image). After it's "Running", the first request triggers auto-ingest of
the documents in `data/source/` (~30 s) before answering. Subsequent deploys
are just a regular `git push hf HEAD:main`.

## Extending

The code mirrors the notebook structure so the extensions suggested there
(memory, confidence scoring, weighted voting, guardrails, more tools) slot in
cleanly — add new tools to `tools.py`, new nodes/edges in `graph.py`.
