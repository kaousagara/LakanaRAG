import subprocess
import os
from fastapi import FastAPI
from pydantic import BaseModel
import httpx

MODEL_PATH = os.environ.get("VLLM_MODEL_PATH", "/home/lakana/models/Llama-2-13b-hf")


def start_vllm():
    """Launch the vLLM OpenAI-compatible API server if not already running."""
    cmd = [
        "python3",
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--model",
        MODEL_PATH,
        "--tensor-parallel-size",
        os.environ.get("VLLM_TP", "2"),
        "--dtype",
        os.environ.get("VLLM_DTYPE", "float16"),
        "--port",
        os.environ.get("VLLM_PORT", "8000"),
    ]
    return subprocess.Popen(cmd)


vllm_process = start_vllm()

app = FastAPI()


class CompletionRequest(BaseModel):
    model: str
    prompt: str
    max_tokens: int = 128
    temperature: float = 0.7


@app.post("/v1/completions")
async def completions(request: CompletionRequest):
    payload = request.dict()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://localhost:{os.environ.get('VLLM_PORT', '8000')}/v1/completions",
            json=payload,
        )
        return resp.json()
