# -*- coding: utf-8 -*-
#
# Copyright @ 2025 Tencent.com
"""Error A2A agent implementation for testing error scenarios."""

from trpc.log import logger
from trpc.trpc_abc.context import Context

from a2a.types import AgentCard, AgentCapabilities, AgentSkill, TextPart, Part, TaskState
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.utils import new_agent_text_message, new_task

from trpc_fastapi import fastapi_route
from trpc_fastapi import get_trpc_ctx

from trpc_a2a.server import TrpcA2AService
from trpc_a2a.server import get_a2a_request_context
from trpc_a2a.server import register_service


class ErrorAgentService(TrpcA2AService):
    """Error A2A agent for testing error handling scenarios."""

    async def get_agent_card(self) -> AgentCard:
        return AgentCard(
            name="Error Handling Agent",
            description="An agent for testing error handling scenarios",
            url="",  # required, but recommended to keep it empty, will use service's ip:port in trpc_python.yaml
            version="1.0.0",
            default_input_modes=["text"],
            default_output_modes=["text"],
            capabilities=AgentCapabilities(streaming=False),
            skills=[
                AgentSkill(
                    id="error_test",
                    name="Error Testing",
                    description="Tests error throwing scenarios",
                    tags=["error", "test"],
                ),
            ],
        )

    async def execute(self, context: Context, event_queue: EventQueue) -> None:
        a2a_context = get_a2a_request_context(context)

        user_input = a2a_context.get_user_input()
        task = a2a_context.current_task or new_task(a2a_context.message)
        await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)

        try:
            input_lower = user_input.lower()

            if "error" in input_lower:
                # Simulate an error
                logger.info(f"[ErrorAgent] Simulating error for input: {user_input}")
                raise ValueError("Simulated error for testing error handling")
            else:
                # Normal successful response
                await updater.add_artifact(
                    [
                        Part(root=TextPart(text=f"Successfully processed: {user_input}. "
                                           f"Send message with 'error' to test error handling."))
                    ],
                    name="response",
                )
                await updater.complete()

        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"[ErrorAgent] Error occurred: {e}")
            await updater.update_status(
                TaskState.failed,
                new_agent_text_message(f"Agent failed with error: {str(e)}", task.context_id, task.id),
                final=True,
            )

    async def cancel(self, context: Context, event_queue: EventQueue) -> None:
        a2a_context = get_a2a_request_context(context)

        task = a2a_context.current_task
        if not task:
            return

        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.update_status(
            TaskState.canceled,
            new_agent_text_message("Error agent cancelled", task.context_id, task.id),
            final=True,
        )


register_service("trpc.a2a_test.test_a2a_agent", ErrorAgentService())


@fastapi_route("/hello", ["GET"], route_params={'response_model': dict})
async def hello() -> dict:
    trpc_ctx = get_trpc_ctx()
    logger.info(f"Request from {trpc_ctx.remote_ip}")
    return {"message": "hello world", "remote_ip": trpc_ctx.remote_ip}
