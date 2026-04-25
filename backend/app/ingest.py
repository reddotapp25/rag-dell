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
