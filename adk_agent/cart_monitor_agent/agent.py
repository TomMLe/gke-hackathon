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
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, SseServerParams
from google.genai import types as genai_types

# Your AgentCard (should already exist)
from a2a.types import AgentCard, AgentSkill, AgentCapabilities

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

    base_toolset = MCPToolset(connection_params=SseServerParams(url=MCP_SSE_URL))

    async def filtered_tools(readonly_context=None):
        tools = await base_toolset.get_tools(readonly_context)
        return [t for t in tools if getattr(t, "name", "").startswith("cart_")]

    class FilteredMcpToolset(MCPToolset):
        async def get_tools(self, readonly_context=None):
            return await filtered_tools(readonly_context)

    toolset_for_agent = FilteredMcpToolset(connection_params=SseServerParams(url=MCP_SSE_URL))

    agent = LlmAgent(
        name="cart_monitor_agent",
        model=MODEL_ID,
        description=agent_card.description,
        instruction=(
            "You are cart_monitor_agent. "
            f"{agent_card.description}\n"
            "Monitor carts, detect anomalies, trigger alerts, and propose interventions."
        ),
        tools=[toolset_for_agent],
    )

    _runner = runner.Runner(app_name="cart_monitor_agent", agent=agent, session_service=session_service)
    return _runner

def _map_a2a_msgs_to_content(messages: List[A2AMessage]) -> genai_types.Content:
    parts: List[genai_types.Part] = []
    for m in messages:
        prefix = "SYSTEM: " if m.role == "system" else ""
        parts.append(genai_types.Part.from_text(f"{prefix}{m.content}"))
    return genai_types.Content(parts=parts)

@app.post("/a2a", response_model=A2AResponse)
async def a2a_endpoint(payload: A2ARequest):
    r = await _ensure_runner()
    content = _map_a2a_msgs_to_content(payload.messages)

    final_text: Optional[str] = None
    async for event in r.run(
        user_id="host_orchestrator",
        session_id="cart_monitor_agent_session",
        request=content,
    ):
        if event.type == "agent_output":
            try:
                final_text = "".join(
                    (p.text or "") for p in (event.output.parts or []) if hasattr(p, "text")
                ).strip() or final_text
            except Exception:
                pass

    if not final_text:
        final_text = "⚠️ cart_monitor_agent produced no text."

    return A2AResponse(
        messages=[A2AMessage(role="assistant", content=final_text)],
        output=final_text
    )

if __name__ == "__main__":
    uvicorn.run("agent:app", host="0.0.0.0", port=SERVE_PORT)