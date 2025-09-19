from typing import Any, Dict
import logging

from a2a.server.agent_execution import AgentExecutor

logger = logging.getLogger(__name__)

class CustomAgentExecutor(AgentExecutor):
    def __init__(self, agent):
        self.agent = agent

    async def execute(self, task: Dict) -> Any:
        logger.info(f"Executing task: {task}")
        # Implement task execution using the agent
        # Assuming the agent has a 'process' method; adjust as needed
        try:
            if hasattr(self.agent, "process"):
                result = await self.agent.process(task)
            else:
                # Fallback: return an ACK if the agent lacks a 'process' coroutine.
                # The A2A handler may stream results separately.
                result = {"status": "accepted"}
            logger.info(f"Task result: {result}")
            return result
        except Exception as e:
            logger.exception(f"Agent execution failed: {e}")
            # Return a structured error; A2A server will handle surfacing it.
            return {"error": str(e)}

    async def cancel(self, task_id: str) -> bool:
        logger.info(f"Cancelling task: {task_id}")
        # Implement cancellation logic
        # For now, return True; add actual cancellation if needed
        return True
