# -*- coding: utf-8 -*-
#
# Copyright @ 2025 Tencent.com
"""FastAPI application with tRPC integration."""

import httpx
from fastapi import FastAPI
from fastapi import Request

from a2a.server.apps.jsonrpc.fastapi_app import A2AFastAPIApplication
from a2a.server.apps.jsonrpc.jsonrpc_app import DefaultCallContextBuilder
from a2a.server.context import ServerCallContext
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.tasks import InMemoryPushNotificationConfigStore
from a2a.server.tasks import BasePushNotificationSender
from a2a.server.tasks import TaskManager
from a2a.server.tasks import ResultAggregator
from a2a.server.events import EventQueue
from a2a.server.events import EventConsumer
from a2a.types import TaskIdParams
from a2a.types import Task
from a2a.types import TaskNotFoundError
from a2a.types import InternalError
from a2a.utils.errors import ServerError

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from trpc.log import logger
from trpc.config import config as trpc_config
from trpc_fastapi import get_trpc_ctx

from .a2a_service import TrpcA2AService
from .trpc_agent_executor import TrpcA2AAgentExecutor
from .utils import set_trpc_context_in_call_context
from .redis_conf import RedisConf


class TrpcRequestHandler(DefaultRequestHandler):
    """tRPC A2A request handler that ensures context is properly propagated."""

    async def on_cancel_task(self, params: TaskIdParams, context: ServerCallContext | None = None) -> Task | None:
        """Override for 'tasks/cancel' to properly include call context.

        Attempts to cancel the task managed by the `AgentExecutor` while ensuring
        the tRPC context is properly passed to the RequestContext.
        """
        task: Task | None = await self.task_store.get(params.id)
        if not task:
            raise ServerError(error=TaskNotFoundError())

        task_manager = TaskManager(
            task_id=task.id,
            context_id=task.context_id,
            task_store=self.task_store,
            initial_message=None,
        )
        result_aggregator = ResultAggregator(task_manager)

        queue = await self._queue_manager.tap(task.id)
        if not queue:
            queue = EventQueue()

        # Use RequestContextBuilder to properly build context including call_context
        request_context = await self._request_context_builder.build(
            task_id=task.id,
            context_id=task.context_id,
            task=task,
            context=context,
        )

        await self.agent_executor.cancel(request_context, queue)

        # Cancel the ongoing task, if one exists.
        if producer_task := self._running_agents.get(task.id):
            producer_task.cancel()

        consumer = EventConsumer(queue)
        result = await result_aggregator.consume_all(consumer)
        if isinstance(result, Task):
            return result

        raise ServerError(error=InternalError(message="Agent did not return valid response for cancel"))


class TrpcCallContextBuilder(DefaultCallContextBuilder):
    """Call context builder that extracts tRPC context from request."""

    def build(self, request: Request) -> ServerCallContext:
        """Builds a ServerCallContext from a FastAPI Request.

        This method extends the default behavior to extract the tRPC context
        from contextvar and store it in the call context for later access.

        Args:
            request: The incoming FastAPI Request object.

        Returns:
            A ServerCallContext instance populated with user, state information,
            and the tRPC context if available.
        """
        # Get the base context from parent
        call_context = super().build(request)

        # Extract tRPC context from contextvar
        trpc_context = get_trpc_ctx()
        if not trpc_context:
            raise ValueError("tRPC context not found in contextvar")

        set_trpc_context_in_call_context(call_context, trpc_context)

        return call_context


class TrpcFastAPIApp(A2AFastAPIApplication):
    """FastAPI app with tRPC integration.

    This class extends A2A's FastAPI application to add tRPC-specific
    functionality like filter application and context management.
    """

    def __init__(
        self,
        agent_card,
        service: TrpcA2AService,
        service_config: trpc_config.Service,
        extended_agent_card=None,
        context_builder=None,
        redis_config: RedisConf = None,
    ):
        """Initialize the tRPC FastAPI application.

        Args:
            agent_card: The agent's metadata
            service: The tRPC A2A service instance
            service_adapter: The tRPC service adapter
            timeout: Request timeout in milliseconds
            service_name: Name of the service
            addr: Address string for logging
            extended_agent_card: Optional extended agent card
            context_builder: Optional context builder
        """
        # Create request handler with agent executor
        agent_executor = TrpcA2AAgentExecutor(service)
        if redis_config.redis_name:
            from .redis_task_store import RedisTaskStore
            from .redis_push_notification_config_store import RedisPushNotificationConfigStore

            task_store = RedisTaskStore(redis_config)
            push_config_store = RedisPushNotificationConfigStore(redis_config)
        else:
            task_store = InMemoryTaskStore()
            push_config_store = InMemoryPushNotificationConfigStore()
        push_sender = BasePushNotificationSender(httpx_client=httpx.AsyncClient(), config_store=push_config_store)
        # Use TrpcRequestHandler instead of DefaultRequestHandler to ensure proper context propagation
        http_handler = TrpcRequestHandler(
            agent_executor=agent_executor,
            task_store=task_store,
            push_config_store=push_config_store,
            push_sender=push_sender,
        )

        # Use TrpcCallContextBuilder by default if none provided
        if context_builder is None:
            context_builder = TrpcCallContextBuilder()

        super().__init__(
            agent_card=agent_card,
            http_handler=http_handler,
            extended_agent_card=extended_agent_card,
            context_builder=context_builder,
        )

        self._service = service
        self._service_name = service_config.name
        self._service_config = service_config
        self._addr = f"{service_config.ip}:{service_config.port}"

        logger.info(f"[A2A] Initialized tRPC FastAPI app for service '{self._service_name}' on {self._addr}")

    def build(self) -> FastAPI:
        """Build FastAPI application with optional custom app and middleware.

        Returns:
            Configured FastAPI application
        """
        if self._service._fastapi:
            app = self._service._fastapi
            logger.info(f"[A2A] Using existing FastAPI app from service '{self._service_name}' on {self._addr}")
            self.add_routes_to_app(app)
        else:
            app = super().build()
            logger.info(f"[A2A] Building new FastAPI app for service '{self._service_name}' on {self._addr}")

        return app

    @classmethod
    async def create_app(
        cls,
        service: TrpcA2AService,
        service_config: trpc_config.Service,
        redis_config: RedisConf,
    ) -> FastAPI:
        """Create FastAPI app with A2A handlers.

        Args:
            service: The tRPC A2A service instance
            service_adapter: The tRPC service adapter
            timeout: Request timeout in milliseconds
            service_name: Name of the service
            addr: Address string for logging

        Returns:
            FastAPI application instance
        """
        logger.info(f"[A2A] Creating FastAPI app for service '{service_config.name}'")

        # Get agent card
        try:
            agent_card = await service.get_agent_card()
            # if not set, inject service's ip:port into agent card url
            if not agent_card.url:
                agent_card.url = f"http://{service_config.ip}:{service_config.port}"
        except Exception as e:
            logger.error(f"[A2A] Failed to get agent card from service: {e}")
            raise

        # Create and return app
        app_instance = cls(
            agent_card=agent_card,
            service=service,
            service_config=service_config,
            redis_config=redis_config,
        )

        logger.info(f"[A2A] FastAPI app created successfully for service '{service_config.name}'")
        app = app_instance.build()
        FastAPIInstrumentor.instrument_app(app)
        return app
