# import json
# import logging
# import re
# import os
# import google.generativeai as genai

# from collections.abc import AsyncIterable
# from typing import Any, Dict

# # from common import AgentRunner, BaseAgent, init_api_key
# from google.adk.agents import Agent
# from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, SseServerParams
# from google.genai import types as genai_types
# from a2a.types import AgentCard, AgentSkill, AgentCapabilities


# logger = logging.getLogger(__name__)

# # MCP Toolset Configuration
# mcp_host = os.getenv("MCP_SERVER_HOST", "ob-mcp-server")
# mcp_port = int(os.getenv("MCP_SERVER_PORT", 8080))
# mcp_path = os.getenv("MCP_SERVER_PATH", "/sse")
# full_mcp_sse_url = f"http://{mcp_host}:{mcp_port}{mcp_path}"
# logger.info(f"Configuring MCPToolset URL: {full_mcp_sse_url}")

# # GOOGLE GEMINI API KEY
# api_key = os.getenv("GOOGLE_API_KEY", "AIzaSyCv39vGzFZUHrida4TM9xV5RKN33zEVZ8A")
# genai.configure(api_key=api_key)

# connection_params = SseServerParams(
#     url=full_mcp_sse_url,
#     headers={'Accept': 'text/event-stream'}  # Standard for SSE
# )

# logger.info(f"Attempting to get tools using MCPToolset.from_server with URL: {full_mcp_sse_url}")
# tools = MCPToolset(
#     connection_params=connection_params
# )

# generate_content_config = genai_types.GenerateContentConfig(
#     temperature=0.0
# )
# root_agent = Agent(
#     name="cart_monitoring_Agent",
#     instruction="You are a cart monitoring agent. Use the monitor_carts tool from the cart-watcher MCP to monitor for abandoned carts and handle related tasks.",
#     model='gemini-2.0-flash',
#     disallow_transfer_to_parent=True,
#     disallow_transfer_to_peers=True,
#     generate_content_config=generate_content_config,
#     tools=[tools]
# )

# logger.info(f"ADK Agent '{root_agent.name}' created and configured with OB MCP Toolset. "
#             f"The toolset will connect to {full_mcp_sse_url} to fetch tool schemas.")

# server.py (cart_monitor_agent using Google ADK + MCPToolset)
import os
from typing import List, Optional, Literal
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
import uvicorn
import asyncio

# --- ADK + MCP ---
from google.adk.agents import LlmAgent
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import SseConnectionParams
from google.genai import types as genai_types

# Your AgentCard (should already exist)
from a2a.types import AgentCard, AgentSkill, AgentCapabilities

from typing import Iterable, AsyncIterable
import logging

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger(__name__)

def get_agent_card() -> AgentCard:
    capabilities = AgentCapabilities(streaming=False, pushNotifications=False)
    return AgentCard(
        id="cart_monitor_agent",
        name="Cart Monitor Agent",
        description="Detects abandoned carts",
        version="1.0.0",
        url="local",  # or use dummy string if running locally
        capabilities=capabilities,
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        skills=[
            AgentSkill(
                id="monitor_carts",
                name= "Monitor Abandoned Carts",
                description="Detects abandoned carts",
                tags=[
                    "Cart monitoring"
                ],
                examples=[
                    "Check for abandoned carts with home decor items",
                    "Monitor abandoned carts with fashion items"
                ],
            )
        ]
    )
Role = Literal["system", "user", "assistant", "human", "ai"]

class A2AMessage(BaseModel):
    role: Role
    content: str

class A2ARequest(BaseModel):
    messages: List[A2AMessage] = Field(default_factory=list)
    metadata: Optional[dict] = None

class A2AResponse(BaseModel):
    messages: List[A2AMessage]
    output: str

def _latest_user_text(messages: list[A2AMessage]) -> str:
    for m in reversed(messages or []):
        if (m.role or "user").lower() in ("user", "human"):
            return m.content
    return (messages[-1].content if messages else "").strip()

def _content_from_text(text: str) -> genai_types.Content:
    return genai_types.Content(
        role="user",
        parts=[genai_types.Part.from_text(text=text)]  # keyword arg is required
    )

MODEL_ID = os.getenv("CART_MONITOR_AGENT_MODEL", "gemini-2.0-flash")
MCP_HOST = os.getenv("MCP_SERVER_HOST", "ob-mcp-server")
MCP_PORT = int(os.getenv("MCP_SERVER_PORT", "8080"))
MCP_PATH = os.getenv("MCP_SERVER_PATH", "/sse")
MCP_SSE_URL = f"http://{MCP_HOST}:{MCP_PORT}{MCP_PATH}"
SERVE_PORT = int(os.getenv("PORT", "10102"))

app = FastAPI(title="cart_monitor_agent (ADK peer)")
agent_card: AgentCard = get_agent_card()
session_service = InMemorySessionService()
_runner: Optional[Runner] = None

async def _ensure_runner() -> Runner:
    global _runner
    if _runner:
        return _runner

    connection_params = SseConnectionParams(
        url=MCP_SSE_URL,
        headers={'Accept': 'text/event-stream'}
    )

    base_toolset = MCPToolset(connection_params=connection_params)

    # DEBUG: show discovered tools
    try:
        tools = await base_toolset.get_tools()
        names = [getattr(t, "name", "?") for t in tools]
        logger.info("MCP tools (%d): %s", len(names), names)
    except Exception:
        logger.exception("get_tools() failed")
        tools = []

    agent = LlmAgent(
        name="cart_monitor_agent",
        model=MODEL_ID,
        description=agent_card.description,
        instruction=(
            "You are cart_monitor_agent. "
            f"{agent_card.description}\n"
            "Monitor abandoned carts with certain category of items. ALWAYS Use the MCP tools given to you"
            "Format your answer as concise Markdown. Use bullet lists for items; if you return structured data, wrap valid JSON in ```json code fences."
        ),
        tools=tools,
    )

    _runner = Runner(app_name="cart_monitor_agent", agent=agent, session_service=session_service)
    # Ensure the default session exists (works with sync OR async session services)
    await session_service.create_session(
        app_name="cart_monitor_agent",
        user_id="host_orchestrator",
        session_id="cart_monitor_agent_session",
    )
    return _runner

def _map_a2a_msgs_to_content(messages: List[A2AMessage]) -> genai_types.Content:
    # Flatten the conversation into a single user message
    lines = []
    for m in messages:
        r = (m.role or "user").lower()
        if r == "system":
            lines.append(f"[SYSTEM] {m.content}")
        elif r in ("assistant", "ai"):
            lines.append(f"Assistant: {m.content}")
        else:
            lines.append(m.content)
    text = "\n".join(lines).strip()
    return genai_types.Content(
        role="user",
        parts=[genai_types.Part.from_text(text=text)]  # ✅ keyword arg, single Part
    )

def _debug_event(evt):
    et = getattr(evt, "type", "")
    tn = getattr(evt, "tool_name", None)
    if et.startswith("tool") or tn:
        logger.info("EVENT %s tool=%s", et, tn)

def _take_text_from_event(evt) -> str:
    # 1) common direct fields
    for attr in ("output_text", "text"):
        val = getattr(evt, attr, None)
        if isinstance(val, str) and val.strip():
            return val.strip()

    # 2) common containers
    for container_attr in ("output", "message", "response", "content"):  # <— added "content"
        out = getattr(evt, container_attr, None)
        if not out:
            continue

        # 2a) direct .text on the container
        val = getattr(out, "text", None)
        if isinstance(val, str) and val.strip():
            return val.strip()

        # 2b) parts on the container
        parts = getattr(out, "parts", None)
        if parts:
            try:
                txt = "".join((getattr(p, "text", "") or "") for p in parts if hasattr(p, "text"))
                if txt.strip():
                    return txt.strip()
            except Exception:
                pass

        # 2c) gemini-style candidates -> content.parts
        candidates = getattr(out, "candidates", None)
        if candidates:
            for c in candidates:
                content = getattr(c, "content", None)
                if content and getattr(content, "parts", None):
                    try:
                        txt = "".join((getattr(p, "text", "") or "") for p in content.parts if hasattr(p, "text"))
                        if txt.strip():
                            return txt.strip()
                    except Exception:
                        pass

    # 3) last resort: nothing
    return ""

    # 1) direct strings commonly present on events
    for attr in ("output_text", "text"):
        val = getattr(evt, attr, None)
        if isinstance(val, str) and val.strip():
            return val.strip()

    # 2) common containers on events
    for container_attr in ("output", "message", "response"):
        out = getattr(evt, container_attr, None)
        if not out:
            continue

        # 2a) direct .text on the container
        val = getattr(out, "text", None)
        if isinstance(val, str) and val.strip():
            return val.strip()

        # 2b) parts on the container
        parts = getattr(out, "parts", None)
        if parts:
            try:
                txt = "".join((getattr(p, "text", "") or "") for p in parts)
                if txt.strip():
                    return txt.strip()
            except Exception:
                pass

        # 2c) Gemini-style candidates -> content.parts
        candidates = getattr(out, "candidates", None)
        if candidates:
            for c in candidates:
                content = getattr(c, "content", None)
                if content and getattr(content, "parts", None):
                    try:
                        txt = "".join((getattr(p, "text", "") or "") for p in content.parts)
                        if txt.strip():
                            return txt.strip()
                    except Exception:
                        pass

    # 3) as a last resort, stringify
    try:
        s = str(evt)
        if s and s != repr(evt):
            return s
    except Exception:
        pass
    return ""



@app.post("/a2a", response_model=A2AResponse)
async def a2a_endpoint(payload: A2ARequest):
    r = await _ensure_runner()

    # 1) send only the latest user turn (keeps models/tooling decisive)
    user_text = _latest_user_text(payload.messages).strip()
    content = _content_from_text(user_text or "Please proceed.")

    # 2) run the agent (handle both async-iterable and sync generators)
    try:
        events = getattr(r, "run_async", None)
        if callable(events):
            events = r.run_async(
                user_id="host_orchestrator",
                session_id="cart_monitor_agent_session",  # or recommend_agent_session
                new_message=content,
            )
        else:
            events = r.run(
                user_id="host_orchestrator",
                session_id="cart_monitor_agent_session",
                new_message=content,
            )
    except TypeError:
        # Some ADK builds use 'request' instead of 'new_message'
        run_fn = getattr(r, "run_async", None) or r.run
        events = run_fn(
            user_id="host_orchestrator",
            session_id="cart_monitor_agent_session",
            request=content,
        )

    chunks: list[str] = []
    final_text: str | None = None

    async def _consume_async(ait: AsyncIterable):
        nonlocal final_text
        async for evt in ait:
            _debug_event(evt)
            text = _take_text_from_event(evt)
            if text:
                if getattr(evt, "type", "") in ("agent_text_delta", "assistant_text_delta", "text_delta"):
                    chunks.append(text)
                else:
                    final_text = text

    def _consume_sync(it: Iterable):
        nonlocal final_text
        for evt in it:
            _debug_event(evt)
            text = _take_text_from_event(evt)
            if text:
                if getattr(evt, "type", "") in ("agent_text_delta", "assistant_text_delta", "text_delta"):
                    chunks.append(text)
                else:
                    final_text = text

    if hasattr(events, "__aiter__"):
        await _consume_async(events)
    else:
        _consume_sync(events)

    # 3) prefer final output; otherwise join deltas
    answer = (final_text or "".join(chunks)).strip()

    if not answer:
        answer = "⚠️ No text produced. Check ADK events and tool availability."

    return A2AResponse(
        messages=[A2AMessage(role="assistant", content=answer)],
        output=answer,
    )

if __name__ == "__main__":
    uvicorn.run("agent:app", host="0.0.0.0", port=SERVE_PORT)