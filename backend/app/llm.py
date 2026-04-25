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
