# Tencent is pleased to support the open source community by making tRPC-A2A-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-A2A-Python is licensed under Apache-2.0.
"""Tests of ``TrpcA2AClient`` through the SDK invoke, the a2a transport and codec.

``A2AClient`` is replaced by a fake, so no request leaves the process.
"""
from uuid import uuid4

import pytest
from a2a.types import AgentCapabilities
from a2a.types import AgentCard
from a2a.types import JSONRPCError
from a2a.types import JSONRPCErrorResponse
from a2a.types import Message
from a2a.types import MessageSendParams
from a2a.types import Part
from a2a.types import Role
from a2a.types import SendMessageRequest
from a2a.types import SendMessageResponse
from a2a.types import SendMessageSuccessResponse
from a2a.types import SendStreamingMessageRequest
from a2a.types import TextPart

from trpc_sdk.abc import PluginType
from trpc_sdk.abc import TrpcContext
from trpc_sdk.client import Options
from trpc_sdk.exceptions import TrpcException
from trpc_sdk.plugin import get_plugin

from trpc_a2a.client import TrpcA2AClient
from trpc_a2a.client import a2a_transport
from trpc_a2a.client.a2a_card_resolver import ResolverResult
from trpc_a2a.client.a2a_card_resolver import ResolverSource
from trpc_a2a.client.a2a_client import _target_from_url
from trpc_a2a.client.codec import A2AClientCodec

_AGENT_URL = "http://127.0.0.1:18080"


def _message(text: str) -> Message:
    return Message(role=Role.user, message_id=str(uuid4()), parts=[Part(root=TextPart(text=text))])


class _FakeA2AClient:
    """Stand-in for ``a2a.client.legacy.A2AClient`` that answers from a queue.

    Attributes:
        calls: ``(method, request, kwargs)`` of every call.
    """

    response = None
    stream_items = []
    instances = []

    def __init__(self, httpx_client, agent_card, url, interceptors):
        self.url = url
        self.calls = []
        _FakeA2AClient.instances.append(self)

    async def send_message(self, request, **kwargs):
        self.calls.append(("send_message", request, kwargs))
        return _FakeA2AClient.response

    async def send_message_streaming(self, request, **kwargs):
        self.calls.append(("send_message_streaming", request, kwargs))
        for item in _FakeA2AClient.stream_items:
            yield item


@pytest.fixture
def fake_a2a(monkeypatch):
    """Patch ``A2AClient`` and give the registered transport an empty client cache."""
    monkeypatch.setattr(a2a_transport, "A2AClient", _FakeA2AClient)
    monkeypatch.setattr(_FakeA2AClient, "instances", [])
    transport = get_plugin(PluginType.CLIENT_TRANSPORT, "a2a")
    monkeypatch.setattr(transport, "_client_infos", {})
    monkeypatch.setattr(transport, "_lock", None)
    return _FakeA2AClient


def _client(service_name: str = "trpc_a2a_client") -> TrpcA2AClient:
    card = AgentCard(name="Echo Agent",
                     description="echo",
                     url=_AGENT_URL,
                     version="1.0.0",
                     default_input_modes=["text"],
                     default_output_modes=["text"],
                     capabilities=AgentCapabilities(streaming=True),
                     skills=[])
    return TrpcA2AClient(service_name, ResolverResult(card=card, source=ResolverSource.URL))


def test_a2a_codec_and_transport_are_registered():
    """Test importing the client registers the a2a codec and transport."""
    assert isinstance(get_plugin(PluginType.CLIENT_CODEC, "a2a"), A2AClientCodec)
    assert isinstance(get_plugin(PluginType.CLIENT_TRANSPORT, "a2a"), a2a_transport.A2AClientTransport)


def test_target_from_url():
    """Test agent URLs become ip:// targets, with the scheme's default port."""
    assert _target_from_url("http://127.0.0.1:18080/") == "ip://127.0.0.1:18080"
    assert _target_from_url("https://agent.example") == "ip://agent.example:443"
    assert _target_from_url("") == ""


@pytest.mark.asyncio
async def test_send_message_returns_a2a_response(fake_a2a):
    """Test send_message goes through invoke and returns the A2A SDK result."""
    expected = SendMessageResponse(root=SendMessageSuccessResponse(id="1", result=_message("pong")))
    fake_a2a.response = expected
    request = SendMessageRequest(id="1", params=MessageSendParams(message=_message("ping")))

    result = await _client().send_message(TrpcContext(), request, options=Options().set_timeout(3000))

    assert result is expected
    (a2a,) = fake_a2a.instances
    assert a2a.url == _AGENT_URL
    method, sent, kwargs = a2a.calls[0]
    assert method == "send_message"
    assert sent is request
    assert kwargs["http_kwargs"]["timeout"] == pytest.approx(3.0, abs=0.1)


@pytest.mark.asyncio
async def test_send_message_jsonrpc_error_raises(fake_a2a):
    """Test a JSON-RPC error answer is raised as a TrpcException."""
    fake_a2a.response = SendMessageResponse(
        root=JSONRPCErrorResponse(id="1", error=JSONRPCError(code=-32001, message="Task not found")))
    request = SendMessageRequest(id="1", params=MessageSendParams(message=_message("ping")))

    with pytest.raises(TrpcException) as exc_info:
        await _client().send_message(TrpcContext(), request)

    assert exc_info.value.code == -32001
    assert exc_info.value.msg == "Task not found"


@pytest.mark.asyncio
async def test_streaming_yields_items_and_raises_on_error(fake_a2a):
    """Test streaming yields every item until a JSON-RPC error item, which is raised."""
    ok = SendMessageResponse(root=SendMessageSuccessResponse(id="1", result=_message("chunk")))
    bad = SendMessageResponse(root=JSONRPCErrorResponse(id="1", error=JSONRPCError(code=-32603, message="boom")))
    fake_a2a.stream_items = [ok, bad]
    request = SendStreamingMessageRequest(id="1", params=MessageSendParams(message=_message("ping")))

    seen = []
    with pytest.raises(TrpcException) as exc_info:
        async for item in _client().send_message_streaming(TrpcContext(), request):
            seen.append(item)

    assert seen == [ok]
    assert exc_info.value.code == -32603
