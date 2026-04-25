# Deploying the Multi-Agent RAG Web App

This app is a single FastAPI process that serves both the API and the frontend.
Everything ships as one Docker image, so it runs the same way on any platform.

## What's in the image

- Python 3.12 + all deps from `backend/requirements.txt`
- The embedding model (`sentence-transformers/all-mpnet-base-v2`) pre-baked
- Your `data/source/` files (re-indexed on first boot)
- The static frontend under `/`

Persistent state lives in a single directory: **`/home/user/app/data/chroma`**
— mount a volume there so the vector DB survives redeploys. (The path is
baked into the image by the `Dockerfile`; override it with the
`CHROMA_DB_PATH` env var if you prefer a different mount point.)

## Required runtime secrets

| Env var           | Required | Notes                                              |
|-------------------|----------|----------------------------------------------------|
| `GROQ_API_KEY`    | yes      | `gsk_...` from https://console.groq.com/keys       |
| `GROQ_MODEL`      | no       | defaults to `openai/gpt-oss-120b`                  |
| `CORS_ORIGINS`    | no       | comma-separated origins; `*` for open              |
| `CHROMA_DB_PATH`  | no       | image default: `/home/user/app/data/chroma`        |

Minimum recommended VM: **1 GB RAM, 1 vCPU**. The embedding model alone is
~420 MB resident.

---

## Option 1 — Local / any VPS with Docker Compose

Simplest path. Works on a $4 DigitalOcean droplet, Hetzner, EC2, your Pi, etc.

```bash
# 1. On the server
git clone <your-repo> && cd Langchain
cp .env.example .env
# edit .env and set GROQ_API_KEY=gsk_...

# 2. Build + run
docker compose up -d --build

# 3. First-time: ingest the Dell docs into Chroma
curl -X POST http://localhost:8000/api/ingest

# 4. Verify
curl http://localhost:8000/api/health
```

Put **Caddy** or **Nginx + certbot** in front for HTTPS and your own domain.

Minimal Caddy (`/etc/caddy/Caddyfile`):
```
yourdomain.com {
    reverse_proxy localhost:8000
}
```

---

## Option 2 — Hugging Face Spaces (free, zero-ops)

The repo's top-level `README.md` has HF Spaces frontmatter, so pushing this
repo to a Space builds it as a Docker Space on port 8000.

```bash
# 1. Create an empty Docker Space at https://huggingface.co/new-space
#    (SDK: Docker, Hardware: CPU basic is enough)
# 2. In the Space's Settings → Variables and secrets:
#      Secret: GROQ_API_KEY = gsk_...
# 3. Push the code:
HF_USER=your_hf_username \
HF_SPACE=your_space_name \
HF_TOKEN=hf_your_write_token \
  ./scripts/push-to-hf.sh
```

Notes:
- First build is ~5–8 minutes (it pre-downloads the embedding model).
- Auto-ingest runs on the first request after boot (~30 s).
- Spaces do **not** support persistent volumes on the free tier, so Chroma
  rebuilds from `data/source/` each cold start. This is fine because the
  corpus is small and re-ingest is fast.
- Subsequent deploys are just `git push hf HEAD:main`.

---

## Option 3 — Google Cloud Run (pay-per-request, generous free tier)

Good fit because traffic is bursty and Cloud Run bills per request.
Caveat: Cloud Run's local filesystem is ephemeral, so you need a mounted
volume for Chroma. Use a **second-gen** service + a **Cloud Storage FUSE**
mount or switch Chroma to a hosted vector DB (Pinecone, Qdrant Cloud, etc.).

Simplest version (ephemeral Chroma, re-ingests on cold start — fine for demos):

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT

# build + push
gcloud builds submit --tag gcr.io/YOUR_PROJECT/langgraph-rag

# deploy
gcloud run deploy langgraph-rag \
  --image gcr.io/YOUR_PROJECT/langgraph-rag \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --concurrency 10 \
  --timeout 300 \
  --min-instances 0 \
  --max-instances 3 \
  --set-env-vars GROQ_MODEL=openai/gpt-oss-120b \
  --set-secrets GROQ_API_KEY=GROQ_API_KEY:latest
```

For persistent Chroma on Cloud Run, either (a) add a GCS volume mount
(`--add-volume` + `--add-volume-mount`) pointing at `/home/user/app/data/chroma`, or (b)
swap Chroma for a managed vector DB.

---

## Option 4 — Render / Railway

Both give you a managed container host with a UI instead of a CLI.

**Render**
1. New -> Web Service -> connect your repo
2. Runtime: **Docker**
3. Instance type: **Standard** (2 GB) — the free 512 MB tier will OOM
4. Add a **Disk**: mount path `/home/user/app/data/chroma`, size 1 GB
5. Env vars: `GROQ_API_KEY=gsk_...`
6. Health check path: `/api/health`

**Railway**
1. New Project -> Deploy from GitHub -> pick this repo
2. Railway autodetects the `Dockerfile`
3. Variables: `GROQ_API_KEY=gsk_...`
4. Add a **Volume** mounted at `/home/user/app/data/chroma`
5. Hit the generated `*.up.railway.app` URL

---

## Post-deploy checklist

- [ ] `GET /api/health` returns `{"status":"ok","has_api_key":"yes"}`
- [ ] `POST /api/ingest` returns non-zero chunk counts for each collection
- [ ] Chat UI at `/` answers a Dell question and shows the debug trace
- [ ] HTTPS is enforced (platform-provided or Caddy/Nginx)
- [ ] `GROQ_API_KEY` is stored in platform secrets, **not** in a committed `.env`
- [ ] `CORS_ORIGINS` is set to your real domain(s) instead of `*`
- [ ] Volume backup for `/home/user/app/data/chroma` if the content matters

## Scaling notes

- Keep **1 worker per process**. The embedding model is loaded once per
  process (~420 MB); 4 workers = ~1.7 GB just for model weights.
- To go beyond ~10 concurrent users, scale **horizontally** (more instances)
  with a shared vector DB — Chroma's local file backend is single-writer.
- For heavier loads swap Chroma for Qdrant / Pinecone / Weaviate and point
  `CHROMA_DB_PATH` logic at the managed DB instead (requires code changes in
  `backend/app/ingest.py` + `backend/app/graph.py`).
