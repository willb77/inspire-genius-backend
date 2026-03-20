from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from ai.meridian.llm.provider import (
    LLMProvider,
    LLMResponse,
    LLMMessage,
    ModelTier,
    AGENT_MODEL_TIERS,
    BedrockProvider,
    AnthropicDirectProvider,
    ProviderFactory,
)
from ai.meridian.core.types import AgentId


# ---------------------------------------------------------------------------
# Tests: ModelTier assignments
# ---------------------------------------------------------------------------

class TestModelTiers:
    def test_all_agents_have_tiers(self):
        for agent_id in AgentId:
            assert agent_id in AGENT_MODEL_TIERS, f"{agent_id} missing tier"

    def test_complex_agents_tier_1(self):
        for aid in [AgentId.MERIDIAN, AgentId.AURA, AgentId.NOVA, AgentId.JAMES]:
            assert AGENT_MODEL_TIERS[aid] == ModelTier.TIER_1_COMPLEX

    def test_moderate_agents_tier_2(self):
        for aid in [AgentId.ECHO, AgentId.FORGE, AgentId.SAGE, AgentId.SENTINEL]:
            assert AGENT_MODEL_TIERS[aid] == ModelTier.TIER_2_MODERATE

    def test_fast_agents_tier_3(self):
        for aid in [AgentId.ANCHOR, AgentId.BRIDGE, AgentId.ALEX]:
            assert AGENT_MODEL_TIERS[aid] == ModelTier.TIER_3_FAST


# ---------------------------------------------------------------------------
# Tests: BedrockProvider
# ---------------------------------------------------------------------------

class TestBedrockProvider:
    def test_provider_name(self):
        provider = BedrockProvider(region="us-east-1")
        assert provider.provider_name == "bedrock"

    def test_get_model_for_tier(self):
        provider = BedrockProvider()
        m1 = provider.get_model_for_tier(ModelTier.TIER_1_COMPLEX)
        m2 = provider.get_model_for_tier(ModelTier.TIER_2_MODERATE)
        m3 = provider.get_model_for_tier(ModelTier.TIER_3_FAST)
        assert "claude" in m1.lower() or "sonnet" in m1.lower()
        assert m1 != m3

    def test_get_model_for_agent(self):
        provider = BedrockProvider()
        model = provider.get_model_for_agent(AgentId.AURA)
        assert model == provider.TIER_MODELS[ModelTier.TIER_1_COMPLEX]

    @pytest.mark.asyncio
    async def test_chat_calls_converse(self):
        provider = BedrockProvider()
        mock_client = MagicMock()
        mock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": "Hello from Bedrock"}]}},
            "usage": {"inputTokens": 10, "outputTokens": 5},
        }
        provider._client = mock_client

        messages = [
            LLMMessage(role="system", content="You are helpful"),
            LLMMessage(role="user", content="Hi"),
        ]
        result = await provider.chat(messages, model="test-model")

        assert isinstance(result, LLMResponse)
        assert result.content == "Hello from Bedrock"
        assert result.provider == "bedrock"
        assert result.usage["input_tokens"] == 10
        mock_client.converse.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self):
        provider = BedrockProvider()
        mock_client = MagicMock()
        mock_client.converse_stream.return_value = {
            "stream": [
                {"contentBlockDelta": {"delta": {"text": "chunk1"}}},
                {"contentBlockDelta": {"delta": {"text": "chunk2"}}},
                {"someOtherEvent": {}},
            ]
        }
        provider._client = mock_client

        messages = [LLMMessage(role="user", content="Hi")]
        chunks = []
        async for chunk in provider.stream(messages, model="test-model"):
            chunks.append(chunk)

        assert chunks == ["chunk1", "chunk2"]


# ---------------------------------------------------------------------------
# Tests: AnthropicDirectProvider
# ---------------------------------------------------------------------------

class TestAnthropicDirectProvider:
    def test_provider_name(self):
        provider = AnthropicDirectProvider(api_key="test")
        assert provider.provider_name == "anthropic"

    def test_get_model_for_agent(self):
        provider = AnthropicDirectProvider(api_key="test")
        model = provider.get_model_for_agent(AgentId.ECHO)
        assert model == provider.TIER_MODELS[ModelTier.TIER_2_MODERATE]


# ---------------------------------------------------------------------------
# Tests: ProviderFactory
# ---------------------------------------------------------------------------

class TestProviderFactory:
    def setup_method(self):
        ProviderFactory.reset()

    def test_register_and_get(self):
        provider = BedrockProvider()
        ProviderFactory.register(provider, default=True)
        assert ProviderFactory.get() is provider
        assert ProviderFactory.get("bedrock") is provider

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError, match="not registered"):
            ProviderFactory.get("nonexistent")

    def test_first_registered_becomes_default(self):
        p1 = BedrockProvider()
        ProviderFactory.register(p1)
        assert ProviderFactory.get() is p1

    def test_explicit_default_overrides(self):
        p1 = BedrockProvider()
        p2 = AnthropicDirectProvider(api_key="test")
        ProviderFactory.register(p1)
        ProviderFactory.register(p2, default=True)
        assert ProviderFactory.get() is p2

    def test_get_for_agent(self):
        provider = BedrockProvider()
        ProviderFactory.register(provider, default=True)
        p, model = ProviderFactory.get_for_agent(AgentId.AURA)
        assert p is provider
        assert model is not None

    def test_reset(self):
        ProviderFactory.register(BedrockProvider())
        ProviderFactory.reset()
        with pytest.raises(ValueError):
            ProviderFactory.get()
