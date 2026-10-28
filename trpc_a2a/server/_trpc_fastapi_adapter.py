# Tencent is pleased to support the open source community by making tRPC-A2A-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-A2A-Python is licensed under Apache-2.0.
"""Service registry for tRPC-A2A services."""
import asyncio
import json
import os
from typing import Any
from typing import Coroutine
from typing import Dict
from typing import Optional

from fastapi import FastAPI
from fastapi import Response
from fastapi import Request
from starlette.responses import JSONResponse

from a2a.types import A2ARequest

from trpc_sdk.abc import PluginInitPos
from trpc_sdk.abc import PluginType
from trpc_sdk.abc import TrpcContext
from trpc_sdk.abc import get_message
from trpc_sdk.config import ServerService
from trpc_sdk.config import TrpcConfig
from trpc_sdk.config import default_worker_num
from trpc_sdk.exceptions import TrpcErrorCode
from trpc_sdk.exceptions import TrpcErrorType
from trpc_sdk.exceptions import TrpcException
from trpc_sdk.exceptions import create_frame_error
from trpc_sdk.log import logger
from trpc_sdk.plugin import register_plugin
from trpc_fastapi import register_fastapi_app

from trpc_fastapi import register_before_process_request_callback
from trpc_fastapi import register_after_process_response_callback
from trpc_fastapi import register_protocol_to_fastapi
from trpc_fastapi import get_protocol_name

from ..common import PLUGIN_NAME
from ..common import PROTOCOL_NAME
from ..common import VERSION

from .a2a_registry import A2AServiceRegistry
from .trpc_fastapi_app import TrpcFastAPIApp
from .redis_conf import get_redis_conf_by_name
from .a2a_service import TrpcA2AService

_MULTI_PROCESS_MODE = "multi_process"

_a2a_services: Dict[str, ServerService] = {}
_built_pid: Optional[int] = None


def get_a2a_services() -> Dict[str, ServerService]:
    """Get all A2A services found by the last ``find_a2a_services`` call."""
    return _a2a_services


register_protocol_to_fastapi(PROTOCOL_NAME)


def find_a2a_services() -> Dict[str, ServerService]:
    """Collect every server service whose protocol is ``a2a``.

    Returns:
        Service configs keyed by service name.
    """
    for service in TrpcConfig.server_config().service:
        if service.protocol == PROTOCOL_NAME:
            _a2a_services[service.name] = service
    return _a2a_services


async def create_a2a_app(a2a_service: TrpcA2AService, service_config: ServerService) -> FastAPI:
    """Create a A2A app."""
    return await TrpcFastAPIApp.create_app(
        service=a2a_service,
        service_config=service_config,
        redis_config=get_redis_conf_by_name(service_config.name),
    )


def _run_blocking(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run ``coro`` to completion on a private event loop.

    The loop is never installed with ``set_event_loop``, so the loop the SDK
    set for this thread is left untouched.

    Args:
        coro: Coroutine to run.

    Returns:
        The coroutine's result.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _serving_process_num() -> int:
    """Return how many processes serve each address under the configured process model."""
    model = TrpcConfig.global_config().processmodel
    if model is None or model.mode != _MULTI_PROCESS_MODE:
        return 1
    return model.handle_num if model.handle_num > 0 else default_worker_num()


def _warn_if_task_state_not_shared(services: Dict[str, ServerService]) -> None:
    """Warn when several processes serve an A2A service backed by in-memory stores.

    Args:
        services: A2A service configs keyed by service name.
    """
    process_num = _serving_process_num()
    if process_num <= 1:
        return
    for service_name in services:
        if get_redis_conf_by_name(service_name).redis_name:
            continue
        logger.warning(f"[A2A] Service '{service_name}' is served by {process_num} processes without "
                       f"'redis_name'; tasks are kept in process memory, so tasks/get and tasks/cancel "
                       f"may reach a process that does not know the task. Configure redis_name to share them.")


@register_plugin(PluginType.USER_DEFINED, PLUGIN_NAME, init_pos=PluginInitPos.WORKER, version=VERSION, report=True)
def setup_a2a_agent():
    """Build and register the FastAPI app of every configured A2A service.

    Runs once per serving process, before the fastapi starter binds any address.
    """
    global _built_pid
    if _built_pid == os.getpid():
        return
    _built_pid = os.getpid()

    a2a_services_configs = find_a2a_services()
    _warn_if_task_state_not_shared(a2a_services_configs)
    for service_name, service_config in a2a_services_configs.items():
        a2a_service = A2AServiceRegistry.get(service_name)
        if not a2a_service:
            logger.warning(f"A2A service '{service_name}' not registered. "
                           f"Please use register_service('{service_name}', service_instance) before starting server.")
            continue
        app = _run_blocking(create_a2a_app(a2a_service, service_config))
        register_fastapi_app(service_config.name, app)


_HTTP_INTERNAL_ERROR_CODE = 500
_DEFAULT_AGENT_CARD_PATH = "/.well-known/agent-card.json"


async def _handle_before_process_request(ctx: TrpcContext, request: Request) -> None:
    """Handle before request.

    Args:
        ctx: The tRPC context
        request: The incoming FastAPI request
    """
    protocol_name = get_protocol_name(ctx)
    if protocol_name != PROTOCOL_NAME:
        return
    # Set Message
    message = get_message(ctx)
    message.set_remote_addr(f"{request.client.host}:{request.client.port}")
    if request.url.path == _DEFAULT_AGENT_CARD_PATH:
        message.set_server_rpc_name(_DEFAULT_AGENT_CARD_PATH)
    else:
        try:
            body = await request.json()
            a2a_request = A2ARequest.model_validate(body)
            message.set_server_rpc_name(a2a_request.root.method)
        except Exception:
            # let a2a-sdk handle the error so that filter can be gotten
            message.set_server_rpc_name(request.url.path)


def _create_error_response(error: Exception) -> Response:
    """Create an error response from an exception.

    Args:
        error: The exception that occurred

    Returns:
        FastAPI Response with error details
    """
    error_response = {
        "jsonrpc": "2.0",
        "error": {
            "code": TrpcErrorCode.TRPC_SERVER_SYSTEM_ERR,
            "message": str(error)
        },  # Internal error
        "id": None,
    }

    return Response(content=json.dumps(error_response),
                    status_code=_HTTP_INTERNAL_ERROR_CODE,
                    media_type="application/json")


async def _handle_after_process_response(ctx: TrpcContext, response: Response) -> Optional[Response]:
    """Handle after response.

    Args:
        ctx: The tRPC context
        response: The outgoing FastAPI response
    """
    protocol_name = get_protocol_name(ctx)
    if protocol_name != PROTOCOL_NAME:
        return None
    message = get_message(ctx)
    if response is None:
        # occurred error when processing user request
        return _create_error_response(message.server_rsp_err)
    # When encountering error, rsp will be a JSONResponse object with A2AError
    # But tRPC-Python need error to be raised, so we raise error here,
    #   but convert error to JSONResponse after filter executing
    if isinstance(response, JSONResponse) and response.status_code == 200:
        # Extract error information from JSONResponse
        response_data = {}
        try:
            response_content = response.body.decode("utf-8")
            response_data = json.loads(response_content)
            if "error" in response_data:
                error = response_data["error"]
                error_code = error.get("code", TrpcErrorCode.TRPC_INVOKE_UNKNOWN_ERR)
                error_message = error.get("message", "Unknown error")
                err = create_frame_error(error_code, error_message)
                logger.debug(f"[A2A] Converting JSONResponse error to TrpcException: {err}")
                message.set_server_rsp_err(err)
        except json.JSONDecodeError:
            # If we can't parse the response, create a generic error
            err = TrpcException(TrpcErrorType.FRAMEWORK, TrpcErrorCode.TRPC_SERVER_SYSTEM_ERR,
                                "Failed to parse error response")
            logger.error("[A2A] Failed to parse JSONResponse error content")
            message.set_server_rsp_err(err)
    return response


register_before_process_request_callback(_handle_before_process_request)
register_after_process_response_callback(_handle_after_process_response)
