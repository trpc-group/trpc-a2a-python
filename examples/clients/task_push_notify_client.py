# -*- coding: utf-8 -*-
#
# Copyright @ 2025 Tencent.com
"""Task-specific push notification client demonstrating task callback notifications with tRPC-A2A server."""

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
    SendMessageRequest,
    SendStreamingMessageRequest,
    Task,
    TaskState,
    PushNotificationConfig,
    SetTaskPushNotificationConfigRequest,
    TaskPushNotificationConfig,
    GetTaskPushNotificationConfigRequest,
    GetTaskPushNotificationConfigParams,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
)

from trpc_a2a.client import TrpcA2AClient, TrpcA2ACardResolver


class TaskWebhookServer:
    """Webhook server to receive task-specific push notifications."""

    def __init__(self, host: str = "localhost", port: int = 19081):
        self.host = host
        self.port = port
        self.app = FastAPI(title="Task Push Notification Webhook Server")
        self.received_notifications: List[Dict[str, Any]] = []
        self.server = None
        self.server_thread = None

        # Setup webhook endpoint
        @self.app.post("/task-webhook")
        async def task_webhook_handler(request: Request):
            try:
                # Parse the notification payload
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

                logger.info(f"[TaskWebhook] Received task notification: {task_data.get('id', 'Unknown')}")
                print(f"\n🔔 Task Push Notification Received at {timestamp}")
                print(f"   Task ID: {task_data.get('id', 'Unknown')}")
                print(f"   Status: {task_data.get('status', {}).get('state', 'Unknown')}")

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
                logger.error(f"[TaskWebhook] Error processing notification: {e}")
                raise HTTPException(status_code=400, detail=str(e))

        @self.app.get("/task-webhook/status")
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
        logger.info(f"[TaskWebhook] Server starting on http://{self.host}:{self.port}")

    def stop(self):
        """Stop the webhook server."""
        if self.server:
            self.server.should_exit = True
        if self.server_thread:
            self.server_thread.join(timeout=5)

    @property
    def webhook_url(self) -> str:
        """Get the webhook URL."""
        return f"http://{self.host}:{self.port}/task-webhook"

    def get_notifications(self) -> List[Dict[str, Any]]:
        """Get all received notifications."""
        return self.received_notifications.copy()

    def clear_notifications(self):
        """Clear all received notifications."""
        self.received_notifications.clear()


class TaskPushNotificationTrpcA2AClient:
    """A2A client with task-specific push notification support."""

    def __init__(self, service_name: str, webhook_port: int = 19081):
        self.service_name = service_name
        self.webhook_port = webhook_port
        self.a2a_client: Optional[TrpcA2AClient] = None
        self.card_resolver: Optional[TrpcA2ACardResolver] = None
        self.agent_card = None
        self.webhook_server: Optional[TaskWebhookServer] = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.webhook_server:
            self.webhook_server.stop()
        # tRPC client cleanup is handled automatically

    async def initialize(self):
        """Initialize the client with agent card discovery and webhook server."""
        logger.info("Initializing Task Push Notification A2A client...")

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
            self.webhook_server = TaskWebhookServer(port=self.webhook_port)
            self.webhook_server.start()

            # Give the server a moment to start
            await asyncio.sleep(2)

            logger.info(f"Task webhook server started at: {self.webhook_server.webhook_url}")

            return True

        except TRPCBaseError as e:
            logger.error(f"Failed to initialize client (TRPC error): {e}")
            return False
        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"Failed to initialize client: {e}")
            return False

    async def test_task_push_notifications(self) -> bool:
        """Test task-specific push notifications in multi-turn scenario."""
        logger.info("\n--- Testing task-specific push notifications ---")

        try:
            # Clear previous notifications
            self.webhook_server.clear_notifications()

            # Step 1: Send initial message to create a task
            logger.info("🚀 Step 1: Creating initial task...")

            message_parts = [Part(root=TextPart(text="Hello, I need help with a task"))]
            message = Message(role=Role.user, message_id=str(uuid4()), parts=message_parts)
            request = SendMessageRequest(id=str(uuid4()), params=MessageSendParams(message=message))

            # Create tRPC context
            ctx = Context()
            response = await self.a2a_client.send_message(ctx, request)

            result = response.root.result
            if not isinstance(result, Task):
                logger.error("Expected Task result from initial message")
                return False

            task = result
            task_id = task.id
            logger.info(f"✅ Task created: {task_id}")
            logger.info(f"   Status: {task.status.state}")

            # Verify the task is waiting for input
            if task.status.state != TaskState.input_required:
                logger.error(f"Expected input_required status, got: {task.status.state}")
                return False

            logger.info("✅ Task is waiting for user input")

            # Step 2: Set up task-specific push notification config
            logger.info("🔧 Step 2: Setting up task-specific push notifications...")

            push_config = PushNotificationConfig(url=self.webhook_server.webhook_url,
                                                 token="task-specific-auth-token-456")

            set_config_params = TaskPushNotificationConfig(task_id=task_id, push_notification_config=push_config)
            set_config_request = SetTaskPushNotificationConfigRequest(id=str(uuid4()), params=set_config_params)

            set_response = await self.a2a_client.set_task_callback(ctx, set_config_request)

            logger.info(f"✅ Push notification config set for task: {task_id}")
            logger.info(f"   Webhook URL: {push_config.url}")

            # Step 3: Verify the config was set (optional)
            logger.info("🔍 Step 3: Verifying push notification config...")

            get_config_params = GetTaskPushNotificationConfigParams(id=task_id)
            get_config_request = GetTaskPushNotificationConfigRequest(id=str(uuid4()), params=get_config_params)

            get_response = await self.a2a_client.get_task_callback(ctx, get_config_request)

            retrieved_config = get_response.root.result.push_notification_config
            logger.info("✅ Verified push notification config:")
            logger.info(f"   URL: {retrieved_config.url}")
            logger.info(f"   Token: {retrieved_config.token}")

            # Step 4: Send follow-up message to trigger processing with push notifications (using streaming)
            logger.info("⚡ Step 4: Sending follow-up input to trigger processing via streaming...")

            follow_up_parts = [Part(root=TextPart(text="analyze data"))]
            follow_up_message = Message(
                role=Role.user,
                message_id=str(uuid4()),
                parts=follow_up_parts,
                task_id=task_id,  # Include task ID to continue the conversation
            )
            streaming_request = SendStreamingMessageRequest(id=str(uuid4()),
                                                            params=MessageSendParams(message=follow_up_message))

            logger.info("📡 Processing streaming responses and push notifications...")

            # Process streaming responses while push notifications come via webhook
            async for response in self.a2a_client.send_message_streaming(ctx, streaming_request):

                result = response.root.result

                # Handle different types of streaming responses
                if isinstance(result, TaskStatusUpdateEvent):
                    logger.info(f"📊 Streaming Status Update: {result.status.state}")
                    if result.final:
                        logger.info("✅ Received final status update via streaming")
                        break
                elif isinstance(result, TaskArtifactUpdateEvent):
                    artifact_name = result.artifact.name or "Unnamed"
                    logger.info(f"🎯 Streaming Artifact Update: {artifact_name}")
                elif isinstance(result, Task):
                    logger.info(f"📦 Streaming Task Update: {result.id} - Status: {result.status.state}")
                else:
                    logger.info(f"📡 Other streaming response: {type(result).__name__}")

            logger.info("✅ Streaming processing completed")

            # Step 5: Check received push notifications
            logger.info("📋 Step 5: Analyzing received push notifications...")

            # Check received notifications
            notifications = self.webhook_server.get_notifications()
            logger.info(f"📊 Received {len(notifications)} push notifications")

            if len(notifications) == 0:
                logger.error("❌ No push notifications received")
                return False

            # Analyze the notifications
            logger.info("\n📋 Push Notification Analysis:")
            task_states = {}
            artifact_count = 0

            for i, notif in enumerate(notifications, 1):
                task_data = notif["task_data"]
                task_state = task_data.get("status", {}).get("state", "unknown")
                current_artifacts = len(task_data.get("artifacts", []))

                task_states[task_state] = task_states.get(task_state, 0) + 1
                artifact_count = max(artifact_count, current_artifacts)

                logger.info(f"   Notification {i}: State={task_state}, Artifacts={current_artifacts}")

            logger.info("\n📈 Summary:")
            logger.info(f"   Total notifications: {len(notifications)}")
            logger.info(f"   States observed: {list(task_states.keys())}")
            logger.info(f"   Maximum artifacts: {artifact_count}")

            # Verify we got meaningful notifications
            success = (len(notifications) > 0 and ("working" in task_states or "completed" in task_states)
                       and artifact_count > 0)

            if success:
                logger.info("✅ Task-specific push notifications test passed!")
                logger.info("   → Task was created successfully")
                logger.info("   → Push notification config was set for specific task")
                logger.info("   → Processing triggered with follow-up input")
                logger.info("   → Push notifications received via webhook")
            else:
                logger.error("❌ Task-specific push notifications test failed")

            return success

        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"Task push notifications test error: {e}")
            return False

    async def run_task_push_notification_tests(self):
        """Run task-specific push notification tests."""
        logger.info("\n🚀 Starting Task-Specific Push Notification Tests")

        success = await self.initialize()
        if not success:
            logger.error("❌ Failed to initialize client")
            return False

        # Test task-specific push notifications
        test_success = await self.test_task_push_notifications()

        logger.info("\n🏁 Task-specific push notification tests completed")
        logger.info(f"Overall result: {'✅ PASSED' if test_success else '❌ FAILED'}")

        if test_success:
            logger.info("\n💡 Key Features Demonstrated:")
            logger.info("   • Multi-turn conversation with task creation")
            logger.info("   • Task-specific push notification configuration")
            logger.info("   • Push notification config verification")
            logger.info("   • Real-time task processing updates via webhooks")
            logger.info("   • Task-specific callback isolation")

        return test_success


async def main():
    """Main function to run the task-specific push notification tests."""
    # Setup tRPC-Python environment
    config.load_global_config("examples/clients/trpc_python.yaml", "utf-8")
    setup()

    async with TaskPushNotificationTrpcA2AClient("trpc.a2a_test.test_a2a_agent", 19081) as client:
        try:
            success = await client.run_task_push_notification_tests()
            return 0 if success else 1

        except KeyboardInterrupt:
            logger.info("\n⚠️ Task-specific push notification tests interrupted by user")
            return 1
        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"\n💥 Unexpected error: {e}")
            return 1


if __name__ == "__main__":
    import sys

    exit_code = asyncio.run(main())
    sys.exit(exit_code)
