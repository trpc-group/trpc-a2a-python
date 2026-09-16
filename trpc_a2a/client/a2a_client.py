# -*- coding: utf-8 -*-
#
# Copyright @ 2025 Tencent.com
"""A2A Client wrapper for tRPC-Python integration."""

from typing import Any, Dict, List, Optional, Callable
from collections.abc import AsyncGenerator

import httpx

from a2a.types import (
    SendMessageRequest,
    SendMessageResponse,
    SendStreamingMessageRequest,
    SendStreamingMessageResponse,
    GetTaskRequest,
    GetTaskResponse,
    CancelTaskRequest,
    CancelTaskResponse,
    SetTaskPushNotificationConfigRequest,
    SetTaskPushNotificationConfigResponse,
    GetTaskPushNotificationConfigRequest,
    GetTaskPushNotificationConfigResponse,
    TaskResubscriptionRequest,
    AgentCard,
    JSONRPCErrorResponse,
)
from a2a.client.middleware import ClientCallInterceptor
from a2a.client.errors import A2AClientError

from trpc import client as TRPCClient
from trpc.client.options import with_service_name, with_serialization_type, with_protocol, with_timeout
from trpc.codec import clone_client_message, SerializationType
from trpc.trpc_abc.context import Context
from trpc.exceptions import NewFrameError, TRPCBaseError, ErrorCode
from trpc.log import logger

from trpc_a2a.client.request import _Request, _Response
from trpc_a2a.client.a2a_card_resolver import ResolverResult, ResolverSource
from trpc_a2a.client.utils import convert_a2a_error_to_trpc_error

# default a2a invoke timeout: 10s
_DEFAULT_TIMEOUT = 10000


class TrpcA2AClient:
    """
    A2A Client wrapper for tRPC-Python.

    Provides tRPC-compatible interfaces for A2A SDK operations including
    message sending, task management, and callback configuration.
    """

    def __init__(
        self,
        service_name: str,
        resolver_result: ResolverResult,
        interceptors: Optional[List[ClientCallInterceptor]] = None,
        httpx_client: Optional[httpx.AsyncClient] = None,
    ):
        """Initialize A2A client from resolver result.

        Args:
            service_name: The service name for tRPC
            resolver_result: The ResolverResult containing AgentCard and source information
            interceptors: Optional list of client call interceptors to apply to requests
            httpx_client: Optional httpx.AsyncClient instance to use for HTTP requests

        Raises:
            ValueError: If httpx_client is provided but not an httpx.AsyncClient instance
        """
        # Validate httpx_client type if provided
        if httpx_client is not None and not isinstance(httpx_client, httpx.AsyncClient):
            raise ValueError("httpx_client must be an httpx.AsyncClient instance")

        self.card_resolver = resolver_result
        self.service_name = service_name
        self.trpc_client = TRPCClient.get_client()
        self.interceptors = interceptors or []
        self.httpx_client = httpx_client

    async def _invoke(self, ctx: Context, request: _Request, options: Optional[List[Callable]] = None) -> _Response:
        """Common setup and invocation logic for both handle methods.

        Args:
            ctx: The tRPC Context instance
            request: The A2A request wrapper
            options: Optional method-specific tRPC options

        Returns:
            The response from the tRPC client

        Raises:
            TRPCBaseError: For tRPC or A2A client errors
        """
        ctx, msg = clone_client_message(ctx)
        msg.set_callee_service_name(self.service_name)
        msg.set_callee_method(request.method)

        # Add interceptors, service_name, and card_resolver to the request
        request.service_name = self.service_name
        request.interceptors = self.interceptors
        request.card_resolver = self.card_resolver
        request.httpx_client = self.httpx_client

        # Set the A2A request as the client request head
        msg.set_client_req_head(request)

        needed_options = [
            with_service_name(self.service_name),
            with_serialization_type(SerializationType.Noop),
        ]

        if self.card_resolver.source == ResolverSource.URL:
            needed_options.extend([
                with_protocol("a2a"),
                # Set default timeout(10s) for non-yaml scenario.
                # It can be replaced when user pass options.
                with_timeout(_DEFAULT_TIMEOUT),
            ])

        if options is None:
            options = needed_options
        else:
            options.extend(needed_options)

        logger.debug(f"[A2A Client] Invoking tRPC client with A2A method: {request.method}")

        # Invoke through tRPC client infrastructure
        await self.trpc_client.invoke(ctx, request, bytes, options)

        # Get the response from the message
        return msg.client_rsp_head

    async def _handle_streaming(self,
                                ctx: Context,
                                request: _Request,
                                options: Optional[List[Callable]] = None) -> AsyncGenerator[Any, None]:
        """Handle streaming A2A request through tRPC infrastructure.

        Args:
            ctx: The tRPC Context instance
            request: The A2A request wrapper
            options: Optional method-specific tRPC options

        Yields:
            The streaming response items from A2A operation

        Raises:
            TRPCBaseError: For tRPC or A2A client errors
        """
        # Because trpc-python's invoke method currently not supported returning iterator,
        # we need to encapsulate the error here which mainly keep user interface consistent with unary invoke.
        try:
            response = await self._invoke(ctx, request, options)

            # The response.result should be an AsyncGenerator from the A2A client
            if hasattr(response.result, "__aiter__"):
                async for item in response.result:
                    if isinstance(item.root, JSONRPCErrorResponse):
                        error = item.root.error
                        raise NewFrameError(error.code, error.message)
                    yield item
            else:
                # If it's not an AsyncGenerator, yield the result as a single item
                yield response.result
        except TRPCBaseError as e:
            raise e
        except A2AClientError as e:
            # Convert A2A errors to TRPC business errors
            trpc_error = convert_a2a_error_to_trpc_error(e)
            logger.error(f"[A2A Client] A2A error converted to TRPC error: {trpc_error}")
            raise trpc_error
        except Exception as e:
            logger.error(f"[A2A Client] Unexpected error: {str(e)}")
            raise NewFrameError(ErrorCode.TRPC_INVOKE_UNKNOWN_ERR, str(e))

    async def _handle(self, ctx: Context, request: _Request, options: Optional[List[Callable]] = None) -> Any:
        """Handle A2A request through tRPC infrastructure.

        Args:
            ctx: The tRPC Context instance
            request: The A2A request wrapper
            options: Optional method-specific tRPC options

        Returns:
            The response result from A2A operation

        Raises:
            TRPCBaseError: For tRPC or A2A client errors
        """
        response = await self._invoke(ctx, request, options)
        return response.result

    async def send_message(
        self,
        context: Context,
        request: SendMessageRequest,
        *,
        http_kwargs: Optional[Dict[str, Any]] = None,
        options: List[Callable] = None,
    ) -> SendMessageResponse:
        """Send a non-streaming message request to the agent.

        Args:
            context: The tRPC Context, a2a-sdk's ClientCallContext can be set by `set_a2a_client_context`
            request: The SendMessageRequest object containing the message and configuration
            options: Optional tRPC-specific options (reserved for future use)
            http_kwargs: Optional dictionary of keyword arguments to pass to the
                underlying httpx.post request

        Returns:
            A SendMessageResponse object containing the agent's response (Task or Message) or an error

        Raises:
            TRPCBaseError: If an A2A client error occurs during the request
        """
        # Create A2A request wrapper
        a2a_request = _Request(
            method="send_message",
            kwargs={
                "request": request,
                "http_kwargs": http_kwargs or {},
            },
        )

        logger.debug(f"[A2A Client] Sending message request: {request.id}")
        result = await self._handle(context, a2a_request, options)
        return result

    async def send_message_streaming(
        self,
        context: Context,
        request: SendStreamingMessageRequest,
        *,
        http_kwargs: Optional[Dict[str, Any]] = None,
        options: List[Callable] = None,
    ) -> AsyncGenerator[SendStreamingMessageResponse, None]:
        """Send a streaming message request to the agent and yield responses as they arrive.

        This method uses Server-Sent Events (SSE) to receive a stream of updates from the agent.

        Args:
            context: The tRPC Context, a2a-sdk's ClientCallContext can be set by `set_a2a_client_context`
            request: The SendStreamingMessageRequest object containing the message and configuration
            options: Optional tRPC-specific options (reserved for future use)
            http_kwargs: Optional dictionary of keyword arguments to pass to the
                underlying httpx.post request. A default `timeout=None` is set but can be overridden

        Yields:
            SendStreamingMessageResponse objects as they are received in the SSE stream.
            These can be Task, Message, TaskStatusUpdateEvent, or TaskArtifactUpdateEvent

        Raises:
            TRPCBaseError: If an A2A client error occurs during the request
        """
        # Create A2A request wrapper
        a2a_request = _Request(
            method="send_message_streaming",
            kwargs={
                "request": request,
                "http_kwargs": http_kwargs or {},
            },
        )

        logger.debug(f"[A2A Client] Starting streaming message request: {request.id}")

        # Use the streaming handler for async generator methods
        async for item in self._handle_streaming(context, a2a_request, options):
            yield item

    async def get_task(
        self,
        context: Context,
        request: GetTaskRequest,
        *,
        http_kwargs: Optional[Dict[str, Any]] = None,
        options: List[Callable] = None,
    ) -> GetTaskResponse:
        """Retrieve the current state and history of a specific task.

        Args:
            context: The tRPC Context, a2a-sdk's ClientCallContext can be set by `set_a2a_client_context`
            request: The GetTaskRequest object specifying the task ID and history length
            options: Optional tRPC-specific options (reserved for future use)
            http_kwargs: Optional dictionary of keyword arguments to pass to the
                underlying httpx.post request

        Returns:
            A GetTaskResponse object containing the Task or an error

        Raises:
            TRPCBaseError: If an A2A client error occurs during the request
        """
        # Create A2A request wrapper
        a2a_request = _Request(
            method="get_task",
            kwargs={
                "request": request,
                "http_kwargs": http_kwargs or {},
            },
        )

        logger.debug(f"[A2A Client] Getting task: {request.id}")
        result = await self._handle(context, a2a_request, options)
        return result

    async def cancel_task(
        self,
        context: Context,
        request: CancelTaskRequest,
        *,
        http_kwargs: Optional[Dict[str, Any]] = None,
        options: List[Callable] = None,
    ) -> CancelTaskResponse:
        """Request the agent to cancel a specific task.

        Args:
            context: The tRPC Context, a2a-sdk's ClientCallContext can be set by `set_a2a_client_context`
            request: The CancelTaskRequest object specifying the task ID
            options: Optional tRPC-specific options (reserved for future use)
            http_kwargs: Optional dictionary of keyword arguments to pass to the
                underlying httpx.post request

        Returns:
            A CancelTaskResponse object containing the updated Task with canceled status or an error

        Raises:
            TRPCBaseError: If an A2A client error occurs during the request
        """
        # Create A2A request wrapper
        a2a_request = _Request(
            method="cancel_task",
            kwargs={
                "request": request,
                "http_kwargs": http_kwargs or {},
            },
        )

        logger.debug(f"[A2A Client] Cancelling task: {request.id}")
        result = await self._handle(context, a2a_request, options)
        return result

    async def set_task_callback(
        self,
        context: Context,
        request: SetTaskPushNotificationConfigRequest,
        *,
        http_kwargs: Optional[Dict[str, Any]] = None,
        options: List[Callable] = None,
    ) -> SetTaskPushNotificationConfigResponse:
        """Set or update the push notification configuration for a specific task.

        Args:
            context: The tRPC Context, a2a-sdk's ClientCallContext can be set by `set_a2a_client_context`
            request: The SetTaskPushNotificationConfigRequest object specifying the task ID and configuration
            options: Optional tRPC-specific options (reserved for future use)
            http_kwargs: Optional dictionary of keyword arguments to pass to the
                underlying httpx.post request

        Returns:
            A SetTaskPushNotificationConfigResponse object containing the confirmation or an error

        Raises:
            TRPCBaseError: If an A2A client error occurs during the request
        """
        # Create A2A request wrapper
        a2a_request = _Request(
            method="set_task_callback",
            kwargs={
                "request": request,
                "http_kwargs": http_kwargs or {},
            },
        )

        logger.debug(f"[A2A Client] Setting task callback: {request.id}")
        result = await self._handle(context, a2a_request, options)
        return result

    async def get_task_callback(
        self,
        context: Context,
        request: GetTaskPushNotificationConfigRequest,
        *,
        http_kwargs: Optional[Dict[str, Any]] = None,
        options: List[Callable] = None,
    ) -> GetTaskPushNotificationConfigResponse:
        """Retrieve the push notification configuration for a specific task.

        Args:
            context: The tRPC Context, a2a-sdk's ClientCallContext can be set by `set_a2a_client_context`
            request: The GetTaskPushNotificationConfigRequest object specifying the task ID
            options: Optional tRPC-specific options (reserved for future use)
            http_kwargs: Optional dictionary of keyword arguments to pass to the
                underlying httpx.post request

        Returns:
            A GetTaskPushNotificationConfigResponse object containing the configuration or an error

        Raises:
            TRPCBaseError: If an A2A client error occurs during the request
        """
        # Create A2A request wrapper
        a2a_request = _Request(
            method="get_task_callback",
            kwargs={
                "request": request,
                "http_kwargs": http_kwargs or {},
            },
        )

        logger.debug(f"[A2A Client] Getting task callback: {request.id}")
        result = await self._handle(context, a2a_request, options)
        return result

    async def resubscribe(
        self,
        context: Context,
        request: TaskResubscriptionRequest,
        *,
        http_kwargs: Optional[Dict[str, Any]] = None,
        options: List[Callable] = None,
    ) -> AsyncGenerator[SendStreamingMessageResponse, None]:
        """Reconnect to get task updates.

        This method uses Server-Sent Events (SSE) to receive a stream of updates from the agent.

        Args:
            context: The tRPC Context, a2a-sdk's ClientCallContext can be set by `set_a2a_client_context`
            request: The TaskResubscriptionRequest object containing the task information to reconnect to
            options: Optional tRPC-specific options (reserved for future use)
            http_kwargs: Optional dictionary of keyword arguments to pass to the
                underlying httpx.post request. A default `timeout=None` is set but can be overridden

        Yields:
            SendStreamingMessageResponse objects as they are received in the SSE stream.
            These can be Task, Message, TaskStatusUpdateEvent, or TaskArtifactUpdateEvent

        Raises:
            TRPCBaseError: If an A2A client error occurs during the request
        """
        # Create A2A request wrapper
        a2a_request = _Request(
            method="resubscribe",
            kwargs={
                "request": request,
                "http_kwargs": http_kwargs or {},
            },
        )

        logger.debug(f"[A2A Client] Resubscribing to task: {request.id}")

        # Use the streaming handler for async generator methods
        async for item in self._handle_streaming(context, a2a_request, options):
            yield item

    async def get_card(
        self,
        context: Context,
        *,
        http_kwargs: Optional[Dict[str, Any]] = None,
        options: List[Callable] = None,
    ) -> AgentCard:
        """Retrieve the authenticated card (if necessary) or the public one.

        Args:
            context: The tRPC Context, a2a-sdk's ClientCallContext can be set by `set_a2a_client_context`
            options: Optional tRPC-specific options (reserved for future use)
            http_kwargs: Optional dictionary of keyword arguments to pass to the
                underlying httpx.post request

        Returns:
            An AgentCard object containing the card or an error

        Raises:
            TRPCBaseError: If an A2A client error occurs during the request
        """
        # Create A2A request wrapper
        a2a_request = _Request(
            method="get_card",
            kwargs={
                "http_kwargs": http_kwargs or {},
            },
        )

        logger.debug("[A2A Client] Getting agent card")
        result = await self._handle(context, a2a_request, options)
        return result
