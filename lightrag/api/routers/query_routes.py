"""
This module contains all query-related routes for the LightRAG API.
"""

import json
import logging
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from lightrag.base import QueryParam
from lightrag.user_profile import (
    load_user_profile,
    update_user_profile,
    record_feedback,
    get_conversation_history,
    append_conversation_history,
    record_branch_feedback,
    auto_tag_entities,
    analyze_behavior,
    revert_user_profile,
)
from ..utils_api import get_combined_auth_dependency
from pydantic import BaseModel, Field, field_validator

from ascii_colors import trace_exception

router = APIRouter(tags=["query"])


class QueryRequest(BaseModel):
    query: str = Field(
        min_length=1,
        description="The query text",
    )

    mode: Literal[
        "local",
        "global",
        "hybrid",
        "naive",
        "mix",
        "bypass",
        "analyste",
        "deepsearch",
    ] = Field(
        default="hybrid",
        description="Query mode",
    )

    only_need_context: Optional[bool] = Field(
        default=None,
        description="If True, only returns the retrieved context without generating a response.",
    )

    only_need_prompt: Optional[bool] = Field(
        default=None,
        description="If True, only returns the generated prompt without producing a response.",
    )

    response_type: Optional[str] = Field(
        min_length=1,
        default=None,
        description="Defines the response format. Examples: 'Multiple Paragraphs', 'Single Paragraph', 'Bullet Points'.",
    )

    top_k: Optional[int] = Field(
        ge=1,
        default=None,
        description="Number of top items to retrieve. Represents entities in 'local' mode and relationships in 'global' mode.",
    )

    max_token_for_text_unit: Optional[int] = Field(
        gt=1,
        default=None,
        description="Maximum number of tokens allowed for each retrieved text chunk.",
    )

    max_token_for_global_context: Optional[int] = Field(
        gt=1,
        default=None,
        description="Maximum number of tokens allocated for relationship descriptions in global retrieval.",
    )

    max_token_for_local_context: Optional[int] = Field(
        gt=1,
        default=None,
        description="Maximum number of tokens allocated for entity descriptions in local retrieval.",
    )

    conversation_history: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Stores past conversation history to maintain context. Format: [{'role': 'user/assistant', 'content': 'message'}].",
    )

    history_turns: Optional[int] = Field(
        ge=0,
        default=None,
        description="Number of complete conversation turns (user-assistant pairs) to consider in the response context.",
    )

    ids: list[str] | None = Field(
        default=None, description="List of ids to filter the results."
    )

    user_prompt: Optional[str] = Field(
        default=None,
        description="User-provided prompt for the query. If provided, this will be used instead of the default value from prompt template.",
    )

    user_profile: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Profile information about the user issuing the query.",
    )

    user_id: Optional[str] = Field(
        default=None,
        description="Identifier used to load and persist the user profile.",
    )

    conversation_id: Optional[str] = Field(
        default=None,
        description="Identifier of the conversation used to store history.",
    )

    def to_query_params(self, is_stream: bool) -> "QueryParam":
        """Convert this model into a :class:`QueryParam`."""
        request_data = self.model_dump(exclude_none=True, exclude={"query"})
        param = QueryParam(**request_data)
        param.stream = is_stream
        return param


class FeedbackRequest(BaseModel):
    user_id: str = Field(..., description="Identifier of the user")
    query: str = Field(..., description="Original query")
    response: str = Field(..., description="System response")
    rating: Literal["positive", "negative"] = Field(
        ..., description="Explicit user rating"
    )
    notes: Optional[str] = Field(
        default=None, description="Optional feedback notes from the user"
    )

    @field_validator("query", mode="after")
    @classmethod
    def query_strip_after(cls, query: str) -> str:
        return query.strip()


class BranchFeedbackRequest(BaseModel):
    user_id: str = Field(..., description="Identifier of the user")
    branch: List[str] = Field(..., description="Tree of Thought branch path")
    rating: Literal["positive", "negative"] = Field(
        ..., description="User rating for this branch"
    )
    notes: Optional[str] = Field(default=None, description="Optional notes")


class TagEntitiesRequest(BaseModel):
    user_id: str = Field(..., description="Identifier of the user")
    entities: List[str] = Field(..., description="Entities to tag as corrected")


class QueryResponse(BaseModel):
    response: str = Field(
        description="The generated response",
    )


def create_query_routes(rag, api_key: Optional[str] = None, top_k: int = 60):
    combined_auth = get_combined_auth_dependency(api_key)

    @router.post(
        "/query", response_model=QueryResponse, dependencies=[Depends(combined_auth)]
    )
    async def query_text(request: QueryRequest):
        """
        Handle a POST request at the /query endpoint to process user queries using RAG capabilities.

        Parameters:
            request (QueryRequest): The request object containing the query parameters.
        Returns:
            QueryResponse: A Pydantic model containing the result of the query processing.
                       If a string is returned (e.g., cache hit), it's directly returned.
                       Otherwise, an async generator may be used to build the response.

        Raises:
            HTTPException: Raised when an error occurs during the request handling process,
                       with status code 500 and detail containing the exception message.
        """
        try:
            param = request.to_query_params(False)
            if request.user_id:
                if request.user_profile is not None:
                    param.user_profile = update_user_profile(
                        request.user_id, request.user_profile
                    )
                else:
                    param.user_profile = load_user_profile(request.user_id)
                param.user_id = request.user_id
                param.conversation_id = request.conversation_id
                if request.conversation_history is None and request.conversation_id:
                    param.conversation_history = get_conversation_history(
                        request.user_id, request.conversation_id
                    )
            if request.user_profile and not request.user_id:
                param.user_profile = request.user_profile
            if request.conversation_history and not param.conversation_history:
                param.conversation_history = request.conversation_history

            response = await rag.aquery(request.query, param=param)

            if request.user_id:
                if isinstance(response, str):
                    resp_text = response
                elif isinstance(response, dict):
                    resp_text = json.dumps(response, indent=2)
                else:
                    resp_text = str(response)
                if request.conversation_id:
                    append_conversation_history(
                        request.user_id,
                        request.conversation_id,
                        [
                            {"role": "user", "content": request.query},
                            {"role": "assistant", "content": resp_text},
                        ],
                    )

            # If response is a string (e.g. cache hit), return directly
            if isinstance(response, str):
                return QueryResponse(response=response)

            if isinstance(response, dict):
                result = json.dumps(response, indent=2)
                return QueryResponse(response=result)
            else:
                return QueryResponse(response=str(response))
        except Exception as e:
            trace_exception(e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/feedback", dependencies=[Depends(combined_auth)])
    async def submit_feedback(request: FeedbackRequest):
        """Record explicit user feedback for a query response."""
        try:
            record_feedback(
                request.user_id,
                request.query,
                request.response,
                request.rating,
                request.notes,
            )
            return {"status": "success"}
        except Exception as e:
            trace_exception(e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/branch-feedback", dependencies=[Depends(combined_auth)])
    async def submit_branch_feedback(request: BranchFeedbackRequest):
        """Record user feedback for a specific Tree of Thought branch."""
        try:
            record_branch_feedback(
                request.user_id,
                request.branch,
                request.rating,
                request.notes,
            )
            return {"status": "success"}
        except Exception as e:
            trace_exception(e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/entities/tag", dependencies=[Depends(combined_auth)])
    async def tag_entities(request: TagEntitiesRequest):
        """Auto-tag entities corrected by the user."""
        try:
            auto_tag_entities(request.user_id, request.entities)
            return {"status": "success"}
        except Exception as e:
            trace_exception(e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/profile/{user_id}/revert", dependencies=[Depends(combined_auth)])
    async def profile_revert(user_id: str, version: int):
        """Revert the user profile to a previous version."""
        try:
            return revert_user_profile(user_id, version)
        except Exception as e:
            trace_exception(e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/profile/{user_id}/analysis", dependencies=[Depends(combined_auth)])
    async def profile_analysis(user_id: str):
        """Return simple behavioural analysis for a user."""
        try:
            return analyze_behavior(user_id)
        except Exception as e:
            trace_exception(e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/query/stream", dependencies=[Depends(combined_auth)])
    async def query_text_stream(request: QueryRequest):
        """
        This endpoint performs a retrieval-augmented generation (RAG) query and streams the response.

        Args:
            request (QueryRequest): The request object containing the query parameters.
            optional_api_key (Optional[str], optional): An optional API key for authentication. Defaults to None.

        Returns:
            StreamingResponse: A streaming response containing the RAG query results.
        """
        try:
            param = request.to_query_params(True)
            if request.user_id:
                if request.user_profile is not None:
                    param.user_profile = update_user_profile(
                        request.user_id, request.user_profile
                    )
                else:
                    param.user_profile = load_user_profile(request.user_id)
                param.user_id = request.user_id
                param.conversation_id = request.conversation_id
                if request.conversation_history is None and request.conversation_id:
                    param.conversation_history = get_conversation_history(
                        request.user_id, request.conversation_id
                    )
            if request.user_profile and not request.user_id:
                param.user_profile = request.user_profile
            if request.conversation_history and not param.conversation_history:
                param.conversation_history = request.conversation_history

            response = await rag.aquery(request.query, param=param)

            from fastapi.responses import StreamingResponse

            async def stream_generator():
                if isinstance(response, str):
                    if request.user_id and request.conversation_id:
                        append_conversation_history(
                            request.user_id,
                            request.conversation_id,
                            [
                                {"role": "user", "content": request.query},
                                {"role": "assistant", "content": response},
                            ],
                        )
                    yield f"{json.dumps({'response': response})}\n"
                else:
                    collected: list[str] = []
                    try:
                        async for chunk in response:
                            if chunk:
                                collected.append(str(chunk))
                                yield f"{json.dumps({'response': chunk})}\n"
                    except Exception as e:
                        logging.error(f"Streaming error: {str(e)}")
                        yield f"{json.dumps({'error': str(e)})}\n"
                    finally:
                        if request.user_id and request.conversation_id:
                            append_conversation_history(
                                request.user_id,
                                request.conversation_id,
                                [
                                    {"role": "user", "content": request.query},
                                    {
                                        "role": "assistant",
                                        "content": "".join(collected),
                                    },
                                ],
                            )

            return StreamingResponse(
                stream_generator(),
                media_type="application/x-ndjson",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Content-Type": "application/x-ndjson",
                    "X-Accel-Buffering": "no",  # Ensure proper handling of streaming response when proxied by Nginx
                },
            )
        except Exception as e:
            trace_exception(e)
            raise HTTPException(status_code=500, detail=str(e))

    return router
