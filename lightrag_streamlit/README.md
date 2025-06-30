# LightRAG Streamlit UI

This Streamlit application offers a simple interface to interact with the LightRAG backend. It mirrors the main features of the React based `lightrag_webui` including:

- Performing RAG queries with all available modes (`local`, `global`, `hybrid`, `naive`, `mix`, `bypass`, `analyste`, `deepsearch`).
- Streaming responses from the `/query/stream` endpoint.
- Uploading and scanning documents.
- Viewing the knowledge graph.

Run the app with:

```bash
streamlit run lightrag_streamlit/app.py
```

Set the `BACKEND_URL` environment variable if the LightRAG API is not running on `http://localhost:8000`.
