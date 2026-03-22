from __future__ import annotations

"""
LLM cost tracking per agent per organization.
"""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field
from prism_inspire.core.log_config import logger
from ai.meridian.core.types import AgentId


# Approximate cost per 1K tokens (input/output) by model tier
TOKEN_COSTS = {
    "tier_1_complex": {"input": 0.003, "output": 0.015},     # Sonnet
    "tier_2_moderate": {"input": 0.0008, "output": 0.004},   # Haiku
    "tier_3_fast": {"input": 0.0001, "output": 0.0004},      # Nova Micro
}

AGENT_TIERS = {
    "meridian": "tier_1_complex",
    "aura": "tier_1_complex", "nova": "tier_1_complex",
    "james": "tier_1_complex", "atlas": "tier_1_complex", "ascend": "tier_1_complex",
    "echo": "tier_2_moderate", "forge": "tier_2_moderate",
    "sage": "tier_2_moderate", "sentinel": "tier_2_moderate", "nexus": "tier_2_moderate",
    "anchor": "tier_3_fast", "bridge": "tier_3_fast", "alex": "tier_3_fast",
}

# Default per-agent token budgets (max tokens per request)
AGENT_TOKEN_BUDGETS = {
    "meridian": 4000, "aura": 3000, "nova": 3000, "james": 3000,
    "atlas": 3000, "ascend": 3000,
    "echo": 2000, "forge": 2000, "sage": 2000, "sentinel": 1500, "nexus": 1500,
    "anchor": 1500, "bridge": 1500, "alex": 2000,
}


class CostRecord(BaseModel):
    """A single cost record."""
    agent_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    org_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class CostTracker:
    """
    Tracks LLM token usage and cost per agent per organization.
    """

    def __init__(self) -> None:
        self._records: list[CostRecord] = []

    def record(
        self,
        agent_id: str,
        input_tokens: int,
        output_tokens: int,
        org_id: Optional[str] = None,
    ) -> CostRecord:
        """Record token usage and compute cost."""
        tier = AGENT_TIERS.get(agent_id, "tier_2_moderate")
        costs = TOKEN_COSTS.get(tier, TOKEN_COSTS["tier_2_moderate"])
        cost = (input_tokens / 1000 * costs["input"]) + (output_tokens / 1000 * costs["output"])

        record = CostRecord(
            agent_id=agent_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=round(cost, 6),
            org_id=org_id,
        )
        self._records.append(record)
        return record

    def get_summary(
        self,
        org_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Get cost summary with optional filters."""
        records = self._records
        if org_id:
            records = [r for r in records if r.org_id == org_id]
        if agent_id:
            records = [r for r in records if r.agent_id == agent_id]

        total_cost = sum(r.cost_usd for r in records)
        total_input = sum(r.input_tokens for r in records)
        total_output = sum(r.output_tokens for r in records)

        by_agent: dict[str, dict[str, Any]] = {}
        for r in records:
            if r.agent_id not in by_agent:
                by_agent[r.agent_id] = {"cost": 0.0, "input_tokens": 0, "output_tokens": 0, "calls": 0}
            by_agent[r.agent_id]["cost"] += r.cost_usd
            by_agent[r.agent_id]["input_tokens"] += r.input_tokens
            by_agent[r.agent_id]["output_tokens"] += r.output_tokens
            by_agent[r.agent_id]["calls"] += 1

        return {
            "total_cost_usd": round(total_cost, 4),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_records": len(records),
            "by_agent": by_agent,
        }

    def get_token_budget(self, agent_id: str) -> int:
        """Get the token budget for an agent."""
        return AGENT_TOKEN_BUDGETS.get(agent_id, 2000)

    def get_record_count(self) -> int:
        return len(self._records)
