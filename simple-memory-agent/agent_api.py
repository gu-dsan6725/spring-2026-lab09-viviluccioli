"""FastAPI wrapper for the memory-enabled agent."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent import Agent


logger = logging.getLogger(__name__)

app = FastAPI(
    title="Memory Agent API",
    description="Multi-tenant conversational agent with semantic memory",
    version="1.0.0",
)


class InvocationRequest(BaseModel):
    """Request payload for a memory-agent invocation."""

    user_id: str = Field(..., description="User identifier for memory isolation")
    query: str = Field(..., description="User message")
    run_id: Optional[str] = Field(
        default=None,
        description="Session identifier. If omitted, a new session id is generated.",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional metadata for request context",
    )


class InvocationResponse(BaseModel):
    """Response payload for a memory-agent invocation."""

    user_id: str
    run_id: str
    response: str
    metadata: Optional[Dict[str, Any]] = None


_session_cache: Dict[str, Agent] = {}
_session_users: Dict[str, str] = {}


def _resolve_api_key() -> Optional[str]:
    """Resolve any configured LLM provider API key."""
    return (
        os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("GROQ_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("GEMINI_API_KEY")
    )


def _get_or_create_agent(user_id: str, run_id: str) -> Agent:
    """Return the cached agent for a session or create a new one."""
    if run_id in _session_cache:
        cached_user_id = _session_users[run_id]
        if cached_user_id != user_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"run_id '{run_id}' is already associated with user_id "
                    f"'{cached_user_id}'"
                ),
            )
        return _session_cache[run_id]

    agent = Agent(
        user_id=user_id,
        run_id=run_id,
        api_key=_resolve_api_key(),
    )
    _session_cache[run_id] = agent
    _session_users[run_id] = user_id
    return agent


@app.get("/ping")
def ping() -> Dict[str, str]:
    """Health-check endpoint."""
    return {
        "status": "ok",
        "message": "Memory Agent API is running",
    }


@app.post("/invocation", response_model=InvocationResponse)
def invocation(payload: InvocationRequest) -> InvocationResponse:
    """Process a user message with a session-scoped memory agent."""
    run_id = payload.run_id or str(uuid.uuid4())[:8]

    try:
        agent = _get_or_create_agent(payload.user_id, run_id)
        response_text = agent.chat(payload.query)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Invocation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return InvocationResponse(
        user_id=payload.user_id,
        run_id=run_id,
        response=response_text,
        metadata=payload.metadata,
    )
