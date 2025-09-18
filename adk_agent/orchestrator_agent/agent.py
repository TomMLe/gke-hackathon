import os
import logging

from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, SseServerParams
from google.genai import types as genai_types
import google.generativeai as genai
from typing import Dict, Any
import httpx

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

def delegate_to_agent(peer: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Delegate a task to a peer agent via A2A HTTP call."""
    peer_urls = {
        "cart_monitor_agent": "http://cart-monitor-agent:10102/tasks",
        "recommend_agent": "http://recommend-agent:10103/tasks"
    }
    url = peer_urls.get(peer)
    if not url:
        raise ValueError(f"Unknown peer: {peer}")
    
    logger.info(f"Delegating to {peer} with input: {input_data}")
    try:
        response = httpx.post(url, json=input_data, timeout=30.0)
        response.raise_for_status()
        result = response.json()
        logger.info(f"Delegation response from {peer}: {result}")
        return result
    except Exception as e:
        logger.error(f"Delegation to {peer} failed: {str(e)}")
        raise

root_agent = Agent(
    name="orchestrator_agent",
    instruction="You are an orchestrator agent for abandoned cart handling. ALWAYS delegate using the delegate_to_agent tool: first to 'cart_monitor_agent' for monitoring, then to 'recommend_agent' for recommendations. Do NOT use MCP tools directly. Log all steps.",
    model='gemini-2.0-flash',
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=False,
    generate_content_config=generate_content_config,
    tools=[delegate_to_agent]  # Disable MCP tools, use custom delegation
)

logger.info(f"ADK Orchestrator Agent '{root_agent.name}' created and configured.")
