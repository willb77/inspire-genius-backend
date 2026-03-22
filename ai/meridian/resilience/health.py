from __future__ import annotations

"""
Agent Health Monitoring — tracks agent availability and provides health endpoints.
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
from ai.meridian.core.types import AgentId
from ai.meridian.resilience.circuit_breaker import CircuitBreaker, CircuitState
from prism_inspire.core.log_config import logger


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class AgentHealthMonitor:
    """
    Monitors health of all agents and orchestrators.

    Provides:
    - Per-agent circuit breakers
    - Health check aggregation
    - Fallback routing when agents are down
    - Meridian always responds (graceful degradation)
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: int = 60,
    ) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._last_check: dict[str, datetime] = {}

        # Initialize circuit breakers for all agents
        for agent_id in AgentId:
            name = agent_id.value
            self._breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout_seconds=recovery_timeout,
            )
        # Add LLM provider breakers
        for provider in ["bedrock", "anthropic", "openai"]:
            self._breakers[f"llm_{provider}"] = CircuitBreaker(
                name=f"llm_{provider}",
                failure_threshold=failure_threshold,
                recovery_timeout_seconds=recovery_timeout,
            )

    def is_agent_available(self, agent_id: str) -> bool:
        """Check if an agent is available (circuit not open)."""
        breaker = self._breakers.get(agent_id)
        if breaker is None:
            return True  # Unknown agents are assumed available
        return breaker.allow_request()

    def record_success(self, agent_id: str) -> None:
        breaker = self._breakers.get(agent_id)
        if breaker:
            breaker.record_success()
            self._last_check[agent_id] = datetime.utcnow()

    def record_failure(self, agent_id: str) -> None:
        breaker = self._breakers.get(agent_id)
        if breaker:
            breaker.record_failure()
            self._last_check[agent_id] = datetime.utcnow()

    def get_agent_health(self, agent_id: str) -> HealthStatus:
        """Get health status for a specific agent."""
        breaker = self._breakers.get(agent_id)
        if breaker is None:
            return HealthStatus.HEALTHY
        state = breaker.state
        if state == CircuitState.CLOSED:
            return HealthStatus.HEALTHY
        elif state == CircuitState.HALF_OPEN:
            return HealthStatus.DEGRADED
        return HealthStatus.UNHEALTHY

    def get_system_health(self) -> dict[str, Any]:
        """Get overall system health summary."""
        agents = {}
        unhealthy_count = 0
        degraded_count = 0

        for name, breaker in self._breakers.items():
            if name.startswith("llm_"):
                continue
            health = self.get_agent_health(name)
            agents[name] = {
                "status": health.value,
                "circuit": breaker.state.value,
                "stats": breaker.get_stats(),
            }
            if health == HealthStatus.UNHEALTHY:
                unhealthy_count += 1
            elif health == HealthStatus.DEGRADED:
                degraded_count += 1

        # LLM providers
        providers = {}
        for name, breaker in self._breakers.items():
            if name.startswith("llm_"):
                providers[name] = {
                    "status": self.get_agent_health(name).value,
                    "stats": breaker.get_stats(),
                }

        total_agents = len(agents)
        healthy_count = total_agents - unhealthy_count - degraded_count

        if unhealthy_count > total_agents // 2:
            overall = HealthStatus.UNHEALTHY
        elif unhealthy_count > 0 or degraded_count > 0:
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY

        return {
            "overall": overall.value,
            "meridian_available": True,  # Meridian ALWAYS responds
            "agents": agents,
            "providers": providers,
            "summary": {
                "total": total_agents,
                "healthy": healthy_count,
                "degraded": degraded_count,
                "unhealthy": unhealthy_count,
            },
        }

    def get_fallback_agent(self, failed_agent_id: str) -> Optional[str]:
        """
        Suggest a fallback agent when the primary is unavailable.
        Returns None if no fallback is available (Meridian handles gracefully).
        """
        fallbacks = {
            AgentId.ECHO.value: AgentId.AURA.value,     # Learning → behavioral context
            AgentId.ANCHOR.value: AgentId.AURA.value,    # Resilience → behavioral context
            AgentId.FORGE.value: AgentId.AURA.value,     # Interpersonal → behavioral context
            AgentId.NOVA.value: AgentId.AURA.value,      # Career → behavioral context
            AgentId.JAMES.value: AgentId.NOVA.value,     # Fit scoring → career strategy
            AgentId.SAGE.value: AgentId.AURA.value,      # Research → behavioral context
            AgentId.ASCEND.value: AgentId.NOVA.value,    # Leadership → career strategy
            AgentId.ALEX.value: AgentId.NOVA.value,      # Student → career strategy
            AgentId.ATLAS.value: AgentId.AURA.value,     # Org → behavioral context
            AgentId.SENTINEL.value: None,                 # Compliance has no fallback — escalate
            AgentId.NEXUS.value: AgentId.AURA.value,     # Culture → behavioral context
            AgentId.BRIDGE.value: AgentId.NOVA.value,    # Pipeline → career strategy
        }
        fallback = fallbacks.get(failed_agent_id)
        if fallback and self.is_agent_available(fallback):
            return fallback
        return None

    def reset_agent(self, agent_id: str) -> None:
        """Manually reset an agent's circuit breaker."""
        breaker = self._breakers.get(agent_id)
        if breaker:
            breaker.reset()
