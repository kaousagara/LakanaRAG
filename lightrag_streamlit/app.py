import os
import json
import requests
import streamlit as st
from typing import List, Dict

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# --- Helper functions -------------------------------------------------------

def get_headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = st.session_state.get("api_key")
    token = st.session_state.get("token")
    if api_key:
        headers["X-API-Key"] = api_key
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def post_json(path: str, data: Dict) -> Dict:
    url = f"{BACKEND_URL}{path}"
    r = requests.post(url, headers=get_headers(), json=data)
    r.raise_for_status()
    return r.json()


def get_json(path: str) -> Dict:
    url = f"{BACKEND_URL}{path}"
    r = requests.get(url, headers=get_headers())
    r.raise_for_status()
    return r.json()


# --- Sidebar ---------------------------------------------------------------

st.sidebar.title("LightRAG")

if "api_key" not in st.session_state:
    st.session_state.api_key = ""
if "token" not in st.session_state:
    st.session_state.token = ""

st.sidebar.text_input("API Key", key="api_key")

with st.sidebar.expander("Login", expanded=False):
    user = st.text_input("Username")
    pwd = st.text_input("Password", type="password")
    if st.button("Login"):
        try:
            r = requests.post(f"{BACKEND_URL}/login", data={"username": user, "password": pwd})
            r.raise_for_status()
            data = r.json()
            st.session_state.token = data.get("access_token", "")
            st.success("Logged in")
        except Exception as e:
            st.error(str(e))

page = st.sidebar.selectbox("Page", ["Chat", "Documents", "Graph"])


# --- Chat Page -------------------------------------------------------------

if page == "Chat":
    st.header("Chat with LightRAG")
    if "messages" not in st.session_state:
        st.session_state.messages = []  # type: List[Dict[str, str]]

    mode = st.selectbox(
        "Mode",
        ["naive", "local", "global", "hybrid", "mix", "bypass", "analyste", "deepsearch"],
        index=3,
    )
    query = st.text_area("Your question")
    stream = st.checkbox("Stream", value=True)
    if st.button("Send") and query.strip():
        param = {
            "query": query,
            "mode": mode,
            "stream": stream,
        }
        st.session_state.messages.append({"role": "user", "content": query})
        placeholder = st.empty()
        collected = ""
        try:
            if stream:
                url = f"{BACKEND_URL}/query/stream"
                with requests.post(url, headers=get_headers(), json=param, stream=True) as r:
                    r.raise_for_status()
                    for line in r.iter_lines():
                        if line:
                            try:
                                data = json.loads(line.decode("utf-8"))
                                chunk = data.get("response", "")
                                collected += chunk
                                placeholder.markdown(collected)
                            except Exception:
                                pass
                st.session_state.messages.append({"role": "assistant", "content": collected})
            else:
                resp = post_json("/query", param)
                st.session_state.messages.append({"role": "assistant", "content": resp.get("response", "")})
        except Exception as e:
            st.error(str(e))

    # Show history
    for m in st.session_state.messages:
        if m["role"] == "user":
            st.markdown(f"**User:** {m['content']}")
        else:
            st.markdown(f"**Assistant:** {m['content']}")


# --- Document Management Page ---------------------------------------------

elif page == "Documents":
    st.header("Documents")
    cols = st.columns(3)
    with cols[0]:
        if st.button("Refresh List"):
            st.session_state.docs = get_json("/documents")
    with cols[1]:
        if st.button("Scan New"):
            try:
                post_json("/documents/scan", {})
                st.success("Scan started")
            except Exception as e:
                st.error(str(e))
    with cols[2]:
        if st.button("Clear All"):
            try:
                requests.delete(f"{BACKEND_URL}/documents", headers=get_headers()).raise_for_status()
                st.success("Documents cleared")
            except Exception as e:
                st.error(str(e))

    uploaded = st.file_uploader("Upload documents", accept_multiple_files=True)
    if uploaded:
        files = [(f.name, f.getvalue()) for f in uploaded]
        multi = []
        for name, data in files:
            multi.append(("files", (name, data)))
        try:
            url = f"{BACKEND_URL}/documents/batch"
            r = requests.post(url, headers=get_headers(), files=multi)
            r.raise_for_status()
            st.success("Uploaded")
        except Exception as e:
            st.error(str(e))

    docs = st.session_state.get("docs")
    if not docs:
        st.write("No document data. Click refresh.")
    else:
        for status, items in docs.get("statuses", {}).items():
            st.subheader(status.capitalize())
            for doc in items:
                st.write(f"{doc['id']} - {doc.get('file_path','')} - {doc['status']}")


# --- Graph Viewer Page ----------------------------------------------------

else:  # Graph
    st.header("Knowledge Graph")
    labels = get_json("/graph/label/list")
    label = st.selectbox("Label", labels)
    depth = st.number_input("Max Depth", 1, 5, 2)
    max_nodes = st.number_input("Max Nodes", 10, 500, 100)
    if st.button("Load Graph"):
        try:
            graph = get_json(f"/graphs?label={label}&max_depth={depth}&max_nodes={max_nodes}")
            import networkx as nx
            from pyvis.network import Network

            G = nx.DiGraph()
            for node in graph.get("nodes", []):
                G.add_node(node["id"], label="\n".join(node.get("labels", [])))
            for edge in graph.get("edges", []):
                G.add_edge(edge["source"], edge["target"], label=edge.get("type", ""))
            net = Network(height="600px", width="100%", directed=True)
            net.from_nx(G)
            net_html = net.generate_html(notebook=False)
            st.components.v1.html(net_html, height=600, scrolling=True)
        except Exception as e:
            st.error(str(e))
