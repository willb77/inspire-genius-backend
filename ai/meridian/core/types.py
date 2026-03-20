from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

class AgentId(str, Enum):
    """All agent identifiers in the Meridian system."""
    MERIDIAN = "meridian"
    # Personal Development
    AURA = "aura"
    ECHO = "echo"
    ANCHOR = "anchor"
    FORGE = "forge"
    # Organizational Intelligence
    ATLAS = "atlas"
    SENTINEL = "sentinel"
    NEXUS = "nexus"
    BRIDGE = "bridge"
    # Strategic Advisory
    NOVA = "nova"
    JAMES = "james"
    SAGE = "sage"
    ASCEND = "ascend"
    ALEX = "alex"

class OrchestratorId(str, Enum):
    PERSONAL_DEVELOPMENT = "personal_development"
    ORGANIZATIONAL_INTELLIGENCE = "organizational_intelligence"
    STRATEGIC_ADVISORY = "strategic_advisory"

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    AWAITING_HUMAN = "awaiting_human"

class TaskPriority(int, Enum):
    LOW = 1
    NORMAL = 5
    HIGH = 8
    HUMAN_CORRECTION = 10

class ConfidenceLevel(str, Enum):
    HIGH = "high"        # >= 0.85 - autonomous execution
    MEDIUM = "medium"    # 0.60-0.84 - proceed with logging
    LOW = "low"          # < 0.60 - human escalation required

class AgentTask(BaseModel):
    """A task dispatched to a specialist agent."""
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: AgentId
    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    behavioral_context: Optional[dict[str, Any]] = None  # Aura's output
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    timeout_seconds: int = 300

class AgentResult(BaseModel):
    """Result from a specialist agent processing a task."""
    task_id: str
    agent_id: AgentId
    status: TaskStatus
    output: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    reasoning: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    completed_at: datetime = Field(default_factory=datetime.utcnow)

class AgentCapability(BaseModel):
    """Describes what an agent can do."""
    agent_id: AgentId
    name: str
    tagline: str
    domain: OrchestratorId
    actions: list[str]
    description: str

class DAGNode(BaseModel):
    """A node in a task execution DAG."""
    node_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task: AgentTask
    dependencies: list[str] = Field(default_factory=list)  # node_ids this depends on
    results: Optional[AgentResult] = None

class ProcessTemplate(BaseModel):
    """A predefined workflow template."""
    template_id: str
    name: str
    description: str
    trigger_patterns: list[str]  # intent patterns that activate this template
    steps: list[dict[str, Any]]  # ordered steps with agent assignments
    variables: dict[str, Any] = Field(default_factory=dict)

class UserIntent(BaseModel):
    """Classified user intent."""
    raw_input: str
    domain: OrchestratorId
    intent_type: str
    confidence: float = Field(ge=0.0, le=1.0)
    entities: dict[str, Any] = Field(default_factory=dict)
    matched_template: Optional[str] = None
