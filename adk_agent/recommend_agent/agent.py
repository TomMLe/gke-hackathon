import os
import logging

from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, SseServerParams
from google.genai import types as genai_types
import google.generativeai as genai
from a2a.types import AgentCard, AgentSkill, AgentCapabilities

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger(__name__)

def get_agent_card() -> AgentCard:
    capabilities = AgentCapabilities(streaming=False, pushNotifications=False)
    return AgentCard(
        id="recommend_agent",
        name="Recommend Agent",
        description="Recommend item agent",
        version="1.0.0",
        url="local",  # or use dummy string if running locally
        capabilities=capabilities,
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        skills=[
            AgentSkill(
                id="recommend_items",
                name= "Recommend items",
                description="uggests similar items based on abandoned cart",
                tags=[
                    "Product recommendation"
                ],
                examples=[
                    "Recommend items similar to these product IDs"
                ],
            )
        ]
    )

# API Key Initialization
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY is not set")
genai.configure(api_key=api_key)

# MCP Toolset Configuration
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
logger.info("MCPToolset initialized for recommendation tools.")

generate_content_config = genai_types.GenerateContentConfig(
    temperature=0.0
)

root_agent = Agent(
    name="recommend_agent",
    instruction="You are a product recommendation agent. Use provided input_data (with user_id and product_ids) to call recommend_items tool and suggest similar products in the same categories (e.g., fashion if majority are fashion). If no input_data, use defaults.",
    model='gemini-2.0-flash',
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
    generate_content_config=generate_content_config,
    tools=[toolset]
)

logger.info(f"ADK Recommendation Agent '{root_agent.name}' created and configured.")
