# -*- coding: utf-8 -*-
#
# Copyright @ 2025 Tencent.com
"""Multi-turn A2A client for testing interactive conversation with tRPC-A2A server."""

import asyncio
import argparse
from uuid import uuid4
from typing import Optional, List

from trpc.trpc_abc.context import Context
from trpc.log import logger
from trpc import config
from trpc.plugin import setup
from trpc.exceptions import TRPCBaseError

from a2a.types import (
    Message,
    TextPart,
    Part,
    Role,
    MessageSendParams,
    SendMessageRequest,
    SendStreamingMessageRequest,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    Task,
    TaskState,
)

from trpc_a2a.client import TrpcA2AClient, TrpcA2ACardResolver


class MultiTurnTrpcA2AClient:
    """Multi-turn A2A client for testing interactive conversation."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.a2a_client: Optional[TrpcA2AClient] = None
        self.card_resolver: Optional[TrpcA2ACardResolver] = None
        self.agent_card = None
        self.current_task_id: Optional[str] = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # tRPC client cleanup is handled automatically
        pass

    async def initialize(self):
        """Initialize the client with agent card discovery."""
        logger.info("Initializing Multi-turn A2A client...")

        try:
            # Create card resolver
            self.card_resolver = TrpcA2ACardResolver()

            # Create tRPC context
            ctx = Context()

            # Get agent card using the resolver
            # Use the agent service approach for discovery
            resolver_result = await self.card_resolver.get_from_agent_service(ctx, self.service_name)
            self.agent_card = resolver_result.card

            logger.info(f"Agent Name: {self.agent_card.name}")
            logger.info(f"Description: {self.agent_card.description}")
            logger.info(f"Version: {self.agent_card.version}")
            logger.info(f"Streaming: {self.agent_card.capabilities.streaming}")

            # Create A2A client using the resolver result
            self.a2a_client = TrpcA2AClient(service_name=self.service_name, resolver_result=resolver_result)

            return True

        except TRPCBaseError as e:
            logger.error(f"Failed to initialize client (TRPC error): {e}")
            return False
        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"Failed to initialize client: {e}")
            return False

    async def test_send_message(self, input_text: str) -> tuple[bool, Optional[str]]:
        """Test non-streaming send_message and return success status and response."""
        logger.info(f"\n--- Testing send_message with input: '{input_text}' ---")
        logger.info(f"Current task ID: {self.current_task_id or 'None (new conversation)'}")

        try:
            # Create message
            message_parts = [Part(root=TextPart(text=input_text))]
            message = Message(role=Role.user, message_id=str(uuid4()), parts=message_parts)

            # Include task ID if this is a continuation of a conversation
            if self.current_task_id:
                message.task_id = self.current_task_id

            request = SendMessageRequest(id=str(uuid4()), params=MessageSendParams(message=message))

            logger.info("Sending message via send_message...")
            response = await self.a2a_client.send_message(Context(), request)

            result = response.root.result
            response_text = ""

            if isinstance(result, Task):
                task = result
                logger.info(f"Task received: {task.id}")
                logger.info(f"Status: {task.status.state}")

                # Store the task ID for subsequent messages in this conversation
                self.current_task_id = task.id

                # Check for artifacts
                if task.artifacts:
                    for artifact in task.artifacts:
                        for part in artifact.parts:
                            if isinstance(part.root, TextPart):
                                response_text = part.root.text
                                logger.info(f"Response: {response_text}")

                # Check if task requires input (multi-turn scenario)
                if task.status.state == TaskState.input_required:
                    logger.info("Task requires additional input (multi-turn scenario)")

            elif isinstance(result, Message):
                msg = result
                for part in msg.parts:
                    if isinstance(part.root, TextPart):
                        response_text = part.root.text
                        logger.info(f"Direct response: {response_text}")

            return True, response_text

        except TRPCBaseError as e:
            logger.error(f"send_message test error: {e}")
            return False, None
        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"send_message test error: {e}")
            return False, None

    async def test_send_message_streaming(self, input_text: str) -> tuple[bool, Optional[str]]:
        """Test streaming send_message_streaming and return success status and response."""
        logger.info(f"\n--- Testing send_message_streaming with input: '{input_text}' ---")
        logger.info(f"Current task ID: {self.current_task_id or 'None (new conversation)'}")

        try:
            # Create message
            message_parts = [Part(root=TextPart(text=input_text))]
            message = Message(role=Role.user, message_id=str(uuid4()), parts=message_parts)

            # Include task ID if this is a continuation of a conversation
            if self.current_task_id:
                message.task_id = self.current_task_id

            streaming_request = SendStreamingMessageRequest(id=str(uuid4()), params=MessageSendParams(message=message))

            logger.info("Sending message via send_message_streaming...")
            event_count = 0
            final_result = None
            response_text = ""

            async for response in self.a2a_client.send_message_streaming(Context(), streaming_request):
                event_count += 1

                result = response.root.result

                if isinstance(result, TaskStatusUpdateEvent):
                    logger.info(f"[Event {event_count}] Status: {result.status.state}")

                    # Store task ID from the task status update
                    if not self.current_task_id and result.task_id:
                        self.current_task_id = result.task_id
                        logger.info(f"Setting task ID from status update: {self.current_task_id}")

                    if result.status.message:
                        for part in result.status.message.parts:
                            if isinstance(part.root, TextPart):
                                logger.info(f"  Message: {part.root.text}")
                    if result.final:
                        final_result = result
                        break

                elif isinstance(result, TaskArtifactUpdateEvent):
                    logger.info(f"[Event {event_count}] Artifact: {result.artifact.name}")

                    # Store task ID from the artifact update
                    if not self.current_task_id and result.task_id:
                        self.current_task_id = result.task_id
                        logger.info(f"Setting task ID from artifact update: {self.current_task_id}")

                    for part in result.artifact.parts:
                        if isinstance(part.root, TextPart):
                            response_text = part.root.text
                            logger.info(f"  Content: {response_text}")

                else:  # Task or Message
                    logger.info(f"[Event {event_count}] Result: {type(result).__name__}")

                    # If we received a Task, store its ID
                    if isinstance(result, Task) and not self.current_task_id:
                        self.current_task_id = result.id
                        logger.info(f"Setting task ID from result: {self.current_task_id}")

                    final_result = result

            logger.info(f"Streaming completed with {event_count} events")

            success = final_result is not None
            return success, response_text

        except TRPCBaseError as e:
            logger.error(f"send_message_streaming test error: {e}")
            return False, None
        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"send_message_streaming test error: {e}")
            return False, None

    async def run_conversation_scenario(self,
                                        scenario_name: str,
                                        initial_prompt: str,
                                        follow_ups: List[str],
                                        use_streaming: bool = False) -> bool:
        """Run a complete conversation scenario."""
        logger.info(f"\n=== Running {scenario_name} Scenario ({'streaming' if use_streaming else 'regular'}) ===")

        # Reset task ID at the start of a new conversation scenario
        self.current_task_id = None
        logger.info("Reset task ID for new conversation scenario")

        overall_success = True

        # Start the conversation
        if use_streaming:
            success, response = await self.test_send_message_streaming(initial_prompt)
        else:
            success, response = await self.test_send_message(initial_prompt)

        if not success:
            logger.error(f"❌ Failed to start {scenario_name}")
            return False

        logger.info(f"✅ Started {scenario_name} successfully")
        logger.info(f"Conversation task ID: {self.current_task_id}")

        # Continue with follow-up messages
        for i, follow_up in enumerate(follow_ups, 1):
            logger.info(f"\n--- Follow-up {i}/{len(follow_ups)} ---")
            logger.info(f"Using task ID: {self.current_task_id}")

            # Brief pause between messages
            await asyncio.sleep(1)

            if use_streaming:
                success, response = await self.test_send_message_streaming(follow_up)
            else:
                success, response = await self.test_send_message(follow_up)

            if success:
                logger.info(f"✅ Follow-up {i} successful")
            else:
                logger.error(f"❌ Follow-up {i} failed")
                overall_success = False

        return overall_success

    async def run_multiturn_tests(self):
        """Run all multi-turn conversation tests."""
        logger.info("\n🚀 Starting Multi-turn A2A Conversation Tests")

        success = await self.initialize()
        if not success:
            logger.error("❌ Failed to initialize client")
            return False

        # Define conversation scenarios
        scenarios = [{
            "name": "Quiz Interaction",
            "initial": "start quiz",
            "follow_ups": ["4", "paris"],
        }]

        overall_success = True

        for i, scenario in enumerate(scenarios, 1):
            logger.info(f"\n=== Scenario {i}/{len(scenarios)}: {scenario['name']} ===")

            # Test both regular and streaming for each scenario
            regular_success = await self.run_conversation_scenario(scenario["name"],
                                                                   scenario["initial"],
                                                                   scenario["follow_ups"],
                                                                   use_streaming=False)

            # Clear state between tests
            self.current_task_id = None
            await asyncio.sleep(2)

            streaming_success = await self.run_conversation_scenario(scenario["name"],
                                                                     scenario["initial"],
                                                                     scenario["follow_ups"],
                                                                     use_streaming=True)

            if regular_success and streaming_success:
                logger.info(f"✅ Scenario {i} passed (both regular and streaming)")
            else:
                logger.error(f"❌ Scenario {i} failed")
                logger.error(f"  Regular: {'✅' if regular_success else '❌'}")
                logger.error(f"  Streaming: {'✅' if streaming_success else '❌'}")
                overall_success = False

            # Clear state after each scenario
            self.current_task_id = None
            await asyncio.sleep(2)

        logger.info("\n🏁 Multi-turn conversation tests completed")
        logger.info(f"Overall result: {'✅ PASSED' if overall_success else '❌ FAILED'}")

        return overall_success


async def main():
    """Main function to run the multi-turn A2A tests."""
    parser = argparse.ArgumentParser(description="Multi-turn A2A Client Tester")
    parser.add_argument(
        "--service",
        default="trpc.a2a_test.test_a2a_agent",
        help="Service name of the tRPC-A2A agent (default: trpc.a2a_test.test_a2a_agent)",
    )

    args = parser.parse_args()

    # Setup tRPC-Python environment
    config.load_global_config("examples/clients/trpc_python.yaml", "utf-8")
    setup()

    # Run tRPC-A2A client
    async with MultiTurnTrpcA2AClient(service_name=args.service) as client:
        try:
            success = await client.run_multiturn_tests()
            return 0 if success else 1

        except KeyboardInterrupt:
            logger.info("\n⚠️ Tests interrupted by user")
            return 1
        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"\n💥 Unexpected error: {e}")
            return 1


if __name__ == "__main__":
    import sys

    exit_code = asyncio.run(main())
    sys.exit(exit_code)
