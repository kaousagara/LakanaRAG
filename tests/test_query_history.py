import asyncio
import tempfile
from lightrag import LightRAG, QueryParam
from lightrag.utils import EmbeddingFunc
from lightrag.user_profile import get_conversation_history


async def dummy_embed(texts):
    return [[0.0] * 2 for _ in texts]


async def dummy_llm(query, system_prompt=None, history_messages=None, stream=False, **kwargs):
    if stream:
        async def gen():
            yield "part1"
            yield "part2"
        return gen()
    return "dummy"


def test_query_appends_history(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("USER_PROFILE_DIR", tmpdir)
        rag = LightRAG(
            embedding_func=EmbeddingFunc(embedding_dim=2, max_token_size=10, func=dummy_embed),
            llm_model_func=dummy_llm,
        )
        param = QueryParam(mode="bypass", user_id="u1", conversation_id="c1")
        asyncio.run(rag.aquery("hello", param))
        history = get_conversation_history("u1", "c1")
        assert history[-2:] == [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "dummy"},
        ]


def test_query_appends_history_stream(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("USER_PROFILE_DIR", tmpdir)
        rag = LightRAG(
            embedding_func=EmbeddingFunc(embedding_dim=2, max_token_size=10, func=dummy_embed),
            llm_model_func=dummy_llm,
        )
        param = QueryParam(mode="bypass", user_id="u2", conversation_id="c2", stream=True)

        async def run():
            chunks = []
            response = await rag.aquery("hello", param)
            async for chunk in response:
                chunks.append(chunk)
            return chunks

        chunks = asyncio.run(run())
        assert chunks == ["part1", "part2"]
        history = get_conversation_history("u2", "c2")
        assert history[-2:] == [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "part1part2"},
        ]
