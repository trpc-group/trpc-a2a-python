# Tencent is pleased to support the open source community by making tRPC-A2A-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-A2A-Python is licensed under Apache-2.0.

from dataclasses import dataclass
from typing import Any
from typing import Dict

from trpc_sdk.config import TrpcConfig

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


def new_redis_client(redis_name: str) -> Any:
    """Create a ``trpc_redis`` client, importing ``trpc_redis`` on first use.

    Args:
        redis_name: Client service name of the redis backend.

    Returns:
        A ``trpc_redis.Client`` for ``redis_name``.

    Raises:
        ImportError: ``trpc_redis`` is not installed.
    """
    try:
        from trpc_redis import Client as RedisClient  # pylint: disable=import-outside-toplevel
    except ImportError as e:
        raise ImportError(f"redis_name '{redis_name}' needs the redis task store; "
                          "install it with: pip install 'trpc-a2a[redis]'") from e
    return RedisClient(name=redis_name)


def _raw_section(key: str) -> Dict[str, Any]:
    """Return one top-level section of the loaded YAML as a plain dict.

    The typed ``ServerService`` drops unknown keys such as ``redis_name``, so
    they are read from the raw config instead.
    """
    parser = TrpcConfig.config_parser()
    if parser is None:
        return {}
    return parser.get(key) or {}


def get_redis_conf_by_name(name: str) -> RedisConf:
    """Get the redis store configuration of the server service ``name``.

    Args:
        name: Server service name.

    Returns:
        The service's redis config; ``redis_name`` is empty when the service
        sets no ``redis_name`` or no client service of that name exists.
    """
    client_conf_dict = _raw_section('client')
    client_service_conf_list = client_conf_dict.get('service') or []
    server_conf_dict = _raw_section('server')
    redis_config = RedisConf()
    for service_dict in server_conf_dict.get('service') or []:
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
