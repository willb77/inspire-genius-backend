"""
Unit tests for Path 4: force-inject full document text into the
PrismCoachAgent system prompt.

Covers:
  1. `get_full_text_for_file_ids` — happy path, empty input, tenant-scoped
     filter, budget truncation, parent-fetch failure resilience.
  2. PrismCoachAgent prompt — `<FORCE_LOADED_DOCUMENTS>` section is injected
     when `connection_handler.full_text_by_file_id` is populated, and
     omitted when empty.
"""
from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ─── get_full_text_for_file_ids ──────────────────────────────────────


@pytest.mark.asyncio
async def test_full_text_empty_file_ids_returns_empty():
    from ai.file_services.schema import get_full_text_for_file_ids

    out = await get_full_text_for_file_ids([], user_id=str(uuid.uuid4()))
    assert out == {}


@pytest.mark.asyncio
async def test_full_text_happy_path_two_files():
    from ai.file_services.schema import get_full_text_for_file_ids

    user_id = str(uuid.uuid4())
    fid_a = str(uuid.uuid4())
    fid_b = str(uuid.uuid4())

    # Mock Milvus store: two files, three chunks each. Chunks reference parent_ids.
    def _docs_for(expr: str):
        if fid_a in expr:
            return [
                SimpleNamespace(metadata={"parent_id": "100", "file_id": fid_a}),
                SimpleNamespace(metadata={"parent_id": "101", "file_id": fid_a}),
                SimpleNamespace(metadata={"parent_id": "100", "file_id": fid_a}),  # dup
            ]
        if fid_b in expr:
            return [
                SimpleNamespace(metadata={"parent_id": "200", "file_id": fid_b}),
                SimpleNamespace(metadata={"parent_id": "201", "file_id": fid_b}),
            ]
        return []

    mock_store = MagicMock()

    async def _async_search(*, query, k, expr):
        return _docs_for(expr)

    mock_store.asimilarity_search = _async_search

    parent_contents = {
        "100": "alpha section one",
        "101": "alpha section two",
        "200": "beta section one",
        "201": "beta section two",
    }

    with patch(
        "prism_inspire.core.milvus_client.milvus_client.get_store",
        return_value=mock_store,
    ), patch(
        "ai.file_services.vector_utils.parent_store.get_parent_contents_sync",
        return_value=parent_contents,
    ):
        out = await get_full_text_for_file_ids([fid_a, fid_b], user_id=user_id)

    assert set(out.keys()) == {fid_a, fid_b}
    # File A should have parents 100, 101 concatenated (dedup applied)
    assert "alpha section one" in out[fid_a]
    assert "alpha section two" in out[fid_a]
    # File B should have parents 200, 201
    assert "beta section one" in out[fid_b]
    assert "beta section two" in out[fid_b]
    # No truncation expected (output well under budget)
    assert "[...truncated" not in out[fid_a]
    assert "[...truncated" not in out[fid_b]


@pytest.mark.asyncio
async def test_full_text_tenant_scoped_filter():
    """The Milvus filter must include user_id to prevent cross-tenant access."""
    from ai.file_services.schema import get_full_text_for_file_ids

    user_id = str(uuid.uuid4())
    fid = str(uuid.uuid4())

    captured_expr = {}
    mock_store = MagicMock()

    async def _async_search(*, query, k, expr):
        captured_expr["expr"] = expr
        return []

    mock_store.asimilarity_search = _async_search

    with patch(
        "prism_inspire.core.milvus_client.milvus_client.get_store",
        return_value=mock_store,
    ), patch(
        "ai.file_services.vector_utils.parent_store.get_parent_contents_sync",
        return_value={},
    ):
        await get_full_text_for_file_ids([fid], user_id=user_id)

    assert "user_id" in captured_expr["expr"]
    assert user_id in captured_expr["expr"]
    assert fid in captured_expr["expr"]


@pytest.mark.asyncio
async def test_full_text_budget_truncation():
    """When per-file content exceeds the char budget, output is truncated with a marker."""
    from ai.file_services.schema import get_full_text_for_file_ids

    user_id = str(uuid.uuid4())
    fid = str(uuid.uuid4())

    mock_store = MagicMock()

    async def _async_search(*, query, k, expr):
        return [SimpleNamespace(metadata={"parent_id": "1", "file_id": fid})]

    mock_store.asimilarity_search = _async_search

    huge = "x" * 10_000

    with patch(
        "prism_inspire.core.milvus_client.milvus_client.get_store",
        return_value=mock_store,
    ), patch(
        "ai.file_services.vector_utils.parent_store.get_parent_contents_sync",
        return_value={"1": huge},
    ):
        # Tiny budget forces truncation
        out = await get_full_text_for_file_ids([fid], user_id=user_id, char_budget=500)

    assert fid in out
    assert len(out[fid]) <= 1000  # truncated body + marker tail
    assert "[...truncated" in out[fid]


@pytest.mark.asyncio
async def test_full_text_milvus_failure_resilience():
    """If Milvus query throws, we log and return {} — never raise."""
    from ai.file_services.schema import get_full_text_for_file_ids

    user_id = str(uuid.uuid4())
    fid = str(uuid.uuid4())

    mock_store = MagicMock()

    async def _async_search(*, query, k, expr):
        raise RuntimeError("milvus connection refused")

    mock_store.asimilarity_search = _async_search

    with patch(
        "prism_inspire.core.milvus_client.milvus_client.get_store",
        return_value=mock_store,
    ):
        out = await get_full_text_for_file_ids([fid], user_id=user_id)

    assert out == {}


# ─── PrismCoachAgent prompt injection ────────────────────────────────


def _make_mock_handler(full_text_by_file_id, filenames=None):
    handler = SimpleNamespace()
    handler.ws = MagicMock()
    handler.agent_id = "prism-coach"
    handler.user_data = {"sub": str(uuid.uuid4())}
    handler.vector_store = MagicMock()
    handler.system_prompt = "INSTRUCTIONS\n{knowledge_base}\nEND"
    handler.file_ids = list(full_text_by_file_id.keys())
    handler.accent = "US/English"
    handler.tone = "Warm"
    handler.voice = "coral"
    handler.report_str = {}
    handler.filenames = filenames or {fid: f"doc_{i}.pdf" for i, fid in enumerate(full_text_by_file_id)}
    handler.predefined_agents = []
    handler.full_text_by_file_id = full_text_by_file_id
    return handler


@pytest.mark.asyncio
async def test_prism_agent_injects_force_loaded_section_when_populated():
    """The <FORCE_LOADED_DOCUMENTS> block must appear in the assembled prompt."""
    fid_a = str(uuid.uuid4())
    fid_b = str(uuid.uuid4())
    handler = _make_mock_handler(
        full_text_by_file_id={
            fid_a: "FULL TEXT OF DOCUMENT A — long detailed content",
            fid_b: "FULL TEXT OF DOCUMENT B — different detailed content",
        },
        filenames={fid_a: "report_a.pdf", fid_b: "report_b.pdf"},
    )

    from ai.ai_agent_services.agent_services.agents.prism_coach_agent import PrismCoachAgent

    # Stub out Gemini helper + Milvus retrievers so the test stays self-contained
    helper = SimpleNamespace(
        user_document_queries="",
        prism_knowledge_queries="",
        prism_coach_professional_knowledge="",
    )

    async def _stub_gemini(*args, **kwargs):
        return helper

    async def _stub_search(*args, **kwargs):
        return ""

    with patch(
        "ai.ai_agent_services.agent_services.agents.prism_coach_agent.get_assistant_helper_gemini",
        new=_stub_gemini,
    ), patch(
        "ai.ai_agent_services.agent_services.agents.prism_coach_agent.get_similarity_search_async",
        new=_stub_search,
    ), patch(
        "ai.ai_agent_services.agent_services.agents.prism_coach_agent.get_coaches_db",
        return_value=MagicMock(),
    ):
        agent = PrismCoachAgent(handler)
        _, system_prompt = await agent.get_knowledge_and_prompt("compare these two documents")

    assert "<FORCE_LOADED_DOCUMENTS>" in system_prompt
    assert "</FORCE_LOADED_DOCUMENTS>" in system_prompt
    assert "report_a.pdf" in system_prompt
    assert "report_b.pdf" in system_prompt
    assert "FULL TEXT OF DOCUMENT A" in system_prompt
    assert "FULL TEXT OF DOCUMENT B" in system_prompt


@pytest.mark.asyncio
async def test_prism_agent_omits_force_section_when_empty():
    """No <FORCE_LOADED_DOCUMENTS> block when full_text_by_file_id is empty."""
    handler = _make_mock_handler(full_text_by_file_id={})

    from ai.ai_agent_services.agent_services.agents.prism_coach_agent import PrismCoachAgent

    helper = SimpleNamespace(
        user_document_queries="",
        prism_knowledge_queries="",
        prism_coach_professional_knowledge="",
    )

    async def _stub_gemini(*args, **kwargs):
        return helper

    async def _stub_search(*args, **kwargs):
        return ""

    with patch(
        "ai.ai_agent_services.agent_services.agents.prism_coach_agent.get_assistant_helper_gemini",
        new=_stub_gemini,
    ), patch(
        "ai.ai_agent_services.agent_services.agents.prism_coach_agent.get_similarity_search_async",
        new=_stub_search,
    ), patch(
        "ai.ai_agent_services.agent_services.agents.prism_coach_agent.get_coaches_db",
        return_value=MagicMock(),
    ):
        agent = PrismCoachAgent(handler)
        _, system_prompt = await agent.get_knowledge_and_prompt("standard question")

    assert "<FORCE_LOADED_DOCUMENTS>" not in system_prompt
    # Existing sections still present
    assert "<USER_CASE_FILES>" in system_prompt
    assert "<INTERNAL_EXPERTISE>" in system_prompt


# ─── Route alias registration ─────────────────────────────────────────


def test_alias_route_registered():
    """Both /v1/ws/agents/{agent_id} and /v1/agents/ws/{agent_id} should be
    registered. We use AST inspection rather than importing the FastAPI app
    because the full app import chain pulls in deps that may not be in a
    minimal test environment (the project uses poetry; this assertion needs
    to remain runnable without the full lockfile installed)."""
    import ast

    src_path = "ai/ai_agent_services/agent_services/agent_services.py"
    with open(src_path) as f:
        tree = ast.parse(f.read())

    paths_found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "agent_chat":
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr == "websocket"
                    and dec.args
                    and isinstance(dec.args[0], ast.Constant)
                ):
                    paths_found.append(dec.args[0].value)

    assert "/ws/agents/{agent_id}" in paths_found, (
        f"Original route missing on agent_chat — found: {paths_found}"
    )
    assert "/agents/ws/{agent_id}" in paths_found, (
        f"Alias route missing on agent_chat — found: {paths_found}. Without "
        f"it, the frontend's URL pattern /v1/agents/ws/<agent> 404s."
    )
