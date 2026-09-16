# -*- coding: utf-8 -*-
#
# Copyright @ 2025 Tencent.com
"""Service registry for tRPC-A2A services."""
import asyncio
import json
from typing import Dict

from fastapi import FastAPI
from fastapi import Response
from fastapi import Request
from starlette.responses import JSONResponse

from a2a.types import A2ARequest

from trpc.plugin import PluginInitPos
from trpc.plugin import PluginType
from trpc.plugin import register_plugin
from trpc.context import TrpcContext
from trpc.log import logger
from trpc.codec.message import get_message
from trpc.config import config as trpc_config
from trpc.exceptions import ErrorCode
from trpc.exceptions import NewFrameError
from trpc.exceptions import TRPCBaseError
from trpc.exceptions import ErrorType
from trpc_fastapi import register_fastapi_app

from trpc_fastapi import register_before_process_request_callback
from trpc_fastapi import register_after_process_response_callback
from trpc_fastapi import register_protocol_to_fastapi
from trpc_fastapi import get_protocol_name

from ..common import PLUGIN_NAME, PROTOCOL_NAME

from .a2a_registry import A2AServiceRegistry
from .trpc_fastapi_app import TrpcFastAPIApp
from .redis_conf import get_redis_conf_by_name
from .a2a_service import TrpcA2AService

_a2a_services: Dict[str, trpc_config.Service] = {}


def get_a2a_services() -> list[str]:
    """Get all A2A services."""
    return _a2a_services

register_protocol_to_fastapi(PROTOCOL_NAME)


def find_a2a_services() -> Dict[str, trpc_config.Service]:
    """Find all A2A services."""
    global _a2a_services
    for service in trpc_config.global_config_obj.server.service:
        if service.protocol == PROTOCOL_NAME:
            _a2a_services[service.name] = service
    return _a2a_services


async def create_a2a_app(a2a_service: TrpcA2AService, service_config: trpc_config.Service) -> FastAPI:
    """Create a A2A app."""
    # Get distributed configuration from service adapter options
    return await TrpcFastAPIApp.create_app(
        service=a2a_service,
        service_config=service_config,
        redis_config=get_redis_conf_by_name(service_config.name),
    )


@register_plugin(PluginType.USER_DEFINED, PLUGIN_NAME, init_pos=PluginInitPos.WORKER)
def setup_a2a_agent():
    """Initialize and register the AgUiAgent plugin.
    """
    a2a_services_configs = find_a2a_services()
    for service_name, service_config in a2a_services_configs.items():
        a2a_service = A2AServiceRegistry.get(service_name)
        if not a2a_service:
            logger.warning(f"A2A service '{service_name}' not registered. "
                         f"Please use register_service('{service_name}', service_instance) before starting server.")
            continue
        app = asyncio.get_event_loop().run_until_complete(create_a2a_app(a2a_service, service_config))
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
            "code": ErrorCode.TRPC_SERVER_SYSTEM_ERR,
            "message": str(error)
        },  # Internal error
        "id": None,
    }

    return Response(content=json.dumps(error_response),
                    status_code=_HTTP_INTERNAL_ERROR_CODE,
                    media_type="application/json")


async def _handle_after_process_response(ctx: TrpcContext, response: Response) -> None:
    """Handle after response.

    Args:
        ctx: The tRPC context
        response: The outgoing FastAPI response
    """
    protocol_name = get_protocol_name(ctx)
    if protocol_name != PROTOCOL_NAME:
        return
    message = ctx.get_client_message()
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
                error_code = error.get("code", ErrorCode.TRPC_INVOKE_UNKNOWN_ERR)
                error_message = error.get("message", "Unknown error")
                err = NewFrameError(error_code, error_message)
                logger.debug(f"[A2A] Converting JSONResponse error to TRPCBaseError: {err}")
                message.set_server_rsp_err(err)
        except json.JSONDecodeError:
            # If we can't parse the response, create a generic error
            err = TRPCBaseError(ErrorType.Framework, ErrorCode.TRPC_SERVER_SYSTEM_ERR, "Failed to parse error response")
            logger.error("[A2A] Failed to parse JSONResponse error content")
            message.set_server_rsp_err(err)
    return response


register_before_process_request_callback(_handle_before_process_request)
register_after_process_response_callback(_handle_after_process_response)
