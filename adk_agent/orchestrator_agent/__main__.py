import logging
import sys
import json
import os

from pathlib import Path

import click
import httpx
import uvicorn
from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryPushNotificationConfigStore, InMemoryTaskStore
from a2a.types import AgentCard
from a2a.server.agent_execution import AgentExecutor
from common.agent_executor import CustomAgentExecutor

# Import your agent class (assuming it's defined in agent.py as root_agent)
from .agent import root_agent as agent_instance  # Adjust based on your agent.py

logger = logging.getLogger(__name__)


def get_agent(agent_card: AgentCard):
    """Get the agent, given an agent card."""
    try:
        return agent_instance  # Return the agent instance from agent.py
    except Exception as e:
        raise e

# A2A Setup
def create_a2a_app(agent_card_path: str):
    logger.info("Creating A2A app with agent card: %s", agent_card_path)
    with Path(agent_card_path).open() as file:
        data = json.load(file)
    agent_card = AgentCard(**data)

    request_handler = DefaultRequestHandler(
        agent_executor=CustomAgentExecutor(agent=get_agent(agent_card)),
        task_store=InMemoryTaskStore(),
        push_config_store=InMemoryPushNotificationConfigStore(),
    )
    logger.info("Request handler created for agent: %s", agent_card.name)

    app = A2AStarletteApplication(
        agent_card=agent_card, http_handler=request_handler
    ).build()
    logger.info("A2AStarletteApplication built")
    return app

# FastAPI with ADK UI
AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESSION_DB_URL = ""
ALLOWED_ORIGINS = ["http://localhost", "http://localhost:8080", "*"]
SERVE_WEB_INTERFACE = True

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    session_db_url=os.getenv("SESSION_DB_URL", SESSION_DB_URL),
    allow_origins=ALLOWED_ORIGINS,
    web=SERVE_WEB_INTERFACE,
)

# Mount A2A app at /a2a (or root if preferred)
a2a_app = create_a2a_app('orchestrator_agent/card.json')
app.mount("/api", a2a_app)  # Mount A2A at /api to avoid UI conflicts

@click.command()
@click.option('--host', 'host', default='0.0.0.0')
@click.option('--port', 'port', default=10101)
def main(host, port):
    """Starts the Orchestrator Agent with ADK UI and A2A server."""
    try:
        logger.info(f'Starting Orchestrator Agent with ADK UI on {host}:{port}')
        uvicorn.run(app, host=host, port=port, log_level='debug')
    except Exception as e:
        logger.error(f'An error occurred during server startup: {e}')
        sys.exit(1)

if __name__ == '__main__':
    main()
