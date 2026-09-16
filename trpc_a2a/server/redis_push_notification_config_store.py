# -*- coding: utf-8 -*-
#
# Copyright @ 2025 Tencent.com

import json
from typing import Optional
from typing_extensions import override

from a2a.types import PushNotificationConfig
from a2a.server.tasks import PushNotificationConfigStore

from trpc.log import logger
from trpc.trpc_abc.context import Context
from trpc_redis.client import Client as RedisClient
from .redis_conf import RedisConf


class RedisPushNotificationConfigStore(PushNotificationConfigStore):
    """Redis-based implementation of PushNotificationConfigStore interface.

    Stores push notification configurations in Redis for distributed access
    """

    def __init__(self, redis_config: RedisConf) -> None:
        """Initializes the RedisPushNotificationConfigStore.
        
        Args:
            redis_url: Redis connection URL
            db: Redis database number
            key_prefix: Prefix for push notification keys in Redis
            ttl: Time-to-live for configurations in seconds
        """
        self.key_prefix = redis_config.notification_key_prefix
        self._redis_name = redis_config.redis_name
        self._ttl = redis_config.ttl
        self._redis = RedisClient(name=self._redis_name)

    @override
    async def set_info(self, task_id: str, notification_config: PushNotificationConfig) -> None:
        """Sets or updates the push notification configuration for a task in Redis."""
        try:
            key = f"{self.key_prefix}{task_id}"

            # Get existing configurations
            ctx = Context()
            existing_data = await self._redis.get(ctx, key)
            configurations = []

            if existing_data:
                configurations = json.loads(existing_data)

            # Set config ID if not provided
            if notification_config.id is None:
                notification_config.id = task_id

            # Remove existing config with same ID if exists
            configurations = [config for config in configurations if config.get('id') != notification_config.id]

            # Add new configuration
            config_dict = {
                'id': notification_config.id,
                'url': notification_config.url,
                'token': notification_config.token
            }
            configurations.append(config_dict)

            # Store in Redis with TTL
            await self._redis.setex(ctx, key, self._ttl, json.dumps(configurations))

            logger.debug(f"[RedisPushNotificationConfigStore] Set config for task {task_id}")

        except Exception as e:
            logger.error(f"[RedisPushNotificationConfigStore] Error setting config for task {task_id}: {e}")
            raise

    @override
    async def get_info(self, task_id: str) -> list[PushNotificationConfig]:
        """Retrieves the push notification configuration for a task from Redis."""
        try:
            key = f"{self.key_prefix}{task_id}"

            ctx = Context()
            config_data = await self._redis.get(ctx, key)
            if not config_data:
                return []

            config_list = json.loads(config_data)
            configurations = []

            for config_dict in config_list:
                config = PushNotificationConfig(id=config_dict.get('id'),
                                                url=config_dict.get('url'),
                                                token=config_dict.get('token'))
                configurations.append(config)

            return configurations

        except Exception as e:
            logger.error(f"[RedisPushNotificationConfigStore] Error getting config for task {task_id}: {e}")
            return []

    @override
    async def delete_info(self, task_id: str, config_id: Optional[str] = None) -> None:
        """Deletes the push notification configuration for a task from Redis."""
        try:
            key = f"{self.key_prefix}{task_id}"

            if config_id is None:
                config_id = task_id

            # Get existing configurations
            ctx = Context()
            existing_data = await self._redis.get(ctx, key)
            if not existing_data:
                return

            configurations = json.loads(existing_data)

            # Remove config with matching ID
            configurations = [config for config in configurations if config.get('id') != config_id]

            if not configurations:
                # If no configs left, delete the key entirely
                await self._redis.delete(ctx, key)
            else:
                # Update with remaining configs
                await self._redis.setex(ctx, key, self._ttl, json.dumps(configurations))

            logger.debug(f"[RedisPushNotificationConfigStore] Deleted config {config_id} for task {task_id}")

        except Exception as e:
            logger.error(f"[RedisPushNotificationConfigStore] Error deleting config for task {task_id}: {e}")
            raise
