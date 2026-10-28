# Tencent is pleased to support the open source community by making tRPC-A2A-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-A2A-Python is licensed under Apache-2.0.
"""A2A client transport implementation for tRPC-Python integration."""

import asyncio
from typing import Dict
from typing import Optional
from dataclasses import dataclass

from a2a.types import SendMessageResponse
from a2a.types import JSONRPCErrorResponse
import httpx

from trpc_sdk.abc import BaseClientTransport
from trpc_sdk.abc import PluginInitPos
from trpc_sdk.abc import PluginType
from trpc_sdk.abc import TrpcContext
from trpc_sdk.abc import get_message
from trpc_sdk.exceptions import ClientInvokeError
from trpc_sdk.exceptions import TrpcErrorCode
from trpc_sdk.exceptions import TrpcException
from trpc_sdk.exceptions import create_frame_error
from trpc_sdk.http import HttpClientReqHeader
from trpc_sdk.log import logger
from trpc_sdk.plugin import register_plugin
from trpc_sdk.transport import RoundTripOptions
from trpc_sdk.transport import get_client_transport

from a2a.client.legacy import A2AClient
from a2a.client.errors import A2AClientError

from ..common import PLUGIN_NAME
from ..common import VERSION

from .request import _Request
from .request import _Response
from .utils import convert_a2a_error_to_trpc_error


@dataclass
class _A2AClientInfo:
    """Private struct to store A2A client and its associated httpx client."""

    a2a_client: A2AClient
    httpx_client: httpx.AsyncClient


@register_plugin(
    PluginType.CLIENT_TRANSPORT,
    PLUGIN_NAME,
    init_pos=PluginInitPos.WORKER,
    version=VERSION,
    report=True,
)
class A2AClientTransport(BaseClientTransport):
    """
    A2A Client Transport for tRPC-Python.

    This transport plugin handles A2A protocol client requests,
    managing A2A SDK client instances and routing requests to the appropriate methods.
    Creates individual httpx clients for each A2A client and distinguishes A2A clients by service_name.
    """

    def __init__(self):
        """Initialize the A2A client transport."""
        super().__init__()
        self._client_infos: Dict[str, _A2AClientInfo] = {}
        self._lock: Optional[asyncio.Lock] = None
        self._closed = False

    def __del__(self):
        """Destructor to ensure cleanup when transport is garbage collected."""
        if len(self._client_infos) > 0 and not self._closed:
            logger.warning("[A2A Transport] Transport was not properly closed before garbage collection")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - ensures cleanup."""
        await self.close()

    async def round_trip(self, ctx: TrpcContext, req_data: bytes, options: RoundTripOptions) -> bytes:
        """Handle client request and return response.

        Args:
            ctx: The tRPC Context instance
            req_data: Request data (not used for A2A as we use message headers)
            options: Round trip options

        Returns:
            Response data (placeholder bytes)

        Raises:
            TrpcException: For A2A client errors converted to framework errors
            ClientInvokeError: For unexpected errors
        """
        message = get_message(ctx)
        # A naming service may resolve to a node registered with a2a protocol while
        # the request header is HTTP; such requests are routed by the http transport.
        if isinstance(message.client_req_head, HttpClientReqHeader):
            http_transport = get_client_transport("http")
            if not http_transport:
                raise ClientInvokeError("HTTP transport not found")
            rsp = await http_transport.round_trip(ctx, req_data, options)
            return rsp

        # Extract the A2A request from the message
        request: _Request = message.client_req_head

        # Get A2A client instance for this request using service_name
        a2a_client = await self._get_a2a_client(ctx, request)

        try:
            # Execute the A2A request with context
            response: _Response = await request.do_request(a2a_client, ctx)
            result = response.result
            # unary invoke raise error here, streaming invoke raise error in a2a_client.py
            # (as round_trip current not support returning iterator)
            if isinstance(result, SendMessageResponse) and isinstance(result.root, JSONRPCErrorResponse):
                error = result.root.error
                raise create_frame_error(error.code, error.message)
            message.set_client_rsp_head(response)
        except TrpcException as e:
            raise e
        except A2AClientError as e:
            # Convert A2A errors to TRPC business errors
            trpc_error = convert_a2a_error_to_trpc_error(e)
            logger.error(f"[A2A Transport] A2A error converted to TRPC error: {trpc_error}")
            raise trpc_error
        except Exception as e:
            logger.error(f"[A2A Transport] Unexpected error: {str(e)}")
            raise create_frame_error(TrpcErrorCode.TRPC_INVOKE_UNKNOWN_ERR, str(e))

        return b"success"

    async def _get_a2a_client(self, ctx: TrpcContext, request: _Request) -> A2AClient:
        """Get or create an A2A client instance based on service_name.

        Args:
            ctx: The tRPC Context instance
            request: The A2A request wrapper containing service_name

        Returns:
            A2A client instance

        Raises:
            ClientInvokeError: If client configuration is invalid
        """
        # Use service_name as the key for client distinction
        service_name = request.service_name
        if not service_name:
            raise ClientInvokeError("service_name is required to identify A2A client")

        # Check if client already exists for this service
        if service_name in self._client_infos:
            return self._client_infos[service_name].a2a_client

        # Created here, not in __init__, so the lock belongs to the loop that serves requests
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            # Double-check pattern
            if service_name in self._client_infos:
                return self._client_infos[service_name].a2a_client

            # Create new A2A client for this service using request
            client_info = await self._create_a2a_client(ctx, request)
            self._client_infos[service_name] = client_info
            logger.debug(f"[A2A Transport] Created new A2A client for service: {service_name}")

            return client_info.a2a_client

    async def _create_a2a_client(self, ctx: TrpcContext, request: _Request) -> _A2AClientInfo:
        """Create a new A2A client instance using the request information.

        Args:
            ctx: The tRPC Context instance
            request: The A2A request wrapper containing card_resolver and interceptors

        Returns:
            _A2AClientInfo containing the A2A client and its httpx client

        Raises:
            ClientInvokeError: If client creation fails
        """
        try:
            # Extract AgentCard and URL from ResolverResult
            agent_card = request.card_resolver.card

            # Use httpx_client from request if available, otherwise create a new one
            if request.httpx_client is not None:
                httpx_client = request.httpx_client
                logger.debug(f"[A2A Transport] Using provided httpx client for service: {request.service_name}")
            else:
                httpx_client = httpx.AsyncClient()
                logger.debug(f"[A2A Transport] Created new httpx client for service: {request.service_name}")

            # Create legacy A2A client instance using the httpx client
            a2a_client = A2AClient(
                httpx_client=httpx_client,
                agent_card=agent_card,
                url=agent_card.url,
                interceptors=request.interceptors,
            )

            # Create and return the client info struct
            client_info = _A2AClientInfo(a2a_client=a2a_client, httpx_client=httpx_client)

            logger.debug(f"[A2A Transport] Successfully created A2A client for service: {request.service_name}")
            return client_info

        except Exception as e:
            logger.error(f"[A2A Transport] Failed to create A2A client for service '{request.service_name}': {e}")
            raise ClientInvokeError(f"Failed to create A2A client for service '{request.service_name}': {e}") from e

    async def close(self):
        """Clean up resources when transport is being shut down."""
        if self._closed:
            logger.debug("[A2A Transport] Transport already closed")
            return

        # Close all httpx clients and clear client infos
        for service_name, client_info in self._client_infos.items():
            if client_info.httpx_client:
                await client_info.httpx_client.aclose()
                logger.debug(f"[A2A Transport] Closed httpx client for service: {service_name}")

        # Clear client infos dictionary
        self._client_infos.clear()

        # Mark as closed
        self._closed = True

        logger.debug("[A2A Transport] Cleaned up all client resources")
