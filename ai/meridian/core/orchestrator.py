from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from ai.meridian.core.types import (
    AgentTask, AgentResult, DAGNode, ProcessTemplate,
    OrchestratorId, AgentId, TaskStatus, ConfidenceLevel,
)
from ai.meridian.core.base_agent import BaseAgent
from prism_inspire.core.log_config import logger


class BaseOrchestrator(ABC):
    """
    Base class for domain orchestrators.

    Orchestrators are LLM-powered planners that:
    1. Generate structured task graphs (DAGs) from process templates
    2. Dispatch tasks to specialist agents
    3. Aggregate results
    4. Check confidence thresholds (Sentinel integration)
    """

    def __init__(self, orchestrator_id: OrchestratorId):
        self._orchestrator_id = orchestrator_id
        self._agents: dict[AgentId, BaseAgent] = {}
        self._templates: dict[str, ProcessTemplate] = {}

    @property
    def orchestrator_id(self) -> OrchestratorId:
        return self._orchestrator_id

    def register_agent(self, agent: BaseAgent) -> None:
        """Register a specialist agent with this orchestrator."""
        self._agents[agent.agent_id] = agent
        logger.info(
            f"Orchestrator {self._orchestrator_id.value}: "
            f"registered agent {agent.agent_id.value}"
        )

    def register_template(self, template: ProcessTemplate) -> None:
        """Register a process template."""
        self._templates[template.template_id] = template

    def get_agent(self, agent_id: AgentId) -> Optional[BaseAgent]:
        return self._agents.get(agent_id)

    @abstractmethod
    async def plan(self, intent: str, context: dict) -> list[DAGNode]:
        """
        Generate a DAG of tasks from the user intent.
        Uses process template matching: classify intent → match template →
        fill variables → validate rules → dispatch.
        """
        ...

    async def execute_dag(self, dag: list[DAGNode]) -> list[AgentResult]:
        """
        Execute a DAG of tasks, respecting dependencies.
        Returns all results in completion order.
        """
        results: list[AgentResult] = []
        completed: dict[str, AgentResult] = {}
        pending = list(dag)

        while pending:
            # Find nodes whose dependencies are all satisfied
            ready = [
                node for node in pending
                if all(dep_id in completed for dep_id in node.dependencies)
            ]
            if not ready:
                logger.error(
                    f"Orchestrator {self._orchestrator_id.value}: "
                    "DAG deadlock - no ready nodes but pending remain"
                )
                break

            for node in ready:
                # Inject results from dependencies into task context
                dep_results = {
                    dep_id: completed[dep_id].output
                    for dep_id in node.dependencies
                    if dep_id in completed
                }
                if dep_results:
                    node.task.context["dependency_results"] = dep_results

                agent = self._agents.get(node.task.agent_id)
                if agent is None:
                    logger.error(
                        f"No agent registered for {node.task.agent_id.value}"
                    )
                    result = AgentResult(
                        task_id=node.task.task_id,
                        agent_id=node.task.agent_id,
                        status=TaskStatus.FAILED,
                        output={"error": "Agent not registered"},
                        confidence=0.0,
                    )
                else:
                    result = await agent._execute(node.task)

                node.results = result
                completed[node.node_id] = result
                results.append(result)
                pending.remove(node)

        return results

    def match_template(self, intent: str) -> Optional[ProcessTemplate]:
        """Match an intent string against registered process templates."""
        for template in self._templates.values():
            for pattern in template.trigger_patterns:
                if pattern.lower() in intent.lower():
                    return template
        return None

    def _check_confidence(self, confidence: float) -> ConfidenceLevel:
        """Evaluate confidence level for autonomous vs human-approval decisions."""
        if confidence >= 0.85:
            return ConfidenceLevel.HIGH
        elif confidence >= 0.60:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW
