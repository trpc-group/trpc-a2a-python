# Tencent is pleased to support the open source community by making tRPC-A2A-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-A2A-Python is licensed under Apache-2.0.
"""Tests of the redis store configuration and the lazy ``trpc_redis`` import."""
import builtins

import pytest

from trpc_a2a.server.redis_conf import DEFAULT_TTL
from trpc_a2a.server.redis_conf import NOTIFICATION_KEY_PREFIX_VALUE
from trpc_a2a.server.redis_conf import TASK_KEY_PREFIX_VALUE
from trpc_a2a.server.redis_conf import RedisConf
from trpc_a2a.server.redis_conf import get_redis_conf_by_name
from trpc_a2a.server.redis_task_store import RedisTaskStore

from .conftest import SERVICE_NAME

_REDIS_YAML = f"""
server:
  service:
    - name: {SERVICE_NAME}
      protocol: a2a
      ip: 127.0.0.1
      port: 18080
      redis_name: trpc.redis.test
      task_key_prefix: "t:"
      notification_key_prefix: "n:"
client:
  service:
    - name: trpc.redis.test
      target: ip://127.0.0.1:6379
      ttl: 60
"""


def test_reads_redis_fields_of_service(load_config):
    """Test redis_name, ttl and both prefixes come from the raw YAML."""
    load_config(_REDIS_YAML)

    assert get_redis_conf_by_name(SERVICE_NAME) == RedisConf(redis_name="trpc.redis.test",
                                                             ttl=60,
                                                             task_key_prefix="t:",
                                                             notification_key_prefix="n:")


def test_missing_client_service_means_no_redis(load_config):
    """Test a redis_name with no matching client service falls back to memory stores."""
    load_config(f"""
server:
  service:
    - name: {SERVICE_NAME}
      protocol: a2a
      redis_name: trpc.redis.missing
""")

    conf = get_redis_conf_by_name(SERVICE_NAME)

    assert conf.redis_name == ""
    assert conf.ttl == DEFAULT_TTL
    assert conf.task_key_prefix == TASK_KEY_PREFIX_VALUE
    assert conf.notification_key_prefix == NOTIFICATION_KEY_PREFIX_VALUE


def test_unknown_service_means_no_redis(load_config):
    """Test a service that is not configured has no redis store."""
    load_config(_REDIS_YAML)

    assert get_redis_conf_by_name("trpc.unknown").redis_name == ""


def test_missing_trpc_redis_raises_clear_error(monkeypatch):
    """Test the store points at the redis extra when trpc_redis is not installed."""
    real_import = builtins.__import__

    def _no_trpc_redis(name, *args, **kwargs):
        if name == "trpc_redis" or name.startswith("trpc_redis."):
            raise ImportError("No module named 'trpc_redis'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_trpc_redis)

    with pytest.raises(ImportError, match=r"trpc-a2a\[redis\]"):
        RedisTaskStore(RedisConf(redis_name="trpc.redis.test"))
