# Tencent is pleased to support the open source community by making tRPC-A2A-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-A2A-Python is licensed under Apache-2.0.
"""Agent executor implementation for tRPC-A2A integration."""

from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue

from trpc_sdk.log import logger

from .a2a_service import TrpcA2AService
from .utils import get_trpc_context_from_request_context
from .utils import set_a2a_request_context


class TrpcA2AAgentExecutor(AgentExecutor):
    """Adapter between A2A AgentExecutor and TrpcA2AService.

    This class bridges the A2A SDK's AgentExecutor interface with
    our TrpcA2AService, handling context conversion and method delegation.
    """

    def __init__(self, service: TrpcA2AService):
        """Initialize the executor adapter.

        Args:
            service: The tRPC A2A service instance
        """
        self._service = service
        logger.info("[A2A] Initialized TrpcA2AAgentExecutor")

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute the agent's logic using tRPC context.

        This method extracts the tRPC TrpcContext from RequestContext
        and delegates to the service's execute method.

        Args:
            context: A2A request context
            event_queue: Event queue for publishing events
        """
        # Extract tRPC context from RequestContext
        trpc_ctx = get_trpc_context_from_request_context(context)

        # Store A2A context in tRPC context for service access
        set_a2a_request_context(trpc_ctx, context)

        logger.debug(f"[A2A] Executing service with task_id: {context.task_id}")

        # Execute service method
        await self._service.execute(trpc_ctx, event_queue)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel a task using tRPC context.

        This method extracts the tRPC TrpcContext from RequestContext
        and delegates to the service's cancel method.

        Args:
            context: A2A request context
            event_queue: Event queue for publishing events
        """
        # Extract tRPC context from RequestContext
        trpc_ctx = get_trpc_context_from_request_context(context)

        # Store A2A context in tRPC context for service access
        set_a2a_request_context(trpc_ctx, context)

        logger.debug(f"[A2A] Cancelling task with task_id: {context.task_id}")

        # Execute service cancel method
        await self._service.cancel(trpc_ctx, event_queue)
