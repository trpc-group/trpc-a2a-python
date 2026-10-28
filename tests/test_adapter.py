# Tencent is pleased to support the open source community by making tRPC-A2A-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-A2A-Python is licensed under Apache-2.0.
"""Tests of the protocol registration and the WORKER plugin that builds A2A apps."""
import asyncio
from unittest import mock

from trpc_sdk.transport import get_protocol_handle
from trpc_fastapi import _trpc_server_process
from trpc_fastapi._trpc_server_process import start_fastapi

from trpc_a2a import register_service
from trpc_a2a.server import _trpc_fastapi_adapter
from trpc_a2a.server._trpc_fastapi_adapter import _run_blocking
from trpc_a2a.server._trpc_fastapi_adapter import find_a2a_services
from trpc_a2a.server._trpc_fastapi_adapter import setup_a2a_agent

from .conftest import SERVICE_NAME
from .conftest import EchoAgent

_A2A_YAML = f"""
server:
  app: test
  server: a2a
  service:
    - name: {SERVICE_NAME}
      protocol: a2a
      ip: 127.0.0.1
      port: 18080
      network: tcp
    - name: trpc.test.other.Greeter
      protocol: trpc
      ip: 127.0.0.1
      port: 18081
      network: tcp
"""

_MULTI_PROCESS_YAML = """
global:
  processmodel:
    mode: multi_process
    io_handle_type: separate
    handle_num: 2
""" + _A2A_YAML


def test_a2a_protocol_served_by_fastapi_starter():
    """Test importing trpc_a2a binds the a2a protocol to the fastapi starter."""
    assert get_protocol_handle("a2a") is start_fastapi


def test_find_a2a_services_reads_only_a2a_services(load_config):
    """Test only services with protocol a2a are collected."""
    load_config(_A2A_YAML)

    services = find_a2a_services()

    assert list(services) == [SERVICE_NAME]
    assert services[SERVICE_NAME].port == 18080


def test_run_blocking_leaves_thread_loop_untouched():
    """Test the private loop never replaces the loop installed for this thread."""
    policy = asyncio.get_event_loop_policy()
    loop = asyncio.new_event_loop()
    policy.set_event_loop(loop)
    try:

        async def _answer():
            return 42

        assert _run_blocking(_answer()) == 42
        assert policy.get_event_loop() is loop
        assert not loop.is_closed()
    finally:
        policy.set_event_loop(None)
        loop.close()


def test_setup_registers_app_once_per_process(load_config, monkeypatch):
    """Test the plugin builds and registers the app, and a second call is a no-op."""
    monkeypatch.setattr(_trpc_server_process, "_user_fastapi_app", {})
    load_config(_A2A_YAML)
    register_service(SERVICE_NAME, EchoAgent())

    setup_a2a_agent()
    app = _trpc_server_process._user_fastapi_app[SERVICE_NAME]
    setup_a2a_agent()

    assert _trpc_server_process._user_fastapi_app[SERVICE_NAME] is app


def test_setup_skips_unregistered_service(load_config, monkeypatch):
    """Test a configured service with no registered agent gets no app."""
    monkeypatch.setattr(_trpc_server_process, "_user_fastapi_app", {})
    load_config(_A2A_YAML)

    setup_a2a_agent()

    assert SERVICE_NAME not in _trpc_server_process._user_fastapi_app


def test_multi_process_without_redis_warns(load_config, monkeypatch):
    """Test several serving processes with in-memory stores log a warning."""
    monkeypatch.setattr(_trpc_server_process, "_user_fastapi_app", {})
    logger = mock.Mock()
    monkeypatch.setattr(_trpc_fastapi_adapter, "logger", logger)
    load_config(_MULTI_PROCESS_YAML)

    setup_a2a_agent()

    warnings = [call.args[0] for call in logger.warning.call_args_list]
    assert any(SERVICE_NAME in w and "redis_name" in w for w in warnings)


def test_single_process_does_not_warn(load_config, monkeypatch):
    """Test the default process model logs no shared-state warning."""
    monkeypatch.setattr(_trpc_server_process, "_user_fastapi_app", {})
    logger = mock.Mock()
    monkeypatch.setattr(_trpc_fastapi_adapter, "logger", logger)
    load_config(_A2A_YAML)
    register_service(SERVICE_NAME, EchoAgent())

    setup_a2a_agent()

    assert not any("redis_name" in call.args[0] for call in logger.warning.call_args_list)
