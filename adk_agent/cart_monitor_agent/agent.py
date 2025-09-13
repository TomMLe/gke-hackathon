import json
import logging
import re
import os

from collections.abc import AsyncIterable
from typing import Any, Dict

# from common import AgentRunner, BaseAgent, init_api_key
from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, SseServerParams
from google.genai import types as genai_types


logger = logging.getLogger(__name__)

# MCP Toolset Configuration
mcp_host = os.getenv("MCP_SERVER_HOST", "ob-mcp-server")
mcp_port = int(os.getenv("MCP_SERVER_PORT", 8080))
mcp_path = os.getenv("MCP_SERVER_PATH", "/sse")
full_mcp_sse_url = f"http://{mcp_host}:{mcp_port}{mcp_path}"
logger.info(f"Configuring MCPToolset URL: {full_mcp_sse_url}")

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
    instruction="You are a cart monitoring agent, specifically for fashion items. Only look for carts with fashion items in it. For example: shoes, sunglasses, etc. Carts have other items, but only look for carts with fashion items Use the monitor_carts tool from the cart-watcher MCP to monitor for abandoned carts and handle related tasks.",
    model='gemini-2.0-flash',
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
    generate_content_config=generate_content_config,
    tools=[tools]
)

logger.info(f"ADK Agent '{root_agent.name}' created and configured with OB MCP Toolset. "
            f"The toolset will connect to {full_mcp_sse_url} to fetch tool schemas.")
