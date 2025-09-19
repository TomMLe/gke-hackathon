import os
import logging

from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, SseServerParams
from google.genai import types as genai_types
import google.generativeai as genai
from typing import Dict, Any, Optional
import httpx
import time
import json
import uuid

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

def delegate_to_agent(peer: str, input_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Delegate a task to a peer agent via A2A HTTP call."""
    if input_data is None:
        input_data = {}
    peer_urls = {
        "cart_monitor_agent": "http://cart-monitor-agent:10102/",
        "recommend_agent": "http://recommend-agent:10103/"
    }
    url = peer_urls.get(peer)
    if not url:
        raise ValueError(f"Unknown peer: {peer}")
    
    # Build ADK message schema for A2A 'message/send'
    message_obj = None
    if isinstance(input_data, dict) and input_data.get("message"):
        # Already in ADK message format
        message_obj = input_data["message"]
    else:
        # Derive a reasonable user message from input_data or defaults
        text = None
        if isinstance(input_data, dict):
            text = input_data.get("text") or input_data.get("prompt")
            if not text:
                if peer == "cart_monitor_agent":
                    text = "monitor abandoned carts"
                else:
                    # For other peers (e.g., recommend_agent), pass structured JSON as text so the agent can parse it
                    text = json.dumps(input_data) if input_data else "proceed"
        message_obj = {"role": "user", "parts": [{"text": str(text)}]}
    # Ensure required messageId for A2A JSON-RPC
    if isinstance(message_obj, dict) and "messageId" not in message_obj:
        message_obj["messageId"] = str(uuid.uuid4())
    # Attach a sessionId and unique request id to satisfy A2A schema expectations
    session_id = os.getenv("A2A_SESSION_ID") or str(uuid.uuid4())
    payload = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "params": {"message": message_obj, "sessionId": session_id},
        "id": str(uuid.uuid4())
    }
    
    # Default ADK JSON-RPC message path; for cart_monitor_agent we will poll task state after sending.
    full_url = url
    body = payload

    logger.info(f"Delegating to {peer} endpoint {full_url} with body: {body}")
    try:
        # 1) Kick off work via JSON-RPC message/send (returns ACK)
        response = httpx.post(full_url, json=body, timeout=30.0)
        response.raise_for_status()
        ack_json = response.json()
        logger.info(f"A2A ACK from {peer}: {ack_json}")

        # 2) For cart_monitor_agent, simply return the ACK payload. The service already responds synchronously.
        if peer == "cart_monitor_agent":
            return ack_json.get("result") or ack_json

        # 3) Other peers: return the ACK or result if present
        result = ack_json.get("result", {}) or ack_json
        return result
    except Exception as e:
        logger.error(f"Delegation to {peer} failed: {str(e)}")
        raise

root_agent = Agent(
    name="orchestrator_agent",
    instruction="You are an orchestrator agent for abandoned cart handling. ALWAYS delegate using the delegate_to_agent tool: first to 'cart_monitor_agent' to get abandoned carts. When delegating to 'cart_monitor_agent', include the end-user request text in input_data.text so the agent can curate results accordingly (e.g., 'monitor abandoned carts with fashion items'). Then use its output (abandoned_carts with user_id and items) to delegate to 'recommend_agent' with dynamic input_data like {'user_id': user_id, 'product_ids': [ids from items]}. Chain calls and log steps.",
    model='gemini-2.0-flash',
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=False,
    generate_content_config=generate_content_config,
    tools=[delegate_to_agent]  # Disable MCP tools, use custom delegation
)

logger.info(f"ADK Orchestrator Agent '{root_agent.name}' created and configured.")
