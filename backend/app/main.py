"""FastAPI app: serves the multi-agent pipeline + the responsive web UI."""
from __future__ import annotations

import logging
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import settings
from .graph import AGENT_LABELS, run_query
from .ingest import COLLECTIONS, build_knowledge_base, ensure_sample_docs
from .llm import get_chroma_client

logger = logging.getLogger("app.main")


def _chroma_is_empty() -> bool:
    """Return True if no collection has any vectors yet."""
    try:
        client = get_chroma_client()
        for name in COLLECTIONS:
            try:
                col = client.get_collection(name)
                if col.count() > 0:
                    return False
            except Exception:
                continue
        return True
    except Exception:
        return True


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # On first boot (e.g. on ephemeral hosts like Hugging Face Spaces) build
    # the knowledge base automatically so the UI works immediately. Set
    # AUTO_INGEST_ON_STARTUP=0 to disable.
    if os.getenv("AUTO_INGEST_ON_STARTUP", "1") == "1":
        try:
            ensure_sample_docs()
            if _chroma_is_empty():
                logger.info("Chroma is empty; auto-ingesting knowledge base...")
                summary = build_knowledge_base(reset=False)
                total = sum(summary.values())
                pretty = ", ".join(f"{k}={v}" for k, v in summary.items())
                if total == 0:
                    logger.warning(
                        "Auto-ingest produced 0 chunks (%s). Check that "
                        "source docs exist and that all required parser "
                        "dependencies are installed.",
                        pretty,
                    )
                else:
                    logger.info("Auto-ingest complete: %s", pretty)
            else:
                logger.info("Chroma already populated; skipping auto-ingest.")
        except Exception as exc:
            logger.warning("Auto-ingest failed (app will still start): %s", exc)
    yield

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"

app = FastAPI(
    title="LangGraph Multi-Agent RAG Chat",
    description=(
        "Collaborative multi-agent chat with planner, specialist RAG agents, "
        "DuckDuckGo search, and final synthesis."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    response: str
    selected_agents: List[str]
    agent_labels: Dict[str, str]
    agent_outputs: Dict[str, str]
    debug_log: str


class IngestResponse(BaseModel):
    status: str
    chunks_per_collection: Dict[str, int]
    source_dir: str


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {
        "status": "ok",
        "model": settings.GROQ_MODEL,
        "has_api_key": "yes" if settings.GROQ_API_KEY else "no",
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    if not settings.GROQ_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="GROQ_API_KEY is not configured on the server.",
        )
    try:
        result = run_query(req.message)
    except Exception as e:
        logger.exception("run_query failed")
        raise HTTPException(
            status_code=500,
            detail="Internal server error. See server logs for details.",
        ) from e

    return ChatResponse(
        response=result["response"],
        selected_agents=result["selected_agents"],
        agent_labels=AGENT_LABELS,
        agent_outputs=result["agent_outputs"],
        debug_log=result["debug_log"],
    )


@app.post("/api/ingest", response_model=IngestResponse)
def ingest(reset: bool = True) -> IngestResponse:
    ensure_sample_docs()
    summary = build_knowledge_base(reset=reset)
    return IngestResponse(
        status="ok",
        chunks_per_collection=summary,
        source_dir=str(settings.SOURCE_DATA_DIR),
    )


@app.post("/api/upload", response_model=IngestResponse)
async def upload(files: List[UploadFile] = File(...)) -> IngestResponse:
    settings.SOURCE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    saved: List[str] = []
    for f in files:
        if not f.filename:
            continue
        dest = settings.SOURCE_DATA_DIR / Path(f.filename).name
        with dest.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        saved.append(dest.name)

    if not saved:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    summary = build_knowledge_base(reset=True)
    return IngestResponse(
        status=f"uploaded {len(saved)} file(s) and re-indexed",
        chunks_per_collection=summary,
        source_dir=str(settings.SOURCE_DATA_DIR),
    )


if FRONTEND_DIR.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(FRONTEND_DIR)),
        name="assets",
    )

    @app.get("/")
    def root() -> FileResponse:
        return FileResponse(str(FRONTEND_DIR / "index.html"))
