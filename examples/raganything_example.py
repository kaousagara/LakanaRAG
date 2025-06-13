#!/usr/bin/env python
"""
Example script demonstrating the integration of MinerU parser with RAGAnything

This example shows how to:
1. Process parsed documents with RAGAnything
2. Perform multimodal queries on the processed documents
3. Handle different types of content (text, images, tables)
"""

import os
import argparse
import asyncio
from lightrag import LightRAG
from lightrag.utils import EmbeddingFunc
from lightrag.llm.ollama import ollama_model_complete, ollama_embed
from lightrag.raganything import RAGAnything


async def process_with_rag(
    file_path: str,
    output_dir: str,
    api_key: str | None = None,
    host: str | None = "http://localhost:11434",
    working_dir: str = None,
):
    """
    Process document with RAGAnything

    Args:
        file_path: Path to the document
        output_dir: Output directory for RAG results
        api_key: Optional Ollama API key
        host: Ollama server host
    """
    try:
        # Initialize RAGAnything with Ollama backend
        lightrag = LightRAG(
            working_dir=working_dir,
            llm_model_func=ollama_model_complete,
            llm_model_name="qwen2:7b",
            llm_model_kwargs={"host": host, "api_key": api_key},
            embedding_func=EmbeddingFunc(
                embedding_dim=3072,
                max_token_size=8192,
                func=lambda texts: ollama_embed(
                    texts,
                    embed_model="bge-m3:latest",
                    host=host,
                    api_key=api_key,
                ),
            ),
        )

        rag = RAGAnything(
            lightrag=lightrag,
            llm_model_func=ollama_model_complete,
            vision_model_func=ollama_model_complete,
            embedding_dim=3072,
            max_token_size=8192,
        )

        # Process document
        await rag.process_document_complete(
            file_path=file_path, output_dir=output_dir, parse_method="auto"
        )

        # Example queries
        queries = [
            "What is the main content of the document?",
            "Describe the images and figures in the document",
            "Tell me about the experimental results and data tables",
        ]

        print("\nQuerying processed document:")
        for query in queries:
            print(f"\nQuery: {query}")
            result = await rag.query_with_multimodal(query, mode="hybrid")
            print(f"Answer: {result}")

    except Exception as e:
        print(f"Error processing with RAG: {str(e)}")


def main():
    """Main function to run the example"""
    parser = argparse.ArgumentParser(description="MinerU RAG Example")
    parser.add_argument("file_path", help="Path to the document to process")
    parser.add_argument(
        "--working_dir", "-w", default="./rag_storage", help="Working directory path"
    )
    parser.add_argument(
        "--output", "-o", default="./output", help="Output directory path"
    )
    parser.add_argument(
        "--api-key", help="Optional Ollama API key for RAG processing"
    )
    parser.add_argument(
        "--host",
        default="http://localhost:11434",
        help="Ollama server host",
    )

    args = parser.parse_args()

    # Create output directory if specified
    if args.output:
        os.makedirs(args.output, exist_ok=True)

    # Process with RAG
    asyncio.run(
        process_with_rag(
            args.file_path,
            args.output,
            args.api_key,
            args.host,
            args.working_dir,
        )
    )


if __name__ == "__main__":
    main()
