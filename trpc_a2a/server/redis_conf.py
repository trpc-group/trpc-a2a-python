# -*- coding: utf-8 -*-
#
# Copyright @ 2025 Tencent.com

from dataclasses import dataclass
from trpc.config import config

TASK_KEY_PREFIX = "task_key_prefix"
TASK_KEY_PREFIX_VALUE = "a2a:tasks:"

NOTIFICATION_KEY_PREFIX = "notification_key_prefix"
NOTIFICATION_KEY_PREFIX_VALUE = "a2a:push_notifications:"

TTL = "ttl"
DEFAULT_TTL = 3600

REDIS_SERVICE_NAME = "redis_name"


@dataclass
class RedisConf:
    redis_name: str = ""
    ttl: int = DEFAULT_TTL
    task_key_prefix: str = TASK_KEY_PREFIX_VALUE
    notification_key_prefix: str = NOTIFICATION_KEY_PREFIX_VALUE


def get_redis_conf_by_name(name: str) -> RedisConf:
    """Get a configuration value by name."""
    client_conf_dict = config.global_config.config.get('client', {})
    client_service_conf_list = client_conf_dict.get('service', [])
    server_conf_dict = config.global_config.config.get('server', {})
    redis_config = RedisConf()
    for service_dict in server_conf_dict.get('service', []):
        if service_dict.get('name') == name:
            redis_name = service_dict.get(REDIS_SERVICE_NAME, "")
            if redis_name:
                for client_service in client_service_conf_list:
                    if client_service.get("name", None) == redis_name:
                        redis_config.ttl = client_service.get(TTL, DEFAULT_TTL)
                        redis_config.redis_name = redis_name
                        redis_config.task_key_prefix = service_dict.get(TASK_KEY_PREFIX, TASK_KEY_PREFIX_VALUE)
                        redis_config.notification_key_prefix = service_dict.get(NOTIFICATION_KEY_PREFIX,
                                                                                NOTIFICATION_KEY_PREFIX_VALUE)
                        return redis_config
    return redis_config
