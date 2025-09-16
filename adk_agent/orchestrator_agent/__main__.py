import logging
import sys
import json

from pathlib import Path

import click
import httpx
import uvicorn

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


@click.command()
@click.option('--host', 'host', default='0.0.0.0')
@click.option('--port', 'port', default=10101)
@click.option('--agent-card', 'agent_card', default='orchestrator_agent/card.json')
def main(host, port, agent_card):
    """Starts the Orchestrator Agent as an A2A server."""
    try:
        with Path(agent_card).open() as file:
            data = json.load(file)
        agent_card = AgentCard(**data)

        client = httpx.AsyncClient()
        request_handler = DefaultRequestHandler(
            agent_executor=CustomAgentExecutor(agent=get_agent(agent_card)),
            task_store=InMemoryTaskStore(),
            push_config_store=InMemoryPushNotificationConfigStore(),
        )

        server = A2AStarletteApplication(
            agent_card=agent_card, http_handler=request_handler
        )

        logger.info(f'Starting Orchestrator Agent server on {host}:{port}')

        uvicorn.run(server.build(), host=host, port=port)
    except FileNotFoundError:
        logger.error(f"Error: File '{agent_card}' not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        logger.error(f"Error: File '{agent_card}' contains invalid JSON.")
        sys.exit(1)
    except Exception as e:
        logger.error(f'An error occurred during server startup: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
