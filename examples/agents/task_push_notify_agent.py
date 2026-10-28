# Tencent is pleased to support the open source community by making tRPC-A2A-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-A2A-Python is licensed under Apache-2.0.
"""Example A2A agent for demonstrating task-specific push notifications in multi-turn scenarios."""

import asyncio

from trpc_sdk.log import logger
from trpc_sdk.abc import TrpcContext

from a2a.types import (
    AgentCard,
    AgentCapabilities,
    AgentSkill,
    TextPart,
    Part,
    TaskState,
)
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.utils import new_agent_text_message, new_task

from trpc_fastapi import fastapi_route
from trpc_fastapi import get_trpc_ctx

from trpc_a2a.server import TrpcA2AService
from trpc_a2a.server import get_a2a_request_context
from trpc_a2a.server import register_service


class TaskPushNotifyAgentService(TrpcA2AService):
    """A2A agent that demonstrates task-specific push notifications in multi-turn scenarios.

    This agent shows how push notifications can be set up for specific tasks after
    they are created, which is useful in multi-turn conversations where the client
    first creates a task and then configures push notifications for it.
    """

    def __init__(self):
        super().__init__()
        """Initialize the task push notification agent."""
        logger.info("[TaskPushNotifyAgent] Initializing Task Push Notification Agent")
        self.conversation_state = {}
        logger.info("[TaskPushNotifyAgent] Agent initialization completed")

    async def get_agent_card(self) -> AgentCard:
        """Return the agent card metadata with push notifications enabled."""
        logger.info("[TaskPushNotifyAgent] Agent card requested")

        agent_card = AgentCard(
            name="Task Push Notification Agent",
            description="An example agent demonstrating task-specific push notifications in multi-turn scenarios",
            url="",  # required, but recommended to keep it empty, will use service's ip:port in trpc_python.yaml
            version="1.0.0",
            default_input_modes=["text", "text/plain"],
            default_output_modes=["text", "text/plain"],
            capabilities=AgentCapabilities(
                streaming=True,
                pushNotifications=True,
            ),
            skills=[
                AgentSkill(
                    id="task_processing",
                    name="Task Processing with Notifications",
                    description="Demonstrates task-specific push notifications in multi-turn scenarios",
                    tags=["multi-turn", "task-notifications"],
                ),
            ],
        )

        logger.debug(f"[TaskPushNotifyAgent] Returning agent card: {agent_card.name} v{agent_card.version}")
        return agent_card

    async def execute(self, context: TrpcContext, event_queue: EventQueue) -> None:
        """Execute the agent's multi-turn logic with task-specific push notifications."""
        logger.info("[TaskPushNotifyAgent] Starting execute method")

        # Get A2A request context
        a2a_context = get_a2a_request_context(context)
        logger.debug("[TaskPushNotifyAgent] Retrieved A2A request context")

        task = a2a_context.current_task
        user_input = a2a_context.get_user_input()

        if not task:
            # Create new task and ask for input
            task = new_task(a2a_context.message)
            await event_queue.enqueue_event(task)
            logger.info(f"[TaskPushNotifyAgent] Created new task {task.id}")

            # Initialize conversation state
            self.conversation_state[task.id] = {"state": "waiting_for_input"}

            # Create task updater
            updater = TaskUpdater(event_queue, task.id, task.context_id)

            # Ask for user input - this will require the client to set up push notifications
            # and then provide input in a subsequent message
            await updater.update_status(
                TaskState.input_required,
                new_agent_text_message(
                    "Hello! I'm ready to process your request. Please provide your task description "
                    "(e.g., 'analyze data', 'generate report', etc.)",
                    task.context_id,
                    task.id,
                ),
                final=True,
            )
            logger.info(f"[TaskPushNotifyAgent] Task {task.id} is waiting for user input")

        else:
            # Continue with existing task - process the user input
            logger.info(f"[TaskPushNotifyAgent] Continuing task {task.id} with input: '{user_input}'")

            # Ensure we have state for this task
            if task.id not in self.conversation_state:
                self.conversation_state[task.id] = {"state": "waiting_for_input"}

            # Create task updater
            updater = TaskUpdater(event_queue, task.id, task.context_id)

            try:
                # Start processing with push notifications
                await updater.update_status(
                    TaskState.working,
                    new_agent_text_message(f"Processing your request: '{user_input}'", task.context_id, task.id),
                )
                logger.info(f"[TaskPushNotifyAgent] Started processing task {task.id}")

                # Execute the processing steps with push notifications
                await self._process_user_request(task.id, user_input, updater)

                # Complete the task
                await updater.complete()
                logger.info(f"[TaskPushNotifyAgent] Task {task.id} completed successfully")

                # Clean up conversation state
                if task.id in self.conversation_state:
                    del self.conversation_state[task.id]

            except Exception as e:  # pylint: disable=broad-except
                logger.error(f"[TaskPushNotifyAgent] Error processing task {task.id}: {e}", exc_info=True)
                await updater.update_status(
                    TaskState.failed,
                    new_agent_text_message(f"Error processing request: {str(e)}", task.context_id, task.id),
                    final=True,
                )

    async def cancel(self, context: TrpcContext, event_queue: EventQueue) -> None:
        """Cancel an ongoing task."""
        logger.info("[TaskPushNotifyAgent] Cancel method called")

        # Get A2A request context
        a2a_context = get_a2a_request_context(context)

        task = a2a_context.current_task
        if not task:
            logger.error("[TaskPushNotifyAgent] No task to cancel - task is None")
            return

        logger.info(f"[TaskPushNotifyAgent] Cancelling task {task.id}")

        # Clean up conversation state
        if task.id in self.conversation_state:
            del self.conversation_state[task.id]
            logger.info(f"[TaskPushNotifyAgent] Cleaned up conversation state for task {task.id}")

        # Create task updater
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        # Update status to cancelled
        await updater.update_status(
            TaskState.canceled,
            new_agent_text_message("Task cancelled by user", task.context_id, task.id),
            final=True,
        )
        logger.info(f"[TaskPushNotifyAgent] Task {task.id} cancellation completed")

    async def _process_user_request(self, task_id: str, user_input: str, updater: TaskUpdater) -> None:
        """Process the user request with push notifications."""
        logger.info(f"[TaskPushNotifyAgent] Processing user request for task {task_id}: '{user_input}'")

        steps = [
            ("Initializing", 1),
            ("Processing", 3),
            ("Finalizing", 1),
        ]

        for i, (step_name, duration) in enumerate(steps, 1):
            logger.info(f"[TaskPushNotifyAgent] Task {task_id}: Step {i}/{len(steps)}: {step_name}")

            await updater.update_status(
                TaskState.working,
                new_agent_text_message(f"Step {i}/{len(steps)}: {step_name}", task_id, task_id),
            )

            await updater.add_artifact(
                [Part(root=TextPart(text=f"Processing step: {step_name}\nProgress: {i}/{len(steps)}"))],
                name=f"processing_step_{i}",
            )

            await asyncio.sleep(duration)

        # Final result
        await updater.add_artifact(
            [Part(root=TextPart(text="Processing completed successfully!\nTask has been fulfilled."))],
            name="processing_result",
        )

        logger.info(f"[TaskPushNotifyAgent] Completed processing for task {task_id}")


register_service("trpc.a2a_test.test_a2a_agent", TaskPushNotifyAgentService())


@fastapi_route("/hello", ["GET"], route_params={'response_model': dict})
async def hello() -> dict:
    trpc_ctx = get_trpc_ctx()
    logger.info(f"Request from {trpc_ctx.remote_ip}")
    return {"message": "hello world", "remote_ip": trpc_ctx.remote_ip}
