# -*- coding: utf-8 -*-
#
# Copyright @ 2025 Tencent.com
"""Push notification client demonstrating push notifications with tRPC-A2A server."""

import asyncio
import json
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import uuid4

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

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
    MessageSendConfiguration,
    SendMessageRequest,
    Task,
    PushNotificationConfig,
)

from trpc_a2a.client import TrpcA2AClient, TrpcA2ACardResolver


class PushNotificationServer:
    """Webhook server to receive push notifications from the A2A agent."""

    def __init__(self, host: str = "localhost", port: int = 19080):
        self.host = host
        self.port = port
        self.app = FastAPI(title="Push Notification Webhook Server")
        self.received_notifications: List[Dict[str, Any]] = []
        self.server = None
        self.server_thread = None
        # Add task completion events - use threading.Event for cross-thread communication
        self.task_events: Dict[str, threading.Event] = {}

        # Setup webhook endpoint
        @self.app.post("/webhook")
        async def webhook_handler(request: Request):
            try:
                # Parse the notification payload - this is the complete Task object from a2a-sdk
                body = await request.body()
                task_data = json.loads(body)

                # Log the received notification
                timestamp = datetime.now().isoformat()
                notification_with_timestamp = {
                    "timestamp": timestamp,
                    "task_data": task_data,
                    "headers": dict(request.headers),
                }

                self.received_notifications.append(notification_with_timestamp)

                # Check if this notification indicates task completion
                task_id = task_data.get("id", "Unknown")
                task_state = task_data.get("status", {}).get("state", "Unknown")

                # Signal task completion if we have an event for this task
                if task_id in self.task_events and task_state == "completed":
                    self.task_events[task_id].set()
                    logger.info(f"[Webhook] Task {task_id} completed - signaling completion")

                logger.info(f"[Webhook] Received task notification: {task_id}")
                print(f"\n🔔 Push Notification Received at {timestamp}")
                print(f"   Task ID: {task_id}")
                print(f"   Status: {task_state}")

                # Show latest message if available
                if task_data.get("messages"):
                    latest_message = task_data["messages"][-1]
                    if latest_message.get("parts"):
                        for part in latest_message["parts"]:
                            if "text" in part:
                                print(f"   Latest Message: {part['text']}")
                                break

                # Show artifact count
                artifact_count = len(task_data.get("artifacts", []))
                if artifact_count > 0:
                    print(f"   Artifacts: {artifact_count}")
                    # Show latest artifact name
                    latest_artifact = task_data["artifacts"][-1]
                    print(f"   Latest Artifact: {latest_artifact.get('name', 'Unnamed')}")

                return JSONResponse(content={"status": "ok"})

            except Exception as e:
                logger.error(f"[Webhook] Error processing notification: {e}")
                raise HTTPException(status_code=400, detail=str(e))

        @self.app.get("/webhook/status")
        async def status():
            return {
                "status": "running",
                "notifications_received": len(self.received_notifications),
                "last_notification": self.received_notifications[-1] if self.received_notifications else None,
            }

    def start(self):
        """Start the webhook server in a background thread."""

        def run_server():
            config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="info")
            self.server = uvicorn.Server(config)
            asyncio.run(self.server.serve())

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        logger.info(f"[Webhook] Server starting on http://{self.host}:{self.port}")

    def stop(self):
        """Stop the webhook server."""
        if self.server:
            self.server.should_exit = True
        if self.server_thread:
            self.server_thread.join(timeout=5)

    @property
    def webhook_url(self) -> str:
        """Get the webhook URL."""
        return f"http://{self.host}:{self.port}/webhook"

    def get_notifications(self) -> List[Dict[str, Any]]:
        """Get all received notifications."""
        return self.received_notifications.copy()

    def clear_notifications(self):
        """Clear all received notifications."""
        self.received_notifications.clear()

    def create_task_event(self, task_id: str) -> threading.Event:
        """Create an event for waiting on a specific task completion."""
        event = threading.Event()
        self.task_events[task_id] = event
        return event

    def remove_task_event(self, task_id: str):
        """Remove a task event after use."""
        if task_id in self.task_events:
            del self.task_events[task_id]


class PushNotificationTrpcA2AClient:
    """A2A client with push notification support using tRPC-A2A with unary requests."""

    def __init__(self, service_name: str, webhook_port: int = 19080):
        self.service_name = service_name
        self.webhook_port = webhook_port
        self.a2a_client: Optional[TrpcA2AClient] = None
        self.card_resolver: Optional[TrpcA2ACardResolver] = None
        self.agent_card = None
        self.webhook_server: Optional[PushNotificationServer] = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.webhook_server:
            self.webhook_server.stop()
        # tRPC client cleanup is handled automatically

    async def initialize(self):
        """Initialize the client with agent card discovery and webhook server."""
        logger.info("Initializing Push Notification A2A client...")

        try:
            # Create card resolver
            self.card_resolver = TrpcA2ACardResolver()

            # Create tRPC context
            ctx = Context()

            # Get agent card using the resolver
            resolver_result = await self.card_resolver.get_from_agent_service(ctx, self.service_name)
            self.agent_card = resolver_result.card

            logger.info(f"Agent Name: {self.agent_card.name}")
            logger.info(f"Description: {self.agent_card.description}")
            logger.info(f"Version: {self.agent_card.version}")
            logger.info(f"Streaming: {self.agent_card.capabilities.streaming}")
            logger.info(f"Push Notifications: {self.agent_card.capabilities.push_notifications}")

            if not self.agent_card.capabilities.push_notifications:
                logger.error("Agent does not support push notifications!")
                return False

            # Create A2A client using the resolver result
            self.a2a_client = TrpcA2AClient(service_name=self.service_name, resolver_result=resolver_result)

            # Start webhook server
            self.webhook_server = PushNotificationServer(port=self.webhook_port)
            self.webhook_server.start()

            # Give the server a moment to start
            await asyncio.sleep(2)

            logger.info(f"Webhook server started at: {self.webhook_server.webhook_url}")

            return True

        except TRPCBaseError as e:
            logger.error(f"Failed to initialize client (TRPC error): {e}")
            return False
        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"Failed to initialize client: {e}")
            return False

    async def _process_request(self, input_text: str) -> Optional[Task]:
        """Send unary request with push notifications and return Task."""
        try:
            # Clear previous notifications
            self.webhook_server.clear_notifications()

            # Create push notification config
            push_config = PushNotificationConfig(
                url=self.webhook_server.webhook_url,
                token="test-auth-token-123"  # Optional authentication token
            )

            # Create message
            message_parts = [Part(root=TextPart(text=input_text))]
            message = Message(role=Role.user, message_id=str(uuid4()), parts=message_parts)
            request_id = str(uuid4())

            # Create configuration with push notifications
            configuration = MessageSendConfiguration(
                accepted_output_modes=["text/plain", "application/json"],
                push_notification_config=push_config,  # Set push notification config directly
                blocking=False,  # NEED IT, otherwise the client will wait for the task to complete
            )

            # Send unary request with push notification config
            message_params = MessageSendParams(message=message, configuration=configuration)
            request = SendMessageRequest(id=request_id, params=message_params)

            logger.info("🚀 Creating unary task with push notifications...")
            logger.info(f"   Push notification URL: {push_config.url}")

            # Send unary request
            response = await self.a2a_client.send_message(Context(), request)

            result = response.root.result

            if not isinstance(result, Task):
                logger.error(f"Expected Task, got {type(result)}")
                return None

            task = result
            logger.info(f"📦 Task created: {task.id}")
            logger.info(f"📊 Status: {task.status.state}")

            logger.info("✅ Unary request completed - Task returned, will use webhooks to receive updates")
            return task

        except TRPCBaseError as e:
            logger.error(f"Unary request processing error (TRPC): {e}")
            return None
        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"Unary request processing error: {e}")
            return None

    async def _wait_for_task_completion(self, task_id: str, timeout_seconds: int = 300) -> bool:
        """Wait for task to complete using event-based signaling."""
        logger.info(f"⏳ Waiting for task {task_id} to complete...")

        # Create an event for this task
        completion_event = self.webhook_server.create_task_event(task_id)

        try:
            # Wait for the event to be set (task completion) or timeout
            # Use threading.Event.wait() which is thread-safe
            if completion_event.wait(timeout=timeout_seconds):
                logger.info(f"✅ Task {task_id} completed successfully!")
                return True
            else:
                logger.warning(f"⏰ Timeout waiting for task {task_id} to complete after {timeout_seconds} seconds")
                return False
        finally:
            # Clean up the event
            self.webhook_server.remove_task_event(task_id)

    async def test_with_push_notifications(self, input_text: str) -> bool:
        """Test task creation with unary request and push notifications."""
        logger.info(f"\n--- Testing unary task with push notifications: '{input_text}' ---")

        # Process request
        result = await self._process_request(input_text)

        if result is None:
            logger.error("❌ Expected Task from unary request")
            return False

        if not isinstance(result, Task):
            logger.error(f"❌ Expected Task, got {type(result)}")
            return False

        logger.info("✅ Unary request sent - Task returned, webhooks configured")

        # Wait for task completion instead of fixed sleep
        task_completed = await self._wait_for_task_completion(result.id)

        if not task_completed:
            logger.warning("⚠️ Task did not complete within timeout period")

        # Check webhook notifications
        final_notifications = self.webhook_server.get_notifications()

        logger.info(f"📊 Notifications received: {len(final_notifications)}")

        return task_completed

    async def run_push_notification_tests(self):
        """Run push notification tests."""
        logger.info("\n🚀 Starting Unary Push Notification Tests")

        success = await self.initialize()
        if not success:
            logger.error("❌ Failed to initialize client")
            return False

        # Test unary with push notifications
        test_input = "multi step process"
        description = "Unary task workflow with push notifications"

        logger.info(f"\n=== Testing: {description} ===")

        # Test with unary and push notifications

        success_push = await self.test_with_push_notifications(test_input)

        if success_push:
            logger.info("✅ Unary push notification test passed")
        else:
            logger.error("❌ Unary push notification test failed")

        # Print summary of all notifications received
        all_notifications = self.webhook_server.get_notifications()
        logger.info("\n📊 Push Notification Summary:")
        logger.info(f"   Total notifications received: {len(all_notifications)}")

        if all_notifications:
            task_states = {}
            for notif in all_notifications:
                # Each notification is a complete Task object
                task_data = notif["task_data"]
                task_state = task_data.get("status", {}).get("state", "unknown")
                task_states[task_state] = task_states.get(task_state, 0) + 1

            logger.info("   Task states received:")
            for state, count in task_states.items():
                logger.info(f"     {state}: {count}")

            # Show artifact progression
            max_artifacts = 0
            for notif in all_notifications:
                task_data = notif["task_data"]
                artifact_count = len(task_data.get("artifacts", []))
                max_artifacts = max(max_artifacts, artifact_count)

            if max_artifacts > 0:
                logger.info(f"   Maximum artifacts in any notification: {max_artifacts}")

        return success_push


async def main():
    """Main function to run the push notification tests."""
    # Setup tRPC-Python environment
    config.load_global_config("examples/clients/trpc_python.yaml", "utf-8")
    setup()

    async with PushNotificationTrpcA2AClient("trpc.a2a_test.test_a2a_agent") as client:
        try:
            success = await client.run_push_notification_tests()
            return 0 if success else 1

        except KeyboardInterrupt:
            logger.info("\n⚠️ Unary push notification tests interrupted by user")
            return 1
        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"\n💥 Unexpected error: {e}")
            return 1


if __name__ == "__main__":
    import sys

    exit_code = asyncio.run(main())
    sys.exit(exit_code)
