import os
import logging

from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, SseServerParams
from google.genai import types as genai_types
import google.generativeai as genai

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger(__name__)

# API Key Initialization
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY is not set")
genai.configure(api_key=api_key)

# MCP Toolset Configuration (optional for orchestrator, but included for consistency)
mcp_host = os.getenv("MCP_SERVER_HOST", "ob-mcp-server")
mcp_port = int(os.getenv("MCP_SERVER_PORT", 8080))
mcp_path = os.getenv("MCP_SERVER_PATH", "/sse")
full_mcp_sse_url = f"http://{mcp_host}:{mcp_port}{mcp_path}"
logger.info(f"Configuring MCPToolset URL: {full_mcp_sse_url}")

connection_params = SseServerParams(
    url=full_mcp_sse_url,
    headers={'Accept': 'text/event-stream'}
)

toolset = MCPToolset(connection_params=connection_params)
logger.info("MCPToolset initialized for orchestrator.")

generate_content_config = genai_types.GenerateContentConfig(
    temperature=0.0
)

root_agent = Agent(
    name="orchestrator_agent",
    instruction="You are an orchestrator agent for abandoned cart handling. Monitor for abandoned fashion carts by delegating to cart_monitor_agent, then suggest recommendations by delegating to recommend_agent. Coordinate the workflow and provide final suggestions.",
    model='gemini-2.0-flash',
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=False,  # Allow transfer to peer agents
    generate_content_config=generate_content_config,
    tools=[toolset]
)

logger.info(f"ADK Orchestrator Agent '{root_agent.name}' created and configured.")
