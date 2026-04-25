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
