from typing import Any, Dict

from a2a.server.agent_execution import AgentExecutor

class CustomAgentExecutor(AgentExecutor):
    def __init__(self, agent):
        self.agent = agent

    async def execute(self, task: Dict) -> Any:
        logger.info(f"Executing task: {task}")
        # Implement task execution using the agent
        # Assuming the agent has a 'process' method; adjust as needed
        result = await self.agent.process(task)
        logger.info(f"Task result: {result}")
        return result

    async def cancel(self, task_id: str) -> bool:
        logger.info(f"Cancelling task: {task_id}")
        # Implement cancellation logic
        # For now, return True; add actual cancellation if needed
        return True
