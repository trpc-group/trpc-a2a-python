# Tencent is pleased to support the open source community by making tRPC-A2A-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-A2A-Python is licensed under Apache-2.0.
"""Basic A2A client for testing text communication with tRPC-A2A server."""

import asyncio
from uuid import uuid4
from typing import Optional

from trpc_sdk.abc import TrpcContext
from trpc_sdk.log import logger
from trpc_sdk.config import TrpcConfig
from trpc_sdk.plugin import init_plugins
from trpc_sdk.exceptions import TrpcException

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
)

from trpc_a2a.client import TrpcA2AClient, TrpcA2ACardResolver


class BasicTrpcA2AClient:
    """Basic A2A client for testing text communication using tRPC-A2A."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.a2a_client: Optional[TrpcA2AClient] = None
        self.card_resolver: Optional[TrpcA2ACardResolver] = None
        self.agent_card = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # tRPC client cleanup is handled automatically
        pass

    async def initialize(self):
        """Initialize the client with agent card discovery."""
        logger.info("Initializing Basic A2A client...")

        try:
            # Create card resolver
            self.card_resolver = TrpcA2ACardResolver()

            # Create tRPC context
            ctx = TrpcContext()

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

        except TrpcException as e:
            logger.error(f"Failed to initialize client (TRPC error): {e}")
            return False
        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"Failed to initialize client: {e}")
            return False

    async def test_send_message(self, input_text: str) -> bool:
        """Test non-streaming send_message."""
        logger.info(f"\n--- Testing send_message with input: '{input_text}' ---")

        try:
            # Create message
            message_parts = [Part(root=TextPart(text=input_text))]
            message = Message(role=Role.user, message_id=str(uuid4()), parts=message_parts)
            request = SendMessageRequest(id=str(uuid4()), params=MessageSendParams(message=message))

            logger.info("Sending message via send_message...")
            response = await self.a2a_client.send_message(TrpcContext(), request)

            result = response.root.result

            if isinstance(result, Task):
                task = result
                logger.info(f"Task created: {task.id}")
                logger.info(f"Status: {task.status.state}")

                # Check for artifacts
                if task.artifacts:
                    for artifact in task.artifacts:
                        for part in artifact.parts:
                            if isinstance(part.root, TextPart):
                                logger.info(f"Response: {part.root.text}")

                return True

            elif isinstance(result, Message):
                msg = result
                for part in msg.parts:
                    if isinstance(part.root, TextPart):
                        logger.info(f"Direct response: {part.root.text}")
                return True

            return False

        except TrpcException as e:
            logger.error(f"send_message test error: {e}")
            return False
        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"send_message test error: {e}")
            return False

    async def test_send_message_streaming(self, input_text: str) -> bool:
        """Test streaming send_message_streaming."""
        logger.info(f"\n--- Testing send_message_streaming with input: '{input_text}' ---")

        try:
            # Create message
            message_parts = [Part(root=TextPart(text=input_text))]
            message = Message(role=Role.user, message_id=str(uuid4()), parts=message_parts)
            streaming_request = SendStreamingMessageRequest(id=str(uuid4()), params=MessageSendParams(message=message))

            logger.info("Sending message via send_message_streaming...")
            event_count = 0
            final_result = None

            async for response in self.a2a_client.send_message_streaming(TrpcContext(), streaming_request):
                event_count += 1

                result = response.root.result

                if isinstance(result, TaskStatusUpdateEvent):
                    logger.info(f"[Event {event_count}] Status: {result.status.state}")
                    if result.status.message:
                        for part in result.status.message.parts:
                            if isinstance(part.root, TextPart):
                                logger.info(f"  Message: {part.root.text}")
                    if result.final:
                        final_result = result
                        break

                elif isinstance(result, TaskArtifactUpdateEvent):
                    logger.info(f"[Event {event_count}] Artifact: {result.artifact.name}")
                    for part in result.artifact.parts:
                        if isinstance(part.root, TextPart):
                            logger.info(f"  Content: {part.root.text}")

                else:  # Task or Message
                    logger.info(f"[Event {event_count}] Result: {type(result).__name__}")
                    final_result = result

            logger.info(f"Streaming completed with {event_count} events")
            return final_result is not None

        except TrpcException as e:
            logger.error(f"send_message_streaming test error: {e}")
            return False
        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"send_message_streaming test error: {e}")
            return False

    async def run_basic_tests(self):
        """Run all basic text communication tests."""
        logger.info("\n🚀 Starting Basic A2A Communication Tests")

        success = await self.initialize()
        if not success:
            logger.error("❌ Failed to initialize client")
            return False

        # Test cases for basic communication
        test_cases = [
            "Hello",
            "echo: test message",
        ]

        overall_success = True

        for i, test_input in enumerate(test_cases, 1):
            logger.info(f"\n=== Test Case {i}/{len(test_cases)} ===")

            # Test both send_message and send_message_streaming
            success_regular = await self.test_send_message(test_input)
            success_streaming = await self.test_send_message_streaming(test_input)

            if success_regular and success_streaming:
                logger.info(f"✅ Test case {i} passed (both regular and streaming)")
            else:
                logger.error(f"❌ Test case {i} failed")
                logger.error(f"  Regular: {'✅' if success_regular else '❌'}")
                logger.error(f"  Streaming: {'✅' if success_streaming else '❌'}")
                overall_success = False

            # Brief pause between tests
            await asyncio.sleep(1)

        logger.info("\n🏁 Basic tests completed")
        logger.info(f"Overall result: {'✅ PASSED' if overall_success else '❌ FAILED'}")

        return overall_success


async def main():
    """Main function to run the basic A2A tests."""
    # Setup tRPC-Python environment
    TrpcConfig.load("examples/clients/trpc_python.yaml", "utf-8")
    init_plugins()

    # Run tRPC-A2A client
    async with BasicTrpcA2AClient(service_name="trpc.a2a_test.test_a2a_agent") as client:
        try:
            success = await client.run_basic_tests()
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
