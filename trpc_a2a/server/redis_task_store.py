# Tencent is pleased to support the open source community by making tRPC-A2A-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-A2A-Python is licensed under Apache-2.0.

import json
from datetime import datetime
from typing import Optional
from typing_extensions import override

from a2a.types import Task
from a2a.types import TaskState
from a2a.types import TaskStatus
from a2a.server.tasks import TaskStore

from trpc_sdk.abc import TrpcContext
from trpc_sdk.log import logger
from .redis_conf import RedisConf
from .redis_conf import new_redis_client


class RedisTaskStore(TaskStore):
    """Redis-based implementation of TaskStore.

    Stores task objects in Redis for distributed access. Task data persists
    across server restarts and can be shared between multiple server instances.
    """

    def __init__(self, redis_config: RedisConf) -> None:
        """Initializes the RedisTaskStore.
        
        Args:
            redis_url: Redis connection URL
            db: Redis database number
            key_prefix: Prefix for task keys in Redis
            ttl: Time-to-live for tasks in seconds
        """
        logger.debug('Initializing RedisTaskStore')
        self.key_prefix = redis_config.task_key_prefix
        self._redis_name = redis_config.redis_name
        self._ttl = redis_config.ttl
        self._redis = new_redis_client(self._redis_name)

    @override
    async def save(self, task: Task) -> None:
        """Saves or updates a task in the Redis store."""
        try:
            key = f"{self.key_prefix}{task.id}"

            # Serialize task
            task_data = self._serialize_task(task)

            # Store with TTL
            ctx = TrpcContext()
            await self._redis.setex(ctx, key, self._ttl, json.dumps(task_data))

            logger.debug('Task %s saved successfully.', task.id)

        except Exception as e:
            logger.error('Error saving task %s: %s', task.id, e)
            raise

    @override
    async def get(self, task_id: str) -> Task | None:
        """Retrieves a task from the Redis store by ID."""
        try:
            key = f"{self.key_prefix}{task_id}"

            logger.debug('Attempting to get task with id: %s', task_id)

            ctx = TrpcContext()
            task_data = await self._redis.get(ctx, key)
            if task_data:
                task = self._deserialize_task(json.loads(task_data))
                if task:
                    logger.debug('Task %s retrieved successfully.', task_id)
                else:
                    logger.debug('Task %s deserialization failed.', task_id)
                return task
            else:
                logger.debug('Task %s not found in store.', task_id)
                return None

        except Exception as e:
            logger.error('Error getting task %s: %s', task_id, e)
            return None

    @override
    async def delete(self, task_id: str) -> None:
        """Deletes a task from the Redis store by ID."""
        try:
            key = f"{self.key_prefix}{task_id}"

            logger.debug('Attempting to delete task with id: %s', task_id)

            ctx = TrpcContext()
            deleted = await self._redis.delete(ctx, key)
            if deleted:
                logger.debug('Task %s deleted successfully.', task_id)
            else:
                logger.warning('Attempted to delete nonexistent task with id: %s', task_id)

        except Exception as e:
            logger.error('Error deleting task %s: %s', task_id, e)
            raise

    def _serialize_task(self, task: Task) -> dict:
        """Serialize Task object for Redis storage."""
        if hasattr(task, 'model_dump'):
            return task.model_dump()
        else:
            # Manual serialization
            return {
                "id": task.id,
                "context_id": task.context_id,
                "status": task.status.model_dump() if hasattr(task.status, 'model_dump') else task.status.__dict__,
                "createdAt": task.createdAt.isoformat() if task.createdAt else None,
                "updatedAt": task.updatedAt.isoformat() if task.updatedAt else None,
            }

    def _deserialize_task(self, task_data: dict) -> Optional[Task]:
        """Deserialize Task object from Redis storage."""
        try:
            # Rebuild Task object
            status_data = task_data.get("status", {})
            status = TaskStatus(
                state=TaskState(status_data.get("state", "pending")),
                message=None  # Simplified handling
            )

            task = Task(
                id=task_data["id"],
                context_id=task_data["context_id"],
                status=status,
                createdAt=datetime.fromisoformat(task_data["createdAt"]) if task_data.get("createdAt") else None,
                updatedAt=datetime.fromisoformat(task_data["updatedAt"]) if task_data.get("updatedAt") else None)

            return task

        except Exception as e:
            logger.error('Error deserializing task: %s', e)
            return None
