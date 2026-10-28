# Tencent is pleased to support the open source community by making tRPC-A2A-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-A2A-Python is licensed under Apache-2.0.
"""Shared fixtures for the trpc-a2a tests.

Nothing here binds a port: apps are driven through FastAPI's TestClient and
the A2A SDK client is replaced by a fake in the client tests.
"""
from typing import Dict

import pytest
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import AgentCapabilities
from a2a.types import AgentCard
from a2a.types import Part
from a2a.types import TextPart
from a2a.utils import new_task

from trpc_sdk.abc import TrpcContext
from trpc_sdk.config import TrpcConfig

import trpc_a2a  # noqa: F401  # registers the a2a protocol and plugin
from trpc_a2a import TrpcA2AService
from trpc_a2a import get_a2a_request_context
from trpc_a2a.server import _trpc_fastapi_adapter
from trpc_a2a.server.a2a_registry import A2AServiceRegistry

SERVICE_NAME = "trpc.a2a_test.test_a2a_agent"


class EchoAgent(TrpcA2AService):
    """Agent that completes every task with an ``echo: <input>`` artifact.

    Attributes:
        seen_contexts: tRPC context of every ``execute`` call.
    """

    def __init__(self):
        super().__init__()
        self.seen_contexts = []

    async def get_agent_card(self) -> AgentCard:
        """Return a minimal card with an empty URL, so the service address is injected."""
        return AgentCard(name="Echo Agent",
                         description="echo",
                         url="",
                         version="1.0.0",
                         default_input_modes=["text"],
                         default_output_modes=["text"],
                         capabilities=AgentCapabilities(streaming=True),
                         skills=[])

    async def execute(self, context: TrpcContext, event_queue: EventQueue) -> None:
        """Echo the user input back as an artifact and complete the task."""
        self.seen_contexts.append(context)
        a2a_context = get_a2a_request_context(context)
        task = a2a_context.current_task or new_task(a2a_context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.add_artifact([Part(root=TextPart(text=f"echo: {a2a_context.get_user_input()}"))], name="echo")
        await updater.complete()

    async def cancel(self, context: TrpcContext, event_queue: EventQueue) -> None:
        """Nothing to cancel."""


@pytest.fixture(autouse=True)
def isolate_a2a_state(monkeypatch):
    """Give every test empty service registries and an unbuilt plugin."""
    monkeypatch.setattr(A2AServiceRegistry, "_services", {})
    monkeypatch.setattr(_trpc_fastapi_adapter, "_a2a_services", {})
    monkeypatch.setattr(_trpc_fastapi_adapter, "_built_pid", None)


@pytest.fixture
def load_config(tmp_path, monkeypatch):
    """Load a YAML string into ``TrpcConfig`` and restore the old state afterwards."""
    monkeypatch.setattr(TrpcConfig, "_config", TrpcConfig.config())
    monkeypatch.setattr(TrpcConfig, "_plugins_config", TrpcConfig.plugins_config())
    monkeypatch.setattr(TrpcConfig, "_config_parser", TrpcConfig.config_parser())

    def _load(content: str) -> Dict:
        path = tmp_path / "trpc_python.yaml"
        path.write_text(content, encoding="utf-8")
        return TrpcConfig.load(str(path))

    return _load
