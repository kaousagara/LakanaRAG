import asyncio
from lightrag.kg.networkx_impl import NetworkXStorage
from lightrag.kg.shared_storage import initialize_share_data
from lightrag.utils import EmbeddingFunc


async def dummy_embed(texts):
    return [[0.0] * 2 for _ in texts]


def test_networkx_detect_communities(tmp_path):
    storage = NetworkXStorage(
        namespace="test",
        global_config={"working_dir": str(tmp_path)},
        embedding_func=EmbeddingFunc(
            embedding_dim=2, max_token_size=10, func=dummy_embed
        ),
    )

    async def run():
        initialize_share_data()
        await storage.initialize()
        await storage.upsert_node("A", {"entity_id": "A"})
        await storage.upsert_node("B", {"entity_id": "B"})
        await storage.upsert_node("C", {"entity_id": "C"})
        await storage.upsert_edge("A", "B", {})
        await storage.upsert_edge("B", "C", {})
        communities = await storage.detect_communities()
        assert communities
        assert set(communities.keys()) >= {"A", "B", "C"}

    asyncio.run(run())
