```python
# backend/requirements.txt
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.7.0
python-dotenv>=1.0.1
python-multipart>=0.0.9

langgraph>=0.2.40
langchain>=0.3.0
langchain-community>=0.3.0
langchain-core>=0.3.0
langchain-groq>=0.2.0
langchain-huggingface>=0.1.0
langchain-chroma>=0.1.4
langchain-text-splitters>=0.3.0

chromadb>=0.5.0
sentence-transformers>=3.0.0

unstructured[md]>=0.15.0
duckduckgo-search>=6.2.0
ddgs>=3.9.0

# end_of_file
```

```python
# backend/app/config.py
"""Central configuration loaded from environment variables."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))

    EMBEDDING_MODEL: str = os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2"
    )

    SOURCE_DATA_DIR: Path = Path(
        os.getenv("SOURCE_DATA_DIR", str(BASE_DIR / "data" / "source"))
    )
    CHROMA_DB_PATH: Path = Path(
        os.getenv("CHROMA_DB_PATH", str(BASE_DIR / "data" / "chroma"))
    )

    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "800"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "150"))

    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    CORS_ORIGINS: list[str] = [
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "*").split(",")
        if o.strip()
    ]


settings = Settings()

settings.SOURCE_DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.CHROMA_DB_PATH.mkdir(parents=True, exist_ok=True)

if settings.GROQ_API_KEY:
    os.environ["GROQ_API_KEY"] = settings.GROQ_API_KEY

# end_of_file
```

```python
# backend/app/graph.py
"""LangGraph pipeline: planner -> specialist agents -> synthesizer."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Dict, List, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import create_react_agent

from .llm import get_llm
from .tools import (
    duckduckgo_search,
    general_rag_tool,
    policy_clause_extract,
    policy_rag_tool,
    product_rag_tool,
    tech_rag_tool,
)

logger = logging.getLogger("app.graph")


def _user_safe_error(exc: Exception) -> str:
    """Return a short, non-leaky error message for the UI.

    Raw upstream exceptions from the LLM provider can include organization
    IDs, service-tier metadata, billing URLs, and occasionally request
    headers. We log the full detail server-side and surface a classified
    short message to the client.
    """
    text = str(exc).lower()
    if "rate_limit" in text or "rate limit" in text or "429" in text:
        return (
            "The language model provider is currently rate-limiting requests. "
            "Please try again in a few minutes."
        )
    if "invalid_api_key" in text or "authentication" in text or "401" in text:
        return "The language model provider rejected the request credentials."
    if "timeout" in text or "timed out" in text:
        return "The language model provider timed out. Please try again."
    if "connection" in text or "network" in text:
        return "Could not reach the language model provider. Please try again."
    return "The language model provider returned an unexpected error."

VALID_AGENTS = ["product_agent", "policy_agent", "tech_agent", "general_agent"]

AGENT_LABELS = {
    "product_agent": "Product Agent",
    "policy_agent": "Policy Agent",
    "tech_agent": "Tech Agent",
    "general_agent": "General Agent",
}


class AgentState(TypedDict, total=False):
    query: str
    response: str
    selected_agents: List[str]
    agent_outputs: Dict[str, str]
    debug_log: str


@lru_cache(maxsize=1)
def _build_agents():
    llm = get_llm()
    product = create_react_agent(
        llm,
        tools=[product_rag_tool, duckduckgo_search],
        prompt=(
            "You are the Product Agent. Handle buying questions, product specs, "
            "inventory, and prices. Prefer internal RAG search for company facts. "
            "Use DuckDuckGo only when the user asks for current or external info. "
            "Be concise and practical."
        ),
    )
    policy = create_react_agent(
        llm,
        tools=[policy_rag_tool, policy_clause_extract, duckduckgo_search],
        prompt=(
            "You are the Policy Agent. Handle return rules, warranty, shipping, "
            "and FAQ. Prefer internal RAG search for company policy. "
            "Use DuckDuckGo only if current external info is required. "
            "If the policy is not found internally, say so clearly.\n\n"
            "IMPORTANT: After you have an answer, you MUST call the "
            "`policy_clause_extract` tool with the user's question to pull the "
            "EXACT verbatim clause from the policy documents. Then end your "
            "response with an 'Evidence' section that shows that clause "
            "unchanged (as a block quote) together with its source file, so "
            "the user can see proof that the answer is correct. If the tool "
            "returns NO_CLAUSE_FOUND, say explicitly that no matching clause "
            "was found in the internal policy documents and do not fabricate "
            "one."
        ),
    )
    tech = create_react_agent(
        llm,
        tools=[tech_rag_tool, duckduckgo_search],
        prompt=(
            "You are the Tech Agent. Handle troubleshooting and technical "
            "explanations. Use internal technical documents first. "
            "Use DuckDuckGo when updated troubleshooting or external facts are "
            "needed. Give safe, step-by-step advice."
        ),
    )
    general = create_react_agent(
        llm,
        tools=[general_rag_tool, duckduckgo_search],
        prompt=(
            "You are the General Agent. Handle general chat, broad questions, "
            "and off-topic requests. Use DuckDuckGo when outside or current "
            "information is needed. Be helpful and clear."
        ),
    )
    return {
        "product_agent": product,
        "policy_agent": policy,
        "tech_agent": tech,
        "general_agent": general,
    }


def _normalize_agent_list(text: str) -> List[str]:
    cleaned = text.lower().replace('"', "").replace("'", "")
    raw = [p.strip() for p in cleaned.replace("\n", ",").split(",") if p.strip()]
    agents: List[str] = []
    for item in raw:
        if item in VALID_AGENTS and item not in agents:
            agents.append(item)
    return agents or ["general_agent"]


PLANNER_PROMPT = """
You are a planner for a collaborative multi-agent AI system.

Choose one or more agents that should help answer the user's question.

Available agents:
- product_agent = products, catalog, specs, prices, inventory, buying decisions
- policy_agent = return policy, warranty, refund, shipping, FAQ, store rules
- tech_agent = troubleshooting, repair, setup, bugs, device support, technical issues
- general_agent = general explanation, broad knowledge, synthesis help, anything else

Rules:
1. You may choose MULTIPLE agents if the question spans multiple domains.
2. Return a comma-separated list using only these exact names.
3. Do not explain your choice.
4. If unsure, include general_agent.

Examples:
- "What products are available?" -> product_agent
- "What is your return policy and warranty?" -> policy_agent
- "What Dell laptops do you have and can I return them after 14 days?" -> product_agent, policy_agent
- "What products are available, what is the return policy, and how do I fix overheating?" -> product_agent, policy_agent, tech_agent
- "Tell me the latest AI trends in 2026" -> general_agent
""".strip()


def planner_node(state: AgentState) -> AgentState:
    query = state["query"]
    try:
        resp = get_llm().invoke(
            [SystemMessage(content=PLANNER_PROMPT), HumanMessage(content=query)]
        )
        selected = _normalize_agent_list(resp.content)
    except Exception:
        selected = ["general_agent"]
    return {
        "selected_agents": selected,
        "debug_log": f"Planner selected: {', '.join(selected)}",
    }


def _extract_final_text(result) -> str:
    try:
        msgs = result.get("messages", [])
        if msgs:
            last = msgs[-1]
            return getattr(last, "content", str(last))
    except Exception:
        pass
    return str(result)


def run_selected_agents_node(state: AgentState) -> AgentState:
    agents = _build_agents()
    query = state["query"]
    selected = state.get("selected_agents") or ["general_agent"]
    outputs: Dict[str, str] = {}
    logs = [state.get("debug_log", "")]

    for name in selected:
        agent = agents.get(name)
        if agent is None:
            outputs[name] = f"Unknown agent: {name}"
            continue
        try:
            result = agent.invoke({"messages": [HumanMessage(content=query)]})
            outputs[name] = _extract_final_text(result)
        except Exception as e:
            logger.exception("Agent %s failed", name)
            outputs[name] = _user_safe_error(e)
        logs.append(f"{AGENT_LABELS.get(name, name)} contributed.")

    return {
        "agent_outputs": outputs,
        "debug_log": "\n".join([x for x in logs if x]),
    }


def synthesize_node(state: AgentState) -> AgentState:
    query = state["query"]
    outputs = state.get("agent_outputs", {}) or {}
    selected = state.get("selected_agents", []) or []

    if not outputs:
        return {
            "response": "No specialist output was produced.",
            "debug_log": (state.get("debug_log", "") or "")
            + "\nNo agent outputs to synthesize.",
        }

    notes = [f"[{n}]\n{outputs[n]}" for n in selected if n in outputs]

    prompt = f"""
You are the final synthesizer in a multi-agent system.

User question:
{query}

Specialist outputs:
{chr(10).join(notes)}

Instructions:
1. Merge the specialist outputs into one coherent final answer.
2. Keep the response concise but complete.
3. If different agents cover different parts, integrate them smoothly.
4. If something is uncertain or missing, say so clearly.
5. Do not mention internal chain-of-thought.
6. When helpful, organize the answer with short sections or bullets.
7. If any specialist included an "Evidence" section with a block-quoted
   verbatim clause and its source, preserve that block quote EXACTLY as
   written (do not paraphrase, shorten, or reformat it) and keep it under a
   final "Evidence" heading so the user can see proof of the answer.
""".strip()

    try:
        resp = get_llm().invoke(
            [
                SystemMessage(content="You are a careful answer synthesizer."),
                HumanMessage(content=prompt),
            ]
        )
        final = resp.content.strip()
    except Exception as e:
        logger.exception("Synthesizer failed")
        final = (
            f"{_user_safe_error(e)}\n\n"
            "Falling back to raw specialist outputs:\n\n"
            + "\n\n".join(notes)
        )

    return {
        "response": final,
        "debug_log": (state.get("debug_log", "") or "")
        + f"\nSynthesizer merged outputs from: {', '.join(selected)}",
    }


@lru_cache(maxsize=1)
def get_app():
    workflow = StateGraph(AgentState)
    workflow.add_node("planner", planner_node)
    workflow.add_node("run_selected_agents", run_selected_agents_node)
    workflow.add_node("synthesize", synthesize_node)
    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "run_selected_agents")
    workflow.add_edge("run_selected_agents", "synthesize")
    workflow.add_edge("synthesize", END)
    return workflow.compile()


def run_query(query: str) -> Dict:
    app = get_app()
    result = app.invoke(
        {
            "query": query,
            "response": "",
            "selected_agents": [],
            "agent_outputs": {},
            "debug_log": "",
        }
    )
    return {
        "query": query,
        "response": result.get("response", ""),
        "selected_agents": result.get("selected_agents", []),
        "agent_outputs": result.get("agent_outputs", {}),
        "debug_log": result.get("debug_log", ""),
    }

# end_of_file
```

```python
# backend/app/ingest.py
"""Document ingestion: classify into domain collections, chunk, and index."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List

from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader, UnstructuredFileLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import settings
from .llm import get_chroma_client, get_embeddings

logger = logging.getLogger("app.ingest")

COLLECTIONS = [
    "product_collection",
    "policy_collection",
    "tech_collection",
    "general_collection",
]


def classify_collection(filename: str) -> str:
    fname = filename.lower()
    if any(k in fname for k in ["product", "catalog", "inventory", "price"]):
        return "product_collection"
    if any(k in fname for k in ["policy", "return", "shipping", "warranty", "faq"]):
        return "policy_collection"
    if any(k in fname for k in ["tech", "repair", "support", "troubleshoot"]):
        return "tech_collection"
    return "general_collection"


def _reset_collections() -> List[str]:
    client = get_chroma_client()
    removed = []
    for name in COLLECTIONS:
        try:
            client.delete_collection(name)
            removed.append(name)
        except Exception:
            pass
    return removed


# File extensions that can be read as plain UTF-8 text. We keep this short
# and explicit so the fast TextLoader path is used for the common cases.
_PLAIN_TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".rst", ".log", ".csv", ".json", ".yaml", ".yml"}


def _loader_for(path: Path):
    """Return the most appropriate loader for ``path``.

    Plain-text / markdown files use ``TextLoader`` so we avoid the
    ``unstructured`` partitioners entirely -- those have heavy optional
    dependencies (NLTK data, libmagic, etc.) that fail silently in locked-down
    environments such as Hugging Face Spaces. Binary/structured formats
    (PDF / DOCX / HTML / ...) still go through ``UnstructuredFileLoader``.
    """
    if path.suffix.lower() in _PLAIN_TEXT_SUFFIXES:
        return TextLoader(str(path), encoding="utf-8", autodetect_encoding=True)
    return UnstructuredFileLoader(str(path))


def _load_documents(folder: Path):
    """Load every file under ``folder``, logging any file that fails to parse.

    We intentionally do NOT use ``silent_errors=True`` here -- a silent failure
    produces an empty knowledge base at runtime (e.g. when an optional parser
    dependency is missing) and is very hard to diagnose later.
    """
    if not folder.exists():
        return []

    candidates = [
        folder / name
        for name in sorted(os.listdir(folder))
        if not name.startswith(".") and (folder / name).is_file()
    ]

    docs = []
    for path in candidates:
        try:
            loader = _loader_for(path)
            docs.extend(loader.load())
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", path.name, exc)
    return docs


def ensure_sample_docs() -> bool:
    """Create sample teaching docs if the source folder is empty."""
    folder = settings.SOURCE_DATA_DIR
    folder.mkdir(parents=True, exist_ok=True)
    visible = [f for f in os.listdir(folder) if not f.startswith(".")]
    if visible:
        return False

    samples = {
        "products.txt": (
            "Dell Store Product Notes\n"
            "- Dell XPS 15 is available with 16GB, 32GB, and 64GB RAM configurations.\n"
            "- Dell Inspiron is designed for everyday productivity and home use.\n"
            "- Dell Alienware laptops are built for high-performance gaming.\n"
            "- The store may launch promotional bundles during festive periods.\n"
        ),
        "policies.txt": (
            "Customer Policy Notes\n"
            "- Returns are accepted within 14 days if the item is in resalable condition.\n"
            "- Warranty claims require proof of purchase.\n"
            "- Shipping times are usually 3 to 5 business days.\n"
            "- Opened software products are non-returnable.\n"
        ),
        "tech.txt": (
            "Technical Support Notes\n"
            "- If a Dell laptop overheats, clean the vents and avoid blocking airflow.\n"
            "- Restarting a device can solve many temporary software issues.\n"
            "- Keep Windows and Dell drivers updated for the latest security patches.\n"
            "- Back up your laptop before major updates.\n"
        ),
    }
    for name, content in samples.items():
        (folder / name).write_text(content, encoding="utf-8")
    return True


def build_knowledge_base(reset: bool = True) -> Dict[str, int]:
    """Ingest all files in SOURCE_DATA_DIR into Chroma collections.

    Returns a map of collection_name -> chunks stored.
    """
    ensure_sample_docs()

    if reset:
        _reset_collections()

    docs = _load_documents(settings.SOURCE_DATA_DIR)
    if not docs:
        logger.warning(
            "No documents were parsed from %s. If the folder contains files, "
            "a parser dependency may be missing (e.g. `unstructured[md]` for "
            "Markdown).",
            settings.SOURCE_DATA_DIR,
        )
        return {name: 0 for name in COLLECTIONS}

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
    )

    buckets: Dict[str, list] = {name: [] for name in COLLECTIONS}

    for doc in docs:
        source = doc.metadata.get("source", "unknown.txt")
        filename = os.path.basename(source)
        target = classify_collection(filename)
        chunks = splitter.split_documents([doc])
        for c in chunks:
            c.metadata["source_file"] = filename
        buckets[target].extend(chunks)

    client = get_chroma_client()
    embeddings = get_embeddings()

    results: Dict[str, int] = {}
    for name, chunk_list in buckets.items():
        if not chunk_list:
            results[name] = 0
            continue
        Chroma.from_documents(
            documents=chunk_list,
            embedding=embeddings,
            client=client,
            collection_name=name,
        )
        results[name] = len(chunk_list)

    logger.info(
        "Ingestion complete: %s",
        ", ".join(f"{k}={v}" for k, v in results.items()),
    )
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    summary = build_knowledge_base(reset=True)
    print("Ingestion complete:")
    for k, v in summary.items():
        print(f"  {k}: {v} chunks")

# end_of_file
```

```python
# backend/app/llm.py
"""Shared LLM, embeddings, and Chroma client singletons."""
from __future__ import annotations

from functools import lru_cache

import chromadb
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings

from .config import settings


@lru_cache(maxsize=1)
def get_llm() -> ChatGroq:
    if not settings.GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Add it to backend/.env or your environment."
        )
    return ChatGroq(
        model=settings.GROQ_MODEL,
        temperature=settings.LLM_TEMPERATURE,
    )


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL)


@lru_cache(maxsize=1)
def get_chroma_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=str(settings.CHROMA_DB_PATH))

# end_of_file
```

```python
# backend/app/main.py
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

# end_of_file
```

```python
# backend/app/tools.py
"""RAG retrieval tools + DuckDuckGo search tool for specialist agents."""
from __future__ import annotations

import logging
from functools import lru_cache

from langchain_chroma import Chroma
from langchain_community.tools.ddg_search.tool import DuckDuckGoSearchRun
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from .llm import get_chroma_client, get_embeddings, get_llm

logger = logging.getLogger("app.tools")


@lru_cache(maxsize=1)
def _ddg() -> DuckDuckGoSearchRun:
    return DuckDuckGoSearchRun()


def make_retrieval_tool(collection_name: str, tool_name: str, description: str):
    @tool(tool_name)
    def retrieval_tool(query: str) -> str:
        """Search the internal vector database for grounded company knowledge."""
        try:
            db = Chroma(
                client=get_chroma_client(),
                collection_name=collection_name,
                embedding_function=get_embeddings(),
            )
            docs = db.similarity_search(query, k=3)
            if not docs:
                return "No internal documents found."
            parts = []
            for i, d in enumerate(docs, start=1):
                src = d.metadata.get("source_file", "unknown")
                parts.append(f"[{i}] Source: {src}\n{d.page_content}")
            return "\n\n".join(parts)
        except Exception:
            logger.exception("Retrieval failed for %s", collection_name)
            return "Internal retrieval error."

    retrieval_tool.description = description
    return retrieval_tool


@tool("duckduckgo_search")
def duckduckgo_search(query: str) -> str:
    """Search the web for recent or external information."""
    try:
        return _ddg().run(query)
    except Exception:
        logger.exception("DuckDuckGo search failed")
        return "Web search is temporarily unavailable."


_CLAUSE_EXTRACTOR_SYSTEM_PROMPT = (
    "You are an evidence extractor for a customer-facing policy assistant.\n"
    "Given a user question and a set of retrieved policy excerpts, your job is to\n"
    "return the EXACT verbatim clause(s) from the excerpts that directly answer\n"
    "the question -- nothing more, nothing less.\n\n"
    "Strict rules:\n"
    "1. Copy the clause EXACTLY as it appears in the excerpt. Do NOT paraphrase,\n"
    "   summarize, translate, correct grammar, or change punctuation.\n"
    "2. Choose the shortest span (1-3 sentences, or a single bullet) that fully\n"
    "   answers the question.\n"
    "3. If multiple distinct clauses are needed, return each as its own quote.\n"
    "4. If NOTHING in the excerpts answers the question, reply with exactly:\n"
    "   NO_CLAUSE_FOUND\n"
    "5. Never invent text that is not present in the excerpts.\n\n"
    "Output format (and nothing else):\n"
    '> "<exact clause copied verbatim>"\n'
    "— Source: <source_file>\n"
)


@tool("policy_clause_extract")
def policy_clause_extract(question: str) -> str:
    """Extract the EXACT verbatim clause from the internal policy documents that
    answers the user's question, so it can be shown to the user as evidence /
    proof that the answer is correct.

    Use this tool whenever you give a policy answer so the user can see the
    underlying clause. Input: the user's original question (or a focused
    rephrasing of it). Output: a block-quoted verbatim clause plus its source
    file, or the literal string "NO_CLAUSE_FOUND" if the policy documents do
    not contain an answer.
    """
    try:
        db = Chroma(
            client=get_chroma_client(),
            collection_name="policy_collection",
            embedding_function=get_embeddings(),
        )
        docs = db.similarity_search(question, k=4)
    except Exception:
        logger.exception("Policy clause retrieval failed")
        return "Policy evidence lookup is temporarily unavailable."

    if not docs:
        return "NO_CLAUSE_FOUND"

    excerpts = []
    for i, d in enumerate(docs, start=1):
        src = d.metadata.get("source_file", "unknown")
        excerpts.append(f"[Excerpt {i} | source: {src}]\n{d.page_content}")
    joined = "\n\n".join(excerpts)

    user_prompt = (
        f"User question:\n{question}\n\n"
        f"Retrieved policy excerpts:\n{joined}\n\n"
        "Return only the verbatim clause(s) in the required output format."
    )

    try:
        resp = get_llm().invoke(
            [
                SystemMessage(content=_CLAUSE_EXTRACTOR_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ]
        )
        extracted = (resp.content or "").strip()
    except Exception:
        logger.exception("Clause extraction LLM call failed")
        return "Policy evidence lookup is temporarily unavailable."

    if not extracted or extracted.upper().startswith("NO_CLAUSE_FOUND"):
        return "NO_CLAUSE_FOUND"
    return extracted


product_rag_tool = make_retrieval_tool(
    "product_collection",
    "product_rag_search",
    "Search internal product, catalog, pricing, and inventory documents.",
)
policy_rag_tool = make_retrieval_tool(
    "policy_collection",
    "policy_rag_search",
    "Search internal return policy, warranty, shipping, and FAQ documents.",
)
tech_rag_tool = make_retrieval_tool(
    "tech_collection",
    "tech_rag_search",
    "Search internal technical support and troubleshooting documents.",
)
general_rag_tool = make_retrieval_tool(
    "general_collection",
    "general_rag_search",
    "Search general internal documents when no specialist collection fits.",
)

# end_of_file
```

```python
# backend/app/__init__.py

# end_of_file
```
