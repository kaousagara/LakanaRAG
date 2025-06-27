"""Minimal example demonstrating the 'deepsearch' mode."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os

from lightrag import LightRAG, QueryParam
from lightrag.llm.ollama import ollama_model_complete, ollama_embed
from lightrag.utils import EmbeddingFunc
from lightrag.kg.shared_storage import initialize_pipeline_status

logging.basicConfig(level=logging.INFO)

WORKING_DIR = os.getenv("WORKING_DIR", "./deepsearch_data")
LLM_MODEL = os.getenv("LLM_MODEL", "gemma3:27b-it-q8_0")
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3:latest")


async def initialize_rag() -> LightRAG:
    rag = LightRAG(
        working_dir=WORKING_DIR,
        llm_model_func=ollama_model_complete,
        llm_model_name=LLM_MODEL,
        llm_model_kwargs={"host": "http://localhost:11434"},
        embedding_func=EmbeddingFunc(
            embedding_dim=1024,
            max_token_size=8192,
            func=lambda texts: ollama_embed(
                texts, embed_model=EMBED_MODEL, host="http://localhost:11434"
            ),
        ),
    )
    await rag.initialize_storages()
    await initialize_pipeline_status()
    return rag


async def main() -> None:
    parser = argparse.ArgumentParser(description="Deepsearch demo")
    parser.add_argument("query", help="Question d'analyse")
    args = parser.parse_args()

    rag = await initialize_rag()
    try:
        resp = await rag.aquery(args.query, QueryParam(mode="deepsearch"))
        print(resp)
    finally:
        await rag.finalize_storages()


if __name__ == "__main__":
    asyncio.run(main())
