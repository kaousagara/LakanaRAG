#!/usr/bin/env python3
"""Example script demonstrating a deep search workflow with LightRAG.

The script initialises a ``LightRAG`` instance using local Ollama models and
provides helper functions to verify a query, generate sub‑queries for missing
information and finally build a simple report composed of an introduction, a
body and a conclusion.

It is a streamlined version of a larger internal tool and can be used as a
reference for integrating LightRAG in custom async pipelines.
"""

from __future__ import annotations

from typing import Any, Optional
import argparse
import asyncio
import json
import logging
import os
import re

import nest_asyncio

from lightrag import LightRAG, QueryParam
from lightrag.llm.ollama import ollama_model_complete, ollama_embed
from lightrag.utils import EmbeddingFunc
from lightrag.kg.shared_storage import initialize_pipeline_status

nest_asyncio.apply()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WORKING_DIR = os.getenv("WORKING_DIR", "./deepsearch_data")
LLM_MODEL = os.getenv("LLM_MODEL", "gemma3:27b-it-q8_0")
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3:latest")
CONCURRENCY_LIMIT = int(os.getenv("CONCURRENCY_LIMIT", "4"))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Ensure working directory exists
os.makedirs(WORKING_DIR, exist_ok=True)

BASE_SYSTEM_PROMPT = (
    "L'agence nationale de la sécurité d'état (ANSE) est un organisme gouvernemental "
    "chargé de la protection des intérêts vitaux du Mali dans les domaines sécuritaire, "
    "religieux, sociopolitique, économique, etc. Pour cela elle procède par la recherche "
    "et le traitement du renseignement, par la production des analyses."
)

SECTION_PROMPT = (
    BASE_SYSTEM_PROMPT
    + "\n---Role---\nVous êtes un analyste de l'ANSE. Répondez toujours de manière analytique: qui fait quoi, avec qui, où, quand et comment."
)

PROMPTS = {
    "verify": SECTION_PROMPT
    + "\nAnalyse la réponse automatique pour détecter tout gap par rapport à la requête initiale. "
    "Si des informations manquent, liste-les et génère une liste de sous-requêtes pour combler ces gaps.",
    "fusion": SECTION_PROMPT
    + "\n Fusionner ces différentes parties du texte en un document unique et fluide."
    "Réorganiser l’ordre des idées pour créer une progression logique.",
}

# Asynchronous semaphore to limit concurrent calls
_semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)


async def initialize_rag() -> LightRAG:
    """Initialise a ``LightRAG`` instance with Ollama models."""
    rag = LightRAG(
        working_dir=WORKING_DIR,
        llm_model_func=ollama_model_complete,
        llm_model_name=LLM_MODEL,
        llm_model_max_async=4,
        llm_model_max_token_size=32768,
        llm_model_kwargs={
            "host": "http://localhost:11434",
            "options": {"num_ctx": 32768},
        },
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


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def parse_json_response(response_text: str) -> Optional[Any]:
    """Parse a JSON response possibly wrapped in markdown fencing."""
    match = re.search(r"```(?:json)?(.*?)```", response_text.strip(), re.DOTALL)
    json_text = match.group(1).strip() if match else response_text.strip()
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        logging.error("Invalid JSON response: %s", response_text)
        return None


async def ask_rag(query: str, prompt: str, mode: str, rag: LightRAG) -> str:
    """Send a query to LightRAG using the given mode."""
    async with _semaphore:
        try:
            return await asyncio.to_thread(
                rag.query, query, QueryParam(mode=mode), prompt
            )
        except Exception as exc:
            logging.error("RAG query failed: %s", exc)
            return ""


async def verify_query(query: str, rag: LightRAG) -> str:
    """Ensure that the user query contains enough information."""
    prompt_verif = (
        SECTION_PROMPT
        + "\nAnalyse la requête suivante et indique si elle fournit toutes les informations nécessaires"
        " pour générer un rapport analytique complet. Si la requête est suffisamment détaillée, réponds uniquement par 'ok'."
        " Sinon, liste brièvement les informations manquantes."
    )

    result = await ask_rag(query, prompt_verif, "naive", rag)
    if "ok" in result.lower():
        return query

    logging.warning("La requête est incomplète : %s", result)
    additional_info = input("Veuillez fournir les informations manquantes :\n")
    return f"{query} {additional_info}".strip()


async def generate_paragraphs(
    section_query: str, section_name: str, rag: LightRAG
) -> str:
    """Generate a short paragraph for the given section."""
    prompt = SECTION_PROMPT + (
        "\nRéponds à la requête en un paragraphe très concis sans mentionner les sources de données."
    )
    return await ask_rag(section_query, prompt, "mix", rag)


async def generate_report(query: str, rag: LightRAG) -> str:
    """Build a simple three part report from the user query."""
    prompt_title = SECTION_PROMPT + (
        "\nDonne en une seule ligne le titre correspondant à la requête sans mentionner les sources."
    )
    title = await ask_rag(query, prompt_title, "mix", rag)

    sections = []
    for name in ["Introduction", "Corps", "Conclusion"]:
        paragraph = await generate_paragraphs(query, name, rag)
        sections.append(f"## {name}\n{paragraph}\n")

    return f"# {title.strip()}\n\n" + "\n".join(sections)


# ---------------------------------------------------------------------------
# Command line interface
# ---------------------------------------------------------------------------


async def main() -> None:
    parser = argparse.ArgumentParser(description="Simple deep search demo")
    parser.add_argument("query", help="Sujet ou question de l'analyse")
    parser.add_argument(
        "--output", default="rapport_analyse.md", help="Fichier de sortie"
    )
    args = parser.parse_args()

    rag = await initialize_rag()

    try:
        checked_query = await verify_query(args.query, rag)
        logging.info("Génération du document en cours ...")
        content = await generate_report(checked_query, rag)
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(content)
        logging.info("Document enregistré dans %s", args.output)
    finally:
        await rag.finalize_storages()


if __name__ == "__main__":
    asyncio.run(main())
