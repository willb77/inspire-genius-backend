from __future__ import annotations

"""
Meridian LLM Provider Abstraction.

Provides a unified interface for LLM interactions across multiple providers.
Supports per-agent model assignment and streaming responses.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, AsyncIterator, Optional
from pydantic import BaseModel, Field
from prism_inspire.core.log_config import logger
from ai.meridian.core.types import AgentId


class LLMResponse(BaseModel):
    """Standardized response from any LLM provider."""
    content: str
    model: str
    provider: str
    usage: dict[str, int] = Field(default_factory=dict)  # tokens in/out
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMMessage(BaseModel):
    """A single message in a conversation."""
    role: str  # "system", "user", "assistant"
    content: str


class ModelTier(str, Enum):
    """Model tiers for per-agent assignment."""
    TIER_1_COMPLEX = "tier_1_complex"      # Deep reasoning (Sonnet)
    TIER_2_MODERATE = "tier_2_moderate"    # Moderate tasks (Haiku)
    TIER_3_FAST = "tier_3_fast"            # Simple/fast tasks


# Per-agent model tier assignment
AGENT_MODEL_TIERS: dict[AgentId, ModelTier] = {
    AgentId.MERIDIAN: ModelTier.TIER_1_COMPLEX,
    AgentId.AURA: ModelTier.TIER_1_COMPLEX,
    AgentId.NOVA: ModelTier.TIER_1_COMPLEX,
    AgentId.JAMES: ModelTier.TIER_1_COMPLEX,
    AgentId.ATLAS: ModelTier.TIER_1_COMPLEX,
    AgentId.ASCEND: ModelTier.TIER_1_COMPLEX,
    AgentId.ECHO: ModelTier.TIER_2_MODERATE,
    AgentId.FORGE: ModelTier.TIER_2_MODERATE,
    AgentId.SAGE: ModelTier.TIER_2_MODERATE,
    AgentId.SENTINEL: ModelTier.TIER_2_MODERATE,
    AgentId.NEXUS: ModelTier.TIER_2_MODERATE,
    AgentId.ANCHOR: ModelTier.TIER_3_FAST,
    AgentId.BRIDGE: ModelTier.TIER_3_FAST,
    AgentId.ALEX: ModelTier.TIER_3_FAST,
}


class LLMProvider(ABC):
    """
    Abstract LLM provider interface.

    All providers implement chat() for single responses and
    stream() for streaming responses.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name (e.g., 'bedrock', 'anthropic')."""
        ...

    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        """Send a chat completion request and return the full response."""
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> AsyncIterator[str]:
        """Stream a chat completion response, yielding text chunks."""
        ...


class BedrockProvider(LLMProvider):
    """
    AWS Bedrock LLM provider (primary).

    Uses boto3 bedrock-runtime client for Claude and other models.
    """

    # Model IDs per tier
    TIER_MODELS: dict[ModelTier, str] = {
        ModelTier.TIER_1_COMPLEX: "anthropic.claude-sonnet-4-20250514-v1:0",
        ModelTier.TIER_2_MODERATE: "anthropic.claude-haiku-4-5-20251001-v1:0",
        ModelTier.TIER_3_FAST: "us.amazon.nova-micro-v1:0",
    }

    def __init__(self, region: Optional[str] = None) -> None:
        self._region = region
        self._client = None

    @property
    def provider_name(self) -> str:
        return "bedrock"

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3
            from prism_inspire.core.config import settings
            self._client = boto3.client(
                "bedrock-runtime",
                region_name=self._region or settings.AWS_REGION,
            )
        return self._client

    def get_model_for_tier(self, tier: ModelTier) -> str:
        return self.TIER_MODELS.get(tier, self.TIER_MODELS[ModelTier.TIER_2_MODERATE])

    def get_model_for_agent(self, agent_id: AgentId) -> str:
        tier = AGENT_MODEL_TIERS.get(agent_id, ModelTier.TIER_2_MODERATE)
        return self.get_model_for_tier(tier)

    async def chat(
        self,
        messages: list[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        import json
        client = self._get_client()
        model_id = model or self.TIER_MODELS[ModelTier.TIER_2_MODERATE]

        # Separate system message from conversation
        system_parts = []
        conversation = []
        for msg in messages:
            if msg.role == "system":
                system_parts.append({"text": msg.content})
            else:
                conversation.append({
                    "role": msg.role,
                    "content": [{"text": msg.content}],
                })

        try:
            body = {
                "messages": conversation,
                "inferenceConfig": {
                    "temperature": temperature,
                    "maxTokens": max_tokens,
                },
            }
            if system_parts:
                body["system"] = system_parts

            response = client.converse(
                modelId=model_id,
                **body,
            )

            output_text = response["output"]["message"]["content"][0]["text"]
            usage = response.get("usage", {})

            return LLMResponse(
                content=output_text,
                model=model_id,
                provider="bedrock",
                usage={
                    "input_tokens": usage.get("inputTokens", 0),
                    "output_tokens": usage.get("outputTokens", 0),
                },
            )
        except Exception as e:
            logger.error(f"BedrockProvider.chat failed: {e}")
            raise

    async def stream(
        self,
        messages: list[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> AsyncIterator[str]:
        import json
        client = self._get_client()
        model_id = model or self.TIER_MODELS[ModelTier.TIER_2_MODERATE]

        system_parts = []
        conversation = []
        for msg in messages:
            if msg.role == "system":
                system_parts.append({"text": msg.content})
            else:
                conversation.append({
                    "role": msg.role,
                    "content": [{"text": msg.content}],
                })

        try:
            body = {
                "messages": conversation,
                "inferenceConfig": {
                    "temperature": temperature,
                    "maxTokens": max_tokens,
                },
            }
            if system_parts:
                body["system"] = system_parts

            response = client.converse_stream(
                modelId=model_id,
                **body,
            )

            for event in response.get("stream", []):
                if "contentBlockDelta" in event:
                    delta = event["contentBlockDelta"].get("delta", {})
                    text = delta.get("text", "")
                    if text:
                        yield text
        except Exception as e:
            logger.error(f"BedrockProvider.stream failed: {e}")
            raise


class AnthropicDirectProvider(LLMProvider):
    """
    Direct Anthropic API provider (fallback).

    Uses the anthropic Python SDK for direct API access.
    """

    TIER_MODELS: dict[ModelTier, str] = {
        ModelTier.TIER_1_COMPLEX: "claude-sonnet-4-20250514",
        ModelTier.TIER_2_MODERATE: "claude-haiku-4-5-20251001",
        ModelTier.TIER_3_FAST: "claude-haiku-4-5-20251001",
    }

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key
        self._client = None

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self._api_key)
            except ImportError:
                raise ImportError(
                    "anthropic package required for AnthropicDirectProvider. "
                    "Install with: pip install anthropic"
                )
        return self._client

    def get_model_for_agent(self, agent_id: AgentId) -> str:
        tier = AGENT_MODEL_TIERS.get(agent_id, ModelTier.TIER_2_MODERATE)
        return self.TIER_MODELS.get(tier, self.TIER_MODELS[ModelTier.TIER_2_MODERATE])

    async def chat(
        self,
        messages: list[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        client = self._get_client()
        model_id = model or self.TIER_MODELS[ModelTier.TIER_2_MODERATE]

        system_text = ""
        conversation = []
        for msg in messages:
            if msg.role == "system":
                system_text = msg.content
            else:
                conversation.append({"role": msg.role, "content": msg.content})

        try:
            kwargs = {
                "model": model_id,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": conversation,
            }
            if system_text:
                kwargs["system"] = system_text

            response = client.messages.create(**kwargs)

            content = response.content[0].text if response.content else ""
            usage = response.usage

            return LLMResponse(
                content=content,
                model=model_id,
                provider="anthropic",
                usage={
                    "input_tokens": usage.input_tokens if usage else 0,
                    "output_tokens": usage.output_tokens if usage else 0,
                },
            )
        except Exception as e:
            logger.error(f"AnthropicDirectProvider.chat failed: {e}")
            raise

    async def stream(
        self,
        messages: list[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> AsyncIterator[str]:
        client = self._get_client()
        model_id = model or self.TIER_MODELS[ModelTier.TIER_2_MODERATE]

        system_text = ""
        conversation = []
        for msg in messages:
            if msg.role == "system":
                system_text = msg.content
            else:
                conversation.append({"role": msg.role, "content": msg.content})

        try:
            kwargs = {
                "model": model_id,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": conversation,
            }
            if system_text:
                kwargs["system"] = system_text

            with client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    yield text
        except Exception as e:
            logger.error(f"AnthropicDirectProvider.stream failed: {e}")
            raise


class ProviderFactory:
    """
    Factory for creating and managing LLM providers.

    Supports provider selection by config and per-agent model assignment.
    """

    _providers: dict[str, LLMProvider] = {}
    _default_provider: Optional[str] = None

    @classmethod
    def register(cls, provider: LLMProvider, default: bool = False) -> None:
        """Register an LLM provider."""
        cls._providers[provider.provider_name] = provider
        if default or cls._default_provider is None:
            cls._default_provider = provider.provider_name
        logger.info(
            f"ProviderFactory: registered {provider.provider_name}"
            f"{' (default)' if default else ''}"
        )

    @classmethod
    def get(cls, name: Optional[str] = None) -> LLMProvider:
        """Get a provider by name, or the default."""
        provider_name = name or cls._default_provider
        if provider_name is None or provider_name not in cls._providers:
            raise ValueError(
                f"LLM provider '{provider_name}' not registered. "
                f"Available: {list(cls._providers.keys())}"
            )
        return cls._providers[provider_name]

    @classmethod
    def get_for_agent(cls, agent_id: AgentId) -> tuple[LLMProvider, str]:
        """
        Get the provider and model for a specific agent.

        Returns:
            Tuple of (provider, model_id)
        """
        provider = cls.get()
        if hasattr(provider, "get_model_for_agent"):
            model = provider.get_model_for_agent(agent_id)
        else:
            model = None
        return provider, model

    @classmethod
    def reset(cls) -> None:
        """Reset all registered providers (useful for testing)."""
        cls._providers = {}
        cls._default_provider = None
