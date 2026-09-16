# -*- coding: utf-8 -*-
#
# Copyright @ 2025 Tencent.com
"""Streaming A2A agent implementation demonstrating real-time updates."""

import asyncio
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


class StreamingAgentService(TrpcA2AService):
    """Streaming A2A agent that provides real-time updates."""

    async def get_agent_card(self) -> AgentCard:
        """Return the agent card metadata."""
        return AgentCard(
            name="Streaming Agent",
            description="A streaming agent for testing real-time communication",
            url="",  # required, but recommended to keep it empty, will use service's ip:port in trpc_python.yaml
            version="1.0.0",
            default_input_modes=["text", "text/plain"],
            default_output_modes=["text", "text/plain"],
            capabilities=AgentCapabilities(streaming=True),
            skills=[
                AgentSkill(
                    id="progress",
                    name="Progress Task",
                    description="Simulates a long-running task with progress updates",
                    tags=["progress", "streaming", "long-running"],
                ),
            ],
        )

    async def execute(self, context: Context, event_queue: EventQueue) -> None:
        """Execute the agent's logic with streaming updates."""
        # Get A2A request context
        a2a_context = get_a2a_request_context(context)

        # Get user input
        user_input = a2a_context.get_user_input()
        logger.info(f"[StreamingAgent] Received input: {user_input}")

        # Get or create task
        task = a2a_context.current_task or new_task(a2a_context.message)
        await event_queue.enqueue_event(task)

        # Create task updater
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        try:
            # Determine task type and execute with streaming
            input_lower = user_input.lower().strip()
            logger.info(f"[StreamingAgent] Input: {input_lower}")

            await self._run_progress_task(updater, task.context_id, task.id)

            logger.info(f"[StreamingAgent] Task {task.id} completed successfully")

        except asyncio.exceptions.CancelledError:
            logger.info(f"[StreamingAgent] Task {task.id} was cancelled")
            await updater.update_status(
                TaskState.canceled,
                new_agent_text_message("Task was cancelled by user", task.context_id, task.id),
                final=True,
            )
        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"[StreamingAgent] Error processing request: {e}")
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

        logger.info(f"[StreamingAgent] Cancelling task {task.id}")

        # Create task updater
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        # Update status to cancelled
        await updater.update_status(
            TaskState.canceled,
            new_agent_text_message("Streaming task cancelled by user", task.context_id, task.id),
            final=True,
        )

    async def _run_progress_task(self, updater: TaskUpdater, context_id: str, task_id: str):
        """Simulate a long-running task with progress updates."""
        steps = [
            "Initializing...",
            "Loading data...",
            "Processing data...",
            "Analyzing results...",
            "Generating report...",
            "Finalizing...",
        ]

        for i, step in enumerate(steps):
            progress = int((i / len(steps)) * 100)
            await updater.update_status(
                TaskState.working,
                new_agent_text_message(f"[{progress}%] {step}", context_id, task_id),
            )
            logger.info(f"[StreamingAgent] Progress: {progress}%")
            await asyncio.sleep(1)  # Simulate work

        # Complete with final result
        await updater.add_artifact(
            [Part(root=TextPart(text="Progress task completed! All steps finished successfully."))],
            name="progress_result",
        )
        await updater.complete()


register_service("trpc.a2a_test.test_a2a_agent", StreamingAgentService())


@fastapi_route("/hello", ["GET"], route_params={'response_model': dict})
async def hello() -> dict:
    trpc_ctx = get_trpc_ctx()
    logger.info(f"Request from {trpc_ctx.remote_ip}")
    return {"message": "hello world", "remote_ip": trpc_ctx.remote_ip}
