# Tencent is pleased to support the open source community by making tRPC-A2A-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-A2A-Python is licensed under Apache-2.0.
"""End-to-end tests of a built A2A app through FastAPI's TestClient.

The A2A app is registered the way the WORKER plugin does it and then built by
trpc_fastapi for a real SDK service, so requests run through the fastapi
middleware, the callback filter and the A2A request handler.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from trpc_sdk.abc import TrpcContext
from trpc_sdk.config import ServerService
from trpc_sdk.server import ServiceOption
from trpc_sdk.server import create_service
from trpc_fastapi import register_fastapi_app
from trpc_fastapi import _trpc_server_process
from trpc_fastapi._trpc_server_process import FastapiProcess
from trpc_fastapi._trpc_server_process import TrpcFastapiServerProcess

from trpc_a2a.server._trpc_fastapi_adapter import _run_blocking
from trpc_a2a.server._trpc_fastapi_adapter import create_a2a_app

from .conftest import SERVICE_NAME
from .conftest import EchoAgent

_PORT = 18090


@pytest.fixture
def agent():
    """The agent served by the app under test."""
    return EchoAgent()


@pytest.fixture
def client(agent, monkeypatch):
    """TestClient over the fastapi app trpc_fastapi builds for the a2a service."""
    monkeypatch.setattr(_trpc_server_process, "_user_fastapi_app", {})
    service_config = ServerService(name=SERVICE_NAME, protocol="a2a", ip="127.0.0.1", port=_PORT, network="tcp")
    register_fastapi_app(SERVICE_NAME, _run_blocking(create_a2a_app(agent, service_config)))

    opt = ServiceOption()
    opt.set_protocol("a2a")
    opt.set_network("tcp")
    opt.set_address(("127.0.0.1", _PORT))
    opt.set_timeout(5000)
    service = create_service(SERVICE_NAME, opt)
    worker = SimpleNamespace(services=[service],
                             tran_opts=[service.opt.transport_option],
                             exit_callbacks=[],
                             post_drain_callbacks=[],
                             drain_seconds=0.0)
    server_process = TrpcFastapiServerProcess(FastapiProcess(), worker, 0)
    return TestClient(server_process.build_app())


def _send_message(text: str) -> dict:
    """Build a JSON-RPC ``message/send`` request body."""
    return {
        "jsonrpc": "2.0",
        "id": str(uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": str(uuid4()),
                "parts": [{
                    "kind": "text",
                    "text": text
                }],
            }
        },
    }


def test_agent_card_url_comes_from_service_address(client):
    """Test the card is served and an empty card URL is replaced by the service address."""
    response = client.get("/.well-known/agent-card.json")

    assert response.status_code == 200
    assert response.json()["name"] == "Echo Agent"
    assert response.json()["url"] == f"http://127.0.0.1:{_PORT}"


def test_message_send_runs_agent_with_trpc_context(client, agent):
    """Test message/send completes a task and the agent sees a tRPC context."""
    response = client.post("/", json=_send_message("hi"))

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["status"]["state"] == "completed"
    assert result["artifacts"][0]["parts"][0]["text"] == "echo: hi"
    assert len(agent.seen_contexts) == 1
    assert isinstance(agent.seen_contexts[0], TrpcContext)


def test_unknown_task_returns_jsonrpc_error(client):
    """Test tasks/get on an unknown task still answers with a JSON-RPC error body."""
    response = client.post("/", json={"jsonrpc": "2.0", "id": "1", "method": "tasks/get", "params": {"id": "nope"}})

    assert response.json()["error"]["code"] == -32001
