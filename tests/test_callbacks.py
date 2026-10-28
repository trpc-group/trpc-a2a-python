# Tencent is pleased to support the open source community by making tRPC-A2A-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-A2A-Python is licensed under Apache-2.0.
"""Tests of the before/after fastapi callbacks that map A2A requests onto tRPC messages."""
import json
from types import SimpleNamespace

import pytest
from fastapi import Response
from starlette.responses import JSONResponse

from trpc_sdk.abc import TrpcContext
from trpc_sdk.abc import get_message
from trpc_sdk.exceptions import TrpcErrorCode
from trpc_sdk.exceptions import TrpcException
from trpc_fastapi._constants import PROTOCOL_NAME

from trpc_a2a.server._trpc_fastapi_adapter import _handle_after_process_response
from trpc_a2a.server._trpc_fastapi_adapter import _handle_before_process_request


def _ctx(protocol: str = "a2a") -> TrpcContext:
    """Build a context that looks like one served under ``protocol``."""
    ctx = TrpcContext()
    ctx.with_meta_data(PROTOCOL_NAME, protocol)
    return ctx


def _request(path: str, body=None) -> SimpleNamespace:
    """Build the parts of a Starlette request the before-callback reads."""

    async def _json():
        if body is None:
            raise ValueError("no body")
        return body

    return SimpleNamespace(client=SimpleNamespace(host="10.0.0.1", port=5000),
                           url=SimpleNamespace(path=path),
                           json=_json)


@pytest.mark.asyncio
async def test_before_sets_rpc_name_from_jsonrpc_method():
    """Test a JSON-RPC body names the RPC after its method."""
    ctx = _ctx()
    body = {"jsonrpc": "2.0", "id": "1", "method": "tasks/get", "params": {"id": "t1"}}

    await _handle_before_process_request(ctx, _request("/", body))

    assert get_message(ctx).server_rpc_name == "tasks/get"


@pytest.mark.asyncio
async def test_before_uses_agent_card_path():
    """Test the agent card path is used as the RPC name without reading a body."""
    ctx = _ctx()

    await _handle_before_process_request(ctx, _request("/.well-known/agent-card.json"))

    assert get_message(ctx).server_rpc_name == "/.well-known/agent-card.json"


@pytest.mark.asyncio
async def test_before_falls_back_to_path_on_bad_body():
    """Test an unparsable body names the RPC after the URL path."""
    ctx = _ctx()

    await _handle_before_process_request(ctx, _request("/rpc"))

    assert get_message(ctx).server_rpc_name == "/rpc"


@pytest.mark.asyncio
async def test_before_ignores_other_protocols():
    """Test requests of another fastapi protocol are left alone."""
    ctx = _ctx("http_fastapi")

    await _handle_before_process_request(ctx, _request("/.well-known/agent-card.json"))

    assert get_message(ctx).server_rpc_name != "/.well-known/agent-card.json"


@pytest.mark.asyncio
async def test_after_turns_jsonrpc_error_into_trpc_exception():
    """Test a 200 JSON-RPC error response is recorded as the server error."""
    ctx = _ctx()
    response = JSONResponse({"jsonrpc": "2.0", "id": "1", "error": {"code": -32001, "message": "Task not found"}})

    returned = await _handle_after_process_response(ctx, response)

    err = get_message(ctx).server_rsp_err
    assert returned is response
    assert isinstance(err, TrpcException)
    assert err.code == -32001
    assert err.msg == "Task not found"


@pytest.mark.asyncio
async def test_after_leaves_success_untouched():
    """Test a successful JSON-RPC response sets no server error."""
    ctx = _ctx()
    response = JSONResponse({"jsonrpc": "2.0", "id": "1", "result": {}})

    await _handle_after_process_response(ctx, response)

    assert get_message(ctx).server_rsp_err.code == TrpcErrorCode.TRPC_INVOKE_SUCCESS


@pytest.mark.asyncio
async def test_after_without_response_returns_500():
    """Test a handler failure becomes a JSON-RPC 500 response."""
    ctx = _ctx()
    get_message(ctx).set_server_rsp_err(RuntimeError("boom"))

    returned = await _handle_after_process_response(ctx, None)

    assert isinstance(returned, Response)
    assert returned.status_code == 500
    assert json.loads(returned.body) == {
        "jsonrpc": "2.0",
        "error": {
            "code": TrpcErrorCode.TRPC_SERVER_SYSTEM_ERR,
            "message": "boom"
        },
        "id": None,
    }
