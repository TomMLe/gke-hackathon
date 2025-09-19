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

# Import your agent class (assuming it's defined in agent.py as CartMonitorAgent or similar)
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
@click.option('--port', 'port', default=10102)
@click.option('--agent-card', 'agent_card', default='cart_monitor_agent/card.json')
def main(host, port, agent_card):
    """Starts the Cart Monitor Agent as an A2A server."""
    try:
        with Path(agent_card).open() as file:
            data = json.load(file)
        agent_card = AgentCard(**data)

        request_handler = DefaultRequestHandler(
            agent_executor=AgentExecutor(agent=get_agent(agent_card)),
            task_store=InMemoryTaskStore(),
            push_config_store=InMemoryPushNotificationConfigStore(),
        )

        server = A2AStarletteApplication(
            agent_card=agent_card, http_handler=request_handler
        )

        logger.info(f'Starting Cart Monitor Agent server on {host}:{port}')

        # Build Starlette app and add a lightweight endpoint to fetch the latest artifact from the in-memory task store.
        app = server.build()

        from starlette.responses import JSONResponse

        async def tasks_last(request):
            try:
                task_store = request_handler.task_store
                tasks = list(getattr(task_store, "_tasks", {}).values())
                if tasks:
                    last = tasks[-1]
                    artifacts = getattr(last, "artifacts", None) or (last.get("artifacts") if isinstance(last, dict) else None)
                    if artifacts:
                        last_art = artifacts[-1]
                        payload = last_art.get("payload") if isinstance(last_art, dict) else None
                        if payload:
                            return JSONResponse({"result": payload})
                return JSONResponse({})
            except Exception as e:
                logger.exception("tasks_last failed")
                return JSONResponse({"error": str(e)}, status_code=500)

        try:
            app.add_route("/tasks/last", tasks_last, methods=["GET"])
            logger.info("Registered /tasks/last endpoint for retrieving latest artifact.")
        except Exception as e:
            logger.error(f"Failed adding route /tasks/last: {e}")

        uvicorn.run(app, host=host, port=port)
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
