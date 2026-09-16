# -*- coding: utf-8 -*-
#
# Copyright @ 2025 Tencent.com
"""Base class for tRPC-A2A services."""

from abc import ABC, abstractmethod
from typing import Optional

from a2a.types import AgentCard
from a2a.server.events import EventQueue

from trpc.trpc_abc.context import Context

from fastapi import FastAPI


class TrpcA2AService(ABC):
    """Base class for tRPC-A2A services.

    Users should inherit from this class to implement their A2A agents
    within the tRPC framework.
    """

    def __init__(self):
        """Initialize the TrpcA2AService."""
        self._fastapi: Optional[FastAPI] = None

    @abstractmethod
    async def get_agent_card(self) -> AgentCard:
        """Return the agent card metadata.

        Returns:
            AgentCard: The agent's metadata describing its capabilities
        """
        pass

    @abstractmethod
    async def execute(self, context: Context, event_queue: EventQueue) -> None:
        """Execute the agent's logic for a given request context.

        The agent should read necessary information from the context and
        publish events to the event_queue. The A2A RequestContext can be
        accessed using get_a2a_request_context(context).

        Args:
            context: tRPC Context containing request information
            event_queue: Queue to publish events to
        """
        pass

    @abstractmethod
    async def cancel(self, context: Context, event_queue: EventQueue) -> None:
        """Cancel an ongoing task.

        The agent should attempt to stop the task and publish a
        TaskStatusUpdateEvent with state TaskState.canceled.

        Args:
            context: tRPC Context containing task information
            event_queue: Queue to publish cancellation status to
        """
        pass

    def set_fastapi(self, app: FastAPI) -> None:
        """Set a custom FastAPI instance for this service.

        Args:
            app: The FastAPI instance to use
        """
        if not isinstance(app, FastAPI):
            raise TypeError("app must be a FastAPI instance")

        self._fastapi = app
