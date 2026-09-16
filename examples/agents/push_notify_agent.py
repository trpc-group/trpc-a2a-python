# -*- coding: utf-8 -*-
#
# Copyright @ 2025 Tencent.com
"""Example A2A agent implementation demonstrating multi-step processes with push notifications using tRPC-A2A."""

import asyncio

from trpc.log import logger
from trpc.trpc_abc.context import Context

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


class PushNotifyAgentService(TrpcA2AService):
    """A2A agent that demonstrates multi-step processes with push notifications.

    This agent leverages the a2a-sdk's built-in push notification system.
    Push notifications are sent automatically by the framework whenever
    the task is updated via TaskUpdater.
    """

    def __init__(self):
        """Initialize the push notification agent."""
        super().__init__()
        logger.info("[PushNotifyAgent] Initializing Push Notification Agent")
        logger.info("[PushNotifyAgent] Agent initialization completed")

    async def get_agent_card(self) -> AgentCard:
        """Return the agent card metadata with push notifications enabled."""
        logger.info("[PushNotifyAgent] Agent card requested")

        agent_card = AgentCard(
            name="Push Notification Agent",
            description="An example agent demonstrating multi-step processes with push notifications",
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
                    id="multi_step",
                    name="Multi-Step Process",
                    description="Demonstrates multi-step process with push notifications",
                    tags=["multi-step", "notifications"],
                ),
            ],
        )

        logger.debug(f"[PushNotifyAgent] Returning agent card: {agent_card.name} v{agent_card.version}")
        return agent_card

    async def execute(self, context: Context, event_queue: EventQueue) -> None:
        """Execute the agent's multi-step process logic.

        The framework automatically sends push notifications whenever we update
        the task status or add artifacts via the TaskUpdater.
        """
        logger.info("[PushNotifyAgent] Starting execute method")

        # Get A2A request context
        a2a_context = get_a2a_request_context(context)
        logger.debug("[PushNotifyAgent] Retrieved A2A request context")

        # Get or create task
        task = a2a_context.current_task or new_task(a2a_context.message)
        await event_queue.enqueue_event(task)
        logger.info(f"[PushNotifyAgent] execute task {task.id}")

        # Create task updater - this is how we interact with the task
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        logger.debug(f"[PushNotifyAgent] Created task updater for task {task.id}")

        try:
            logger.info(f"[PushNotifyAgent] Starting task processing for {task.id}")

            # Update status to working - this will automatically trigger push notification
            await updater.update_status(
                TaskState.working,
                new_agent_text_message("Starting multi-step task processing...", task.context_id, task.id),
            )
            logger.info(f"[PushNotifyAgent] Updated task {task.id} status to working")

            # Execute multi-step process - each update triggers automatic push notifications
            await self._handle_multi_step(task.id, updater)

            # Complete the task - this will trigger final push notification
            await updater.complete()

            logger.info(f"[PushNotifyAgent] Task {task.id} completed successfully")

        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"[PushNotifyAgent] Error processing task {task.id}: {e}", exc_info=True)
            # Update status to failed - this will trigger error push notification
            await updater.update_status(
                TaskState.failed,
                new_agent_text_message(f"Error: {str(e)}", task.context_id, task.id),
                final=True,
            )

    async def cancel(self, context: Context, event_queue: EventQueue) -> None:
        """Cancel an ongoing task.

        Cancellation status update will also trigger automatic push notification.
        """
        logger.info("[PushNotifyAgent] Cancel method called")

        # Get A2A request context
        a2a_context = get_a2a_request_context(context)

        task = a2a_context.current_task
        if not task:
            logger.error("[PushNotifyAgent] No task to cancel - task is None")
            return

        logger.info(f"[PushNotifyAgent] Cancelling task {task.id}")

        # Create task updater
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        logger.debug(f"[PushNotifyAgent] Created task updater for cancellation of task {task.id}")

        # Update status to cancelled - this will trigger automatic push notification
        await updater.update_status(
            TaskState.canceled,
            new_agent_text_message("Task cancelled by user", task.context_id, task.id),
            final=True,
        )
        logger.info(f"[PushNotifyAgent] Updated task {task.id} status to cancelled")

        logger.info(f"[PushNotifyAgent] Task {task.id} cancellation completed")

    async def _handle_multi_step(self, task_id: str, updater: TaskUpdater) -> None:
        """Handle multi-step process.

        Each status update and artifact addition automatically triggers
        push notifications via the a2a framework.
        """
        logger.info(f"[PushNotifyAgent] Starting multi-step process for task {task_id}")

        processes = [
            ("Data Validation", 3),
            ("Preprocessing", 4),
            ("Main Processing", 6),
            ("Quality Check", 2),
            ("Delivery", 1),
        ]

        total_time = sum(time for _, time in processes)
        elapsed_time = 0

        logger.info(f"[PushNotifyAgent] Task {task_id}: Will execute {len(processes)} processes "
                    f"with total estimated time: {total_time}s")

        for i, (process_name, duration) in enumerate(processes, 1):
            logger.info(f"[PushNotifyAgent] Task {task_id}: Starting step {i}/{len(processes)}: "
                        f"{process_name} (estimated: {duration}s)")

            # Update status for this step - triggers automatic push notification
            await updater.update_status(
                TaskState.working,
                new_agent_text_message(f"Step {i}/{len(processes)}: Starting {process_name}", task_id, task_id),
            )

            # Add artifact for process start - triggers automatic push notification
            start_text = (f"Starting: {process_name}\n"
                          f"Estimated duration: {duration}s\n"
                          f"Overall progress: {(elapsed_time / total_time) * 100:.1f}%")
            await updater.add_artifact(
                [Part(root=TextPart(text=start_text))],
                name=f"process_{process_name.lower().replace(' ', '_')}_start",
            )
            logger.debug(f"[PushNotifyAgent] Task {task_id}: Added start artifact for {process_name}")

            logger.debug(f"[PushNotifyAgent] Task {task_id}: Simulating work for {process_name} ({duration}s)")
            await asyncio.sleep(duration)
            elapsed_time += duration

            # Add completion artifact - triggers automatic push notification
            complete_text = (f"Completed: {process_name} ✓\n"
                             f"Duration: {duration}s\n"
                             f"Overall progress: {(elapsed_time / total_time) * 100:.1f}%")
            await updater.add_artifact(
                [Part(root=TextPart(text=complete_text))],
                name=f"process_{process_name.lower().replace(' ', '_')}_complete",
            )
            logger.debug(f"[PushNotifyAgent] Task {task_id}: Added completion artifact for {process_name}")

            logger.info(f"[PushNotifyAgent] Task {task_id}: Completed step {i}/{len(processes)}: "
                        f"{process_name} (progress: {(elapsed_time / total_time) * 100:.1f}%)")

        # Final status update
        await updater.update_status(
            TaskState.working,
            new_agent_text_message("All processing steps completed successfully!", task_id, task_id),
        )

        logger.info(f"[PushNotifyAgent] Task {task_id}: Multi-step process completed successfully in {elapsed_time}s")


register_service("trpc.a2a_test.test_a2a_agent", PushNotifyAgentService())


@fastapi_route("/hello", ["GET"], route_params={'response_model': dict})
async def hello() -> dict:
    trpc_ctx = get_trpc_ctx()
    logger.info(f"Request from {trpc_ctx.remote_ip}")
    return {"message": "hello world", "remote_ip": trpc_ctx.remote_ip}
