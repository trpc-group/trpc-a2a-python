# -*- coding: utf-8 -*-
#
# Copyright @ 2025 Tencent.com
"""Utility functions for tRPC-A2A integration."""

from typing import Optional

from a2a.server.agent_execution import RequestContext
from a2a.server.context import ServerCallContext

from trpc.trpc_abc.context import Context
from trpc.log import logger

A2A_CONTEXT_KEY = "__trpc_a2a_request_context__"
TRPC_CONTEXT_KEY = "__trpc_context__"


def get_a2a_request_context(trpc_context: Context) -> Optional[RequestContext]:
    """Extract A2A RequestContext from tRPC Context.

    This utility function retrieves the A2A RequestContext that was
    stored in the tRPC Context during request processing.

    Args:
        trpc_context: The tRPC Context instance

    Returns:
        A2A RequestContext if found, None otherwise

    Example:
        >>> async def execute(self, context: Context, event_queue: EventQueue):
        >>>     # Get A2A context from tRPC context
        >>>     a2a_context = get_a2a_request_context(context)
        >>>     if a2a_context:
        >>>         user_input = a2a_context.get_user_input()
        >>>         task_id = a2a_context.task_id
    """
    try:
        request_context = trpc_context.get_meta_data(A2A_CONTEXT_KEY)
        if request_context and isinstance(request_context, RequestContext):
            return request_context
        return None
    except Exception as e:  # pylint: disable=broad-except
        logger.error(f"[A2A] Error retrieving A2A request context: {e}")
        return None


def set_a2a_request_context(trpc_context: Context, request_context: RequestContext) -> None:
    """Store A2A RequestContext in tRPC Context.

    This utility function stores the A2A RequestContext in the tRPC
    Context's metadata for later retrieval.

    Args:
        trpc_context: The tRPC Context instance
        request_context: The A2A RequestContext to store

    Example:
        >>> trpc_ctx = Context()
        >>> a2a_ctx = RequestContext(...)
        >>> set_a2a_request_context(trpc_ctx, a2a_ctx)
    """
    try:
        trpc_context.with_meta_data(A2A_CONTEXT_KEY, request_context)
        logger.debug("[A2A] Stored A2A request context in tRPC context")
    except Exception as e:
        logger.error(f"[A2A] Error storing A2A request context: {e}")
        raise


def set_trpc_context_in_call_context(call_context: ServerCallContext, trpc_context: Context) -> None:
    """Store tRPC Context in ServerCallContext state.

    This utility function stores the tRPC Context in the A2A
    ServerCallContext's state for later retrieval.

    Args:
        call_context: The A2A ServerCallContext instance
        trpc_context: The tRPC Context to store

    Example:
        >>> call_context = ServerCallContext(...)
        >>> trpc_ctx = Context()
        >>> set_trpc_context_in_call_context(call_context, trpc_ctx)
    """
    call_context.state[TRPC_CONTEXT_KEY] = trpc_context
    logger.debug("[A2A] Stored tRPC context in call_context.state")


def get_trpc_context_from_request_context(request_context: RequestContext) -> Optional[Context]:
    """Extract tRPC Context from A2A RequestContext.

    This utility function retrieves the tRPC Context that was stored
    in the RequestContext's call_context state during request processing.

    Args:
        request_context: The A2A RequestContext instance

    Returns:
        tRPC Context if found, None otherwise

    Example:
        >>> async def execute(self, context: RequestContext, event_queue: EventQueue):
        >>>     # Get tRPC context from A2A context
        >>>     trpc_ctx = get_trpc_context_from_request_context(context)
        >>>     if trpc_ctx:
        >>>         # Use tRPC context...
    """
    return request_context.call_context.state.get(TRPC_CONTEXT_KEY)
