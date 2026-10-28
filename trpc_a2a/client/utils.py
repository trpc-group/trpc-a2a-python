# Tencent is pleased to support the open source community by making tRPC-A2A-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-A2A-Python is licensed under Apache-2.0.
"""Utility functions for tRPC-A2A client integration."""

from typing import Optional

from a2a.client.middleware import ClientCallContext
from a2a.client.errors import (
    A2AClientError,
    A2AClientHTTPError,
    A2AClientJSONRPCError,
)

from trpc_sdk.abc import TrpcContext
from trpc_sdk.exceptions import TrpcErrorCode
from trpc_sdk.exceptions import TrpcException
from trpc_sdk.exceptions import create_frame_error
from trpc_sdk.log import logger

A2A_CLIENT_CONTEXT_KEY = "__trpc_a2a_client_call_context__"


def convert_a2a_error_to_trpc_error(a2a_error: A2AClientError) -> TrpcException:
    """Convert A2A client errors to TRPC framework errors.

    Args:
        a2a_error: The A2A client error to convert

    Returns:
        TrpcException: The converted TRPC framework error
    """
    if isinstance(a2a_error, A2AClientHTTPError):
        # Use a specific error code for HTTP errors
        error_code = a2a_error.status_code
        error_msg = f"A2AClientHTTPError {a2a_error.status_code}: {a2a_error.message}"
    elif isinstance(a2a_error, A2AClientJSONRPCError):
        error_code = a2a_error.error.code
        error_msg = f"A2AClientJSONRPCError {a2a_error.error.code}: {a2a_error.error.message}"
    else:
        # Use TRPC_INVOKE_UNKNOWN_ERR for all other A2A errors
        error_code = TrpcErrorCode.TRPC_INVOKE_UNKNOWN_ERR
        error_msg = f"A2A Error: {a2a_error.message}"

    return create_frame_error(error_code, error_msg)


def get_a2a_client_context(trpc_context: TrpcContext) -> Optional[ClientCallContext]:
    """Extract A2A ClientCallContext from tRPC Context.

    This utility function retrieves the A2A ClientCallContext that was
    stored in the tRPC Context during client request processing.

    Args:
        trpc_context: The tRPC Context instance

    Returns:
        A2A ClientCallContext if found, None otherwise

    Example:
        >>> async def my_client_call(context: TrpcContext):
        >>>     # Get A2A client context from tRPC context
        >>>     client_ctx = get_a2a_client_context(context)
        >>>     if client_ctx:
        >>>         # Use client context for interceptors, etc.
        >>>         pass
    """
    try:
        client_context = trpc_context.get_meta_data(A2A_CLIENT_CONTEXT_KEY)
        if client_context and isinstance(client_context, ClientCallContext):
            return client_context
        return None
    except Exception as e:
        logger.error(f"[A2A Client] Error retrieving A2A client context: {e}")
        return None


def set_a2a_client_context(trpc_context: TrpcContext, client_context: ClientCallContext) -> None:
    """Store A2A ClientCallContext in tRPC Context.

    This utility function stores the A2A ClientCallContext in the tRPC
    Context's metadata for later retrieval.

    Args:
        trpc_context: The tRPC Context instance
        client_context: The A2A ClientCallContext to store

    Example:
        >>> trpc_ctx = TrpcContext()
        >>> client_ctx = ClientCallContext(...)
        >>> set_a2a_client_context(trpc_ctx, client_ctx)
    """
    try:
        trpc_context.with_meta_data(A2A_CLIENT_CONTEXT_KEY, client_context)
        logger.debug("[A2A Client] Stored A2A client context in tRPC context")
    except Exception as e:
        logger.error(f"[A2A Client] Error storing A2A client context: {e}")
        raise
