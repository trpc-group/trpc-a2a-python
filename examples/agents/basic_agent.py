# -*- coding: utf-8 -*-
#
# Copyright @ 2025 Tencent.com
"""Example A2A agent implementation using tRPC-A2A."""

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


class BasicAgentService(TrpcA2AService):
    """Example A2A agent that provides simple responses."""

    async def get_agent_card(self) -> AgentCard:
        """Return the agent card metadata."""
        return AgentCard(
            name="Basic Agent",
            description="An example agent demonstrating tRPC-A2A integration",
            url="",  # required, but recommended to keep it empty, will use service's ip:port in trpc_python.yaml
            version="1.0.0",
            default_input_modes=["text", "text/plain"],
            default_output_modes=["text", "text/plain"],
            capabilities=AgentCapabilities(streaming=True),
            skills=[
                AgentSkill(
                    id="greet",
                    name="Greeting",
                    description="Provides friendly greetings",
                    tags=["greeting", "hello"],
                ),
                AgentSkill(
                    id="echo",
                    name="Echo",
                    description="Echoes back the user's message",
                    tags=["echo", "repeat"],
                ),
            ],
        )

    async def execute(self, context: Context, event_queue: EventQueue) -> None:
        """Execute the agent's logic."""
        # Get A2A request context
        a2a_context = get_a2a_request_context(context)

        # Get user input
        user_input = a2a_context.get_user_input()
        logger.info(f"[BasicAgent] Received input: {user_input}")

        # Get or create task
        task = a2a_context.current_task or new_task(a2a_context.message)
        await event_queue.enqueue_event(task)

        # Create task updater
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        try:
            # Update status to working
            await updater.update_status(
                TaskState.working,
                new_agent_text_message("Processing your request...", task.context_id, task.id),
            )

            # Process the input
            response = self._process_input(user_input)

            # Add response as artifact
            await updater.add_artifact(
                [Part(root=TextPart(text=response))],
                name="response",
            )

            # Complete the task
            await updater.complete()

            logger.info(f"[BasicAgent] Task {task.id} completed successfully")

        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"[BasicAgent] Error processing request: {e}")
            await updater.update_status(
                TaskState.failed,
                new_agent_text_message(f"Error: {str(e)}", task.context_id, task.id),
                final=True,
            )

    async def cancel(self, context: Context, event_queue: EventQueue) -> None:
        """Cancel an ongoing task."""
        # Get A2A request context
        a2a_context = get_a2a_request_context(context)

        task = a2a_context.current_task
        if not task:
            logger.error("No task to cancel")
            return

        logger.info(f"[BasicAgent] Cancelling task {task.id}")

        # Create task updater
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        # Update status to cancelled
        await updater.update_status(
            TaskState.canceled,
            new_agent_text_message("Task cancelled by user", task.context_id, task.id),
            final=True,
        )

    def _process_input(self, user_input: str) -> str:
        """Simple input processing logic."""
        input_lower = user_input.lower().strip()

        # Greeting responses
        if any(word in input_lower for word in ["hello", "hi", "greet", "hey"]):
            return "Hello! I'm your tRPC-A2A agent. How can I help you today?"

        # Echo responses
        if input_lower.startswith("echo:"):
            # Extract the message to echo
            if ":" in user_input:
                message = user_input.split(":", 1)[1].strip()
                return f"You said: {message}"

        # Default response
        return (f"I received your message: '{user_input}'. "
                "I can greet you or echo your messages. "
                "Try saying 'hello' or 'echo: your message'.")


register_service("trpc.a2a_test.test_a2a_agent", BasicAgentService())


@fastapi_route("/hello", ["GET"], route_params={'response_model': dict})
async def hello() -> dict:
    trpc_ctx = get_trpc_ctx()
    logger.info(f"Request from {trpc_ctx.remote_ip}")
    return {"message": "hello world", "remote_ip": trpc_ctx.remote_ip}
