import json
import logging
import re
import os
import google.generativeai as genai

from collections.abc import AsyncIterable
from typing import Any, Dict

# from common import AgentRunner, BaseAgent, init_api_key
from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, SseServerParams
from google.genai import types as genai_types
from a2a.types import AgentCard, AgentSkill, AgentCapabilities


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

# MCP Toolset Configuration
mcp_host = os.getenv("MCP_SERVER_HOST", "ob-mcp-server")
mcp_port = int(os.getenv("MCP_SERVER_PORT", 8080))
mcp_path = os.getenv("MCP_SERVER_PATH", "/sse")
full_mcp_sse_url = f"http://{mcp_host}:{mcp_port}{mcp_path}"
logger.info(f"Configuring MCPToolset URL: {full_mcp_sse_url}")

# GOOGLE GEMINI API KEY
api_key = os.getenv("GOOGLE_API_KEY", "AIzaSyCv39vGzFZUHrida4TM9xV5RKN33zEVZ8A")
genai.configure(api_key=api_key)

connection_params = SseServerParams(
    url=full_mcp_sse_url,
    headers={'Accept': 'text/event-stream'}  # Standard for SSE
)

logger.info(f"Attempting to get tools using MCPToolset.from_server with URL: {full_mcp_sse_url}")
tools = MCPToolset(
    connection_params=connection_params
)

generate_content_config = genai_types.GenerateContentConfig(
    temperature=0.0
)
root_agent = Agent(
    name="cart_monitoring_Agent",
    instruction="You are a cart monitoring agent. Use the monitor_carts tool from the cart-watcher MCP to monitor for abandoned carts and handle related tasks.",
    model='gemini-2.0-flash',
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
    generate_content_config=generate_content_config,
    tools=[tools]
)

logger.info(f"ADK Agent '{root_agent.name}' created and configured with OB MCP Toolset. "
            f"The toolset will connect to {full_mcp_sse_url} to fetch tool schemas.")
