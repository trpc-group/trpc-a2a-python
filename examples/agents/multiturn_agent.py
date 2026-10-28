# Tencent is pleased to support the open source community by making tRPC-A2A-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-A2A-Python is licensed under Apache-2.0.
"""Multi-turn A2A agent implementation."""

from typing import Dict, Any, AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum

from trpc_sdk.log import logger
from trpc_sdk.abc import TrpcContext

from a2a.types import AgentCard, AgentCapabilities, AgentSkill, TextPart, Part, TaskState
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.utils import new_agent_text_message, new_task

from trpc_fastapi import fastapi_route
from trpc_fastapi import get_trpc_ctx

from trpc_a2a.server import TrpcA2AService
from trpc_a2a.server import get_a2a_request_context
from trpc_a2a.server import register_service


class QuizState(Enum):
    """Quiz state enumeration."""

    INITIAL = "initial"
    QUIZ_STARTED = "quiz_started"
    QUIZ_COMPLETED = "quiz_completed"


@dataclass
class QuizSession:
    """Quiz session data."""

    state: QuizState = QuizState.INITIAL
    current_question: int = 0
    questions: list = field(default_factory=lambda: [
        {
            "question": "What is 2 + 2?",
            "answer": "4"
        },
        {
            "question": "What is the capital of France?",
            "answer": "paris"
        },
    ])


class QuizAgent:
    """Quiz agent that handles the interactive quiz logic."""

    def __init__(self):
        self.sessions: Dict[str, QuizSession] = {}

    def _get_or_create_session(self, task_id: str) -> QuizSession:
        """Get existing session or create new one."""
        if task_id not in self.sessions:
            self.sessions[task_id] = QuizSession()
        return self.sessions[task_id]

    def _cleanup_session(self, task_id: str) -> None:
        """Clean up session data."""
        if task_id in self.sessions:
            del self.sessions[task_id]

    async def stream(self, user_input: str, context_id: str, task_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream quiz responses based on user input and current state."""
        session = self._get_or_create_session(task_id)
        user_input_lower = user_input.lower()

        if "quiz" in user_input_lower:
            # Start or restart the quiz
            session.state = QuizState.QUIZ_STARTED
            session.current_question = 0
            current_question = session.questions[0]["question"]

            yield {"content": current_question, "is_task_complete": False, "require_user_input": True}

        elif session.state == QuizState.QUIZ_STARTED:
            # Process quiz answer
            current_q_idx = session.current_question
            current_question = session.questions[current_q_idx]

            if user_input_lower == current_question["answer"].lower():
                # Correct answer
                next_q_idx = current_q_idx + 1

                if next_q_idx < len(session.questions):
                    # Move to next question
                    session.current_question = next_q_idx
                    next_question = session.questions[next_q_idx]["question"]
                    response = f"Correct! Next question: {next_question}"

                    yield {"content": response, "is_task_complete": False, "require_user_input": True}
                else:
                    # End of quiz
                    session.state = QuizState.QUIZ_COMPLETED
                    self._cleanup_session(task_id)

                    yield {
                        "content": "Congratulations! You completed the quiz. Say 'quiz' to start again.",
                        "is_task_complete": True,
                        "require_user_input": False,
                    }
            else:
                # Wrong answer
                response = f"Incorrect. Try again: {current_question['question']}"

                yield {"content": response, "is_task_complete": False, "require_user_input": True}
        else:
            # Default response
            yield {
                "content": f"Received: {user_input}. Say 'quiz' to start.",
                "is_task_complete": True,
                "require_user_input": False,
            }


class MultiTurnAgentService(TrpcA2AService):
    """Multi-turn A2A agent that requires multiple interactions."""

    def __init__(self):
        super().__init__()
        self.quiz_agent = QuizAgent()
        logger.info("MultiTurnAgent initialized")

    async def get_agent_card(self) -> AgentCard:
        logger.info("Getting agent card")
        return AgentCard(
            name="Multi-Turn Agent",
            description="An agent for testing multi-turn conversations",
            url="",
            version="1.0.0",
            default_input_modes=["text"],
            default_output_modes=["text"],
            capabilities=AgentCapabilities(streaming=True),
            skills=[
                AgentSkill(
                    id="quiz",
                    name="Interactive Quiz",
                    description="Conducts an interactive quiz",
                    tags=["quiz"],
                ),
            ],
        )

    async def execute(self, context: TrpcContext, event_queue: EventQueue) -> None:
        a2a_context = get_a2a_request_context(context)
        task = a2a_context.current_task

        if not task:
            task = new_task(a2a_context.message)
            await event_queue.enqueue_event(task)
            logger.info(f"Create new task: {task.id}")

        updater = TaskUpdater(event_queue, task.id, task.context_id)
        user_input = a2a_context.get_user_input()
        logger.info(f"[Task: {task.id}] User input: '{user_input}'")

        try:
            async for item in self.quiz_agent.stream(user_input, task.context_id, task.id):
                is_task_complete = item["is_task_complete"]
                require_user_input = item["require_user_input"]
                content = item["content"]

                if not is_task_complete and not require_user_input:
                    await updater.update_status(
                        TaskState.working,
                        new_agent_text_message(content, task.context_id, task.id),
                    )
                elif require_user_input:
                    await updater.update_status(
                        TaskState.input_required,
                        new_agent_text_message(content, task.context_id, task.id),
                        final=True,
                    )
                    break
                else:
                    await updater.add_artifact(
                        [Part(root=TextPart(text=content))],
                        name="response",
                    )
                    await updater.complete()
                    break

        except Exception as e:
            logger.error(f"An error occurred while streaming the response: {e}")
            await updater.update_status(
                TaskState.error,
                new_agent_text_message("An error occurred", task.context_id, task.id),
                final=True,
            )

    async def cancel(self, context: TrpcContext, event_queue: EventQueue) -> None:
        a2a_context = get_a2a_request_context(context)
        task = a2a_context.current_task

        if not task:
            logger.info("Cancel called but no task found")
            return

        # Clean up quiz session when task is cancelled
        if task.id in self.quiz_agent.sessions:
            self.quiz_agent._cleanup_session(task.id)
            logger.info(f"[Task: {task.id}] Cleaned up quiz session on cancel")

        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.update_status(
            TaskState.canceled,
            new_agent_text_message("Agent cancelled", task.context_id, task.id),
            final=True,
        )
        logger.info(f"[Task: {task.id}] Task cancelled")


register_service("trpc.a2a_test.test_a2a_agent", MultiTurnAgentService())


@fastapi_route("/hello", ["GET"], route_params={'response_model': dict})
async def hello() -> dict:
    trpc_ctx = get_trpc_ctx()
    logger.info(f"Request from {trpc_ctx.remote_ip}")
    return {"message": "hello world", "remote_ip": trpc_ctx.remote_ip}
