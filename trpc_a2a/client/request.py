# Tencent is pleased to support the open source community by making tRPC-A2A-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-A2A-Python is licensed under Apache-2.0.
"""Request and response classes for tRPC-A2A client integration."""

from typing import Any
from typing import Dict
from typing import List
from typing import Optional

import httpx

from a2a.client.legacy import A2AClient
from a2a.client.middleware import ClientCallInterceptor

from trpc_sdk.abc import TrpcContext
from trpc_sdk.exceptions import ClientInvokeError
from trpc_sdk.log import logger

from trpc_a2a.client.utils import get_a2a_client_context
from trpc_a2a.client.a2a_card_resolver import ResolverResult


class _Request:
    """
    tRPC-A2A request encapsulation class.
    Encapsulates A2A client method calls with unified request processing.
    """

    # List of methods that don't require a request object
    NO_REQUEST_METHODS = {
        "get_card",
    }

    # List of streaming methods that return AsyncGenerator
    STREAMING_METHODS = {
        "send_message_streaming",
        "resubscribe",
    }

    def __init__(self, method: str, kwargs: Dict[str, Any]):
        """Initialize A2A request.

        Args:
            method: A2A method name (e.g., "send_message", "get_task")
            kwargs: Keyword arguments for A2A client method call, should include request object
        """
        self.method = method
        self.kwargs = kwargs
        self.service_name: Optional[str] = None
        self.interceptors: Optional[List[ClientCallInterceptor]] = None
        self.card_resolver: Optional[ResolverResult] = None
        self.httpx_client: Optional[httpx.AsyncClient] = None

    async def do_request(self, a2a_client: A2AClient, context: TrpcContext) -> "_Response":
        """Execute the A2A request using the provided client and context.

        Args:
            a2a_client: The A2A client instance
            context: The tRPC Context instance

        Returns:
            _Response containing the result or error

        Raises:
            TrpcException: For A2A client errors
            ClientInvokeError: For unexpected errors
        """
        try:
            method_func = getattr(a2a_client, self.method)
        except AttributeError as e:
            logger.error(f"A2A client method {self.method} does not exist: {str(e)}")
            raise ClientInvokeError(f"A2A client method {self.method} does not exist") from e

        # Get A2A client context from tRPC context
        self.kwargs["context"] = get_a2a_client_context(context)

        # Extract request object and prepare method kwargs
        request_obj = None
        if self.method not in self.NO_REQUEST_METHODS:
            request_obj = self.kwargs.pop("request", None)
        method_kwargs = self.kwargs
        if "http_kwargs" in method_kwargs:
            http_kwargs = method_kwargs["http_kwargs"]
            if "timeout" not in http_kwargs:
                # httpx takes seconds; a non-positive tRPC timeout means no limit
                timeout_sec = context.get_timeout_sec()
                method_kwargs["http_kwargs"]["timeout"] = timeout_sec if timeout_sec > 0 else None

        # Call the A2A client method
        if self.method in self.STREAMING_METHODS:
            # For streaming methods, don't await - return the async generator directly
            if request_obj is not None:
                result = method_func(request_obj, **method_kwargs)
            else:
                result = method_func(**method_kwargs)
        else:
            # For non-streaming methods, await the result
            if request_obj is not None:
                result = await method_func(request_obj, **method_kwargs)
            else:
                result = await method_func(**method_kwargs)

        logger.debug(f"A2A request succeeded for method {self.method}")

        return _Response(result=result)


class _Response:
    """
    Response message encapsulation class.
    Encapsulates A2A client operation response results.
    """

    def __init__(self, result: Any = None):
        """Initialize A2A response.

        Args:
            result: The response result from A2A client
        """
        self.result = result

    def __str__(self) -> str:
        return f"_Response(result={self.result})"
